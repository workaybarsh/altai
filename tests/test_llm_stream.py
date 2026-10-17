"""llm-stream.py'nin cevrimdisi davranislarini dogrular (gercek LLM/TTS gerekmez)."""
import importlib.util
import json
import os
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("llm_stream", os.path.join(ROOT, "agent", "llm-stream.py"))
ls = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ls)


# --------------------------------------------------------------- cumle bolme

def test_sentence_buffer_splits_on_boundary():
    sb = ls.SentenceBuffer()
    assert sb.feed("Merhaba") == []
    assert sb.feed(" dünya! Nasıl") == ["Merhaba dünya!"]
    assert sb.flush() == ["Nasıl"]


def test_sentence_buffer_symbol_only_is_not_speakable():
    """Tampon saf bolme yapar; gonderilebilirlik filtresi cagirana (run) aittir."""
    sb = ls.SentenceBuffer()
    out = sb.feed("???") + sb.flush()
    assert out == ["???"]
    assert not any(ls.is_speakable(s) for s in out)


def test_sentence_buffer_force_flush_long_text():
    sb = ls.SentenceBuffer(force_chars=40, soft_chars=0)
    out = sb.feed("kelime " * 12)     # sinirdan uzun, noktalama yok
    assert out and len(out[0]) <= 41
    assert out[0].startswith("kelime")


def test_sentence_buffer_soft_split_on_comma():
    sb = ls.SentenceBuffer(force_chars=500, soft_chars=30)
    out = sb.feed("birinci kisim, ikinci kisim, ucuncu kisim devam ediyor")
    assert out and out[0].endswith(",")     # virgulden erken baslatildi


def test_is_speakable():
    assert ls.is_speakable("Merhaba")
    assert ls.is_speakable("3 elma")
    assert not ls.is_speakable("???")
    assert not ls.is_speakable("")


def test_json_summary_is_utf8_literal(tmp_path):
    """--json-out UTF-8 ve ensure_ascii=False yazmali (tuzak #14).

    Dosyayi PowerShell 5.1 `Get-Content -Raw` ile okuyan taraf **ANSI** varsayar;
    JSON'da kacisli (\\u00e7) olursa sorun yok ama yollardaki 'i' ancak gercek
    UTF-8 baytlarinda dogru cozulur. Bu yuzden sozlesme: UTF-8 + ensure_ascii=False.
    """
    path = tmp_path / "s.json"
    ls._json({"ok": True, "text": "çığ İĞÜŞ", "out": r"C:\Varsayılan\x.wav"}, str(path))
    raw = path.read_bytes()
    assert "çığ İĞÜŞ".encode("utf-8") in raw
    assert b"\\u00e7" not in raw
    assert json.loads(raw.decode("utf-8"))["out"].endswith("x.wav")


# ------------------------------------------------------- sahte sunucular

class _FakeLLM(BaseHTTPRequestHandler):
    """SSE akisi taklidi: dusunme + icerik parcalari."""
    chunks = []
    seen_body = {}

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        _FakeLLM.seen_body = json.loads(self.rfile.read(n).decode("utf-8"))
        # Content-Length ile tek parca yaz: Windows loopback'te yarim kapanan
        # baglanti ConnectionResetError uretiyor (test kirilgan oluyordu).
        parts = []
        for kind, txt in self.chunks:
            key = "reasoning_content" if kind == "reasoning" else "content"
            payload = {"choices": [{"delta": {key: txt}, "finish_reason": None}]}
            parts.append(f"data: {json.dumps(payload)}\n\n")
        end = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        parts.append(f"data: {json.dumps(end)}\n\ndata: [DONE]\n\n")
        body = "".join(parts).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        # Windows loopback: sunucu yaniti yazdiktan hemen sonra soketi kapatirsa
        # istemcide ConnectionResetError olabiliyor -> kisa bekle.
        time.sleep(0.05)

    def log_message(self, *a):
        pass


class _FakeTTS(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        _FakeTTS.requests.append(body)
        text = body["texts"][0]
        idx = len(_FakeTTS.requests)
        out = os.path.join(body["out_dir"], f"{body.get('prefix', 's_')}{idx}.wav")
        with open(out, "wb") as f:
            f.write(b"RIFF")
        payload = {"ok": True, "count": 1, "failed": 0, "results": [
            {"ok": True, "index": 1, "text": text, "out": out, "audio_seconds": 1.0,
             "tts_seconds": 0.1, "retried": False}]}
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
        time.sleep(0.05)

    def log_message(self, *a):
        pass


def _serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_iter_deltas_separates_reasoning(tmp_path):
    _FakeLLM.chunks = [("reasoning", "dusunuyorum..."), ("content", "Merhaba!")]
    srv = _serve(_FakeLLM)
    try:
        got = list(ls.iter_deltas(f"http://127.0.0.1:{srv.server_address[1]}",
                                  [{"role": "user", "content": "selam"}], think=True))
    finally:
        srv.shutdown()
        srv.server_close()
    kinds = [k for k, _ in got]
    assert ("reasoning", "dusunuyorum...") in got
    assert ("content", "Merhaba!") in got
    assert kinds[0] == "first"                       # ilk parca isaretlenir
    assert _FakeLLM.seen_body["stream"] is True
    assert _FakeLLM.seen_body["chat_template_kwargs"]["enable_thinking"] is True


def test_run_end_to_end_with_fakes(tmp_path):
    _FakeLLM.chunks = [("reasoning", "hmm"),
                       ("content", "Merhaba! "),
                       ("content", "Nasilsin? "),
                       ("content", "Iyiyim.")]
    _FakeTTS.requests = []
    llm = _serve(_FakeLLM)
    tts_srv = _serve(_FakeTTS)
    try:
        out = ls.run("selam", f"http://127.0.0.1:{llm.server_address[1]}",
                     f"http://127.0.0.1:{tts_srv.server_address[1]}",
                     str(tmp_path), prefix="x_", lang="tr", play=False)
    finally:
        llm.shutdown()
        tts_srv.shutdown()
        llm.server_close()
        tts_srv.server_close()

    assert out["ok"] is True
    assert [s["text"] for s in out["sentences"]] == ["Merhaba!", "Nasilsin?", "Iyiyim."]
    assert out["answer"] == "Merhaba! Nasilsin? Iyiyim."
    assert out["reasoning_chars"] == 3                    # dusunme icerige karismadi
    assert out["first_token_kind"] == "reasoning"
    for key in ("first_token_seconds", "first_sentence_seconds", "first_audio_seconds",
                "llm_seconds", "total_seconds"):
        assert isinstance(out[key], float)
    # ilk ses, LLM bitmeden hazir olmali (akisli hat: ustelik asil amac)
    assert out["first_audio_seconds"] <= out["total_seconds"]
    assert sum(1 for s in out["sentences"] if os.path.exists(s["out"])) == 3
    assert len(_FakeTTS.requests) == 3                    # cumle basina bir istek


def test_run_skips_symbol_only_sentence(tmp_path):
    _FakeLLM.chunks = [("content", "???. Merhaba!")]
    _FakeTTS.requests = []
    llm = _serve(_FakeLLM)
    tts_srv = _serve(_FakeTTS)
    try:
        out = ls.run("selam", f"http://127.0.0.1:{llm.server_address[1]}",
                     f"http://127.0.0.1:{tts_srv.server_address[1]}",
                     str(tmp_path), prefix="y_", play=False)
    finally:
        llm.shutdown()
        tts_srv.shutdown()
        llm.server_close()
        tts_srv.server_close()

    assert [s["text"] for s in out["sentences"]] == ["Merhaba!"]
    assert len(_FakeTTS.requests) == 1                    # sembol-only gonderilmedi


# --------------------------------------------- dayaniklilik (Windows loopback RST)

def test_synth_retries_transient_connection_error(monkeypatch, tmp_path):
    """Gecici socket reset'i (WinError 10054) tekrar denenir; sentez idempotent."""
    calls = []

    def fake_post(url, payload, timeout=300):
        calls.append(url)
        if len(calls) == 1:
            raise ConnectionResetError("[WinError 10054] reset")
        return {"results": [{"ok": True, "out": str(tmp_path / "a.wav"), "audio_seconds": 1.0}]}

    monkeypatch.setattr(ls, "_post_json", fake_post)
    monkeypatch.setattr(ls.time, "sleep", lambda *_: None)
    res = ls.synth("http://x", "Merhaba", str(tmp_path), "s_1_", lang="tr")
    assert res["ok"] is True
    assert res["client_attempts"] == 2
    assert len(calls) == 2


def test_synth_does_not_retry_http_error(monkeypatch, tmp_path):
    """400 gibi istek reddi tekrar denenmez (girdi zaten gecersiz)."""
    calls = []

    def fake_post(url, payload, timeout=300):
        calls.append(url)
        raise urllib.error.HTTPError(url, 400, "bad request", {}, None)

    monkeypatch.setattr(ls, "_post_json", fake_post)
    with pytest.raises(urllib.error.HTTPError):
        ls.synth("http://x", "???", str(tmp_path), "s_1_")
    assert len(calls) == 1


def test_run_survives_mid_stream_reset(monkeypatch, tmp_path):
    """LLM akisi ortasinda koparsa eldeki cumleler soylenir, durum ozete yazilir."""
    _FakeTTS.requests = []
    tts = _serve(_FakeTTS)

    def fake_deltas(*a, **k):
        yield ("first", "content")
        yield ("content", "Merhaba! ")
        raise ConnectionResetError("[WinError 10054] reset")

    monkeypatch.setattr(ls, "iter_deltas", fake_deltas)
    try:
        out = ls.run("selam", "http://x", f"http://127.0.0.1:{tts.server_address[1]}",
                     str(tmp_path), prefix="r_", play=False)
    finally:
        tts.shutdown()
        tts.server_close()

    assert out["ok"] is True
    assert out["stream_error"].startswith("ConnectionResetError")
    assert [s["text"] for s in out["sentences"]] == ["Merhaba!"]


def test_run_records_failed_sentence_without_dropping_turn(monkeypatch, tmp_path):
    """Tek cumlenin TTS'i patlarsa tur tumuyle dusmez; hangi cumle oldugu kaydedilir."""
    def fake_deltas(*a, **k):
        yield ("first", "content")
        yield ("content", "Birinci cumle. Ikinci cumle.")

    def boom(*a, **k):
        raise RuntimeError("TTS basarisiz: olmadi")

    monkeypatch.setattr(ls, "iter_deltas", fake_deltas)
    monkeypatch.setattr(ls, "synth", boom)
    out = ls.run("selam", "http://x", "http://y", str(tmp_path), prefix="f_", play=False)

    assert out["ok"] is False                      # hicbir ses uretilemedi
    assert [f["index"] for f in out["failed_sentences"]] == [1, 2]
    assert out["failed_sentences"][0]["text"] == "Birinci cumle."
