"""Verifies the pure (offline) behaviour of tts-tools.py."""
import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("tts_tools", os.path.join(ROOT, "agent", "tts-tools.py"))
tts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tts)


def test_empty_text_returns_error(tmp_path, capsys):
    out = tmp_path / "x.wav"
    code = tts.main(["--backend", "sapi", "--text", "   ", "--out", str(out)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False


def test_missing_piper_reports_error(tmp_path, capsys):
    code = tts.main(["--backend", "piper", "--text", "merhaba", "--out", str(tmp_path / "a.wav"),
                     "--piper", "kesinlikle-olmayan-piper-x"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["ok"] is False
    assert "piper" in payload["error"].lower()


def test_sapi_synthesizes_on_windows(tmp_path, capsys):
    if os.name != "nt":
        import pytest
        pytest.skip("SAPI is Windows only")
    out = tmp_path / "sapi.wav"
    code = tts.main(["--backend", "sapi", "--text", "Merhaba dunya", "--out", str(out)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["ok"] is True
    assert os.path.exists(out)
    assert payload["audio_seconds"] > 0


def test_voxcpm_missing_dependency_reports_error(tmp_path, capsys):
    """If voxcpm is not installed, returns ok=false honestly (does not trigger a heavy model download)."""
    import pytest
    try:
        import voxcpm  # noqa: F401
    except Exception:
        pass
    else:
        pytest.skip("voxcpm is installed; skipped to avoid triggering a heavy model load")
    out = tmp_path / "v.wav"
    code = tts.main(["--backend", "voxcpm", "--text", "merhaba", "--out", str(out)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["ok"] is False
    assert payload["backend"] == "voxcpm"


def test_tr_lower_is_turkish_aware():
    assert tts.tr_lower("İSTANBUL IĞDIR") == "istanbul ığdır"


def test_tr_respell_maps_s_to_sh():
    assert tts.tr_respell("Çalışan şair, şaşkın şarkı") == "Çalıshan shair, shashkın sharkı"


def test_tr_softg_turkish_rules():
    # between two vowels -> 'y'
    assert tts.tr_softg("değil") == "deyil"
    assert tts.tr_softg("ağaç") == "ayaç"
    assert tts.tr_softg("kağıt") == "kayıt"
    # after a vowel, before a consonant/finally -> the previous vowel is lengthened (in Turkish ğ always follows a vowel)
    assert tts.tr_softg("dağ") == "daa"
    assert tts.tr_softg("yağmur") == "yaamur"
    assert tts.tr_softg("öğretmen") == "ööretmen"
    assert tts.tr_softg("mağdur") == "maadur"
    assert tts.tr_softg("iğne") == "iine"
    # after a consonant (rare/loanword) -> 'g'
    assert tts.tr_softg("xğx") == "xgx"


def test_tr_softg_leaves_other_text_alone():
    assert tts.tr_softg("merhaba dünya") == "merhaba dünya"
    assert tts.tr_respell("Harika Aybars!") == "Harika Aybars!"


def test_tr_respell_fixes_the_broken_sentence():
    # The example complained about by ear: 'çalıştığı' came out as 'çalıştı ki'.
    src = "Tam yerel çalıştığı için cevaplarım hem hızlı hem de gizli."
    assert tts.tr_respell(src) == "Tam yerel çalıshtıyı için cevaplarım hem hızlı hem de gizli."


def test_tr_respell_softg_can_be_disabled():
    """A/B and rollback: softg=False -> old behaviour ('ş'->'sh' stays, 'ğ' is left alone)."""
    out = tts.tr_respell("değil dağ çalıştığı", softg=False)
    assert out == "değil dağ çalı" + "sh" + "tığı"   # 'ş' -> s+h, 'ğ' untouched
    assert tts.tr_respell("değil dağ", softg=True) == "deyil daa"


def test_install_tr_tokenizer_fix_keeps_precomposed():
    import unicodedata

    class FakeTok:
        def preprocess_text(self, raw_text, language_id=None, lowercase=True, nfkd_normalize=True):
            t = raw_text.lower() if lowercase else raw_text
            return unicodedata.normalize("NFKD", t) if nfkd_normalize else t

    tok = tts.install_tr_tokenizer_fix(FakeTok())
    tr = tok.preprocess_text("ŞÜĞÖÇ IĞDIR", language_id="tr")
    assert "ş" in tr and "ü" in tr and "ı" in tr          # diacritics are preserved
    assert "\u0308" not in tr and "\u0327" not in tr      # does not decompose under NFKD
    en = tok.preprocess_text("Ş", language_id="en")       # non-tr: original NFKD
    assert "\u0327" in en


def test_synth_chatterbox_mtl_sets_language_id(monkeypatch, tmp_path):
    """Regression: `uses_mtl` must be defined; otherwise the chatterbox path would raise NameError."""
    import sys
    import types

    fake_torch = types.ModuleType("torch")
    fake_torch.manual_seed = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    saved = {}
    monkeypatch.setattr(tts, "_save_wav",
                        lambda wav, path, sr: saved.update(path=path, sr=sr) or "stub")

    class FakeTok:
        def preprocess_text(self, t, language_id=None, lowercase=True, nfkd_normalize=True):
            return t

    class FakeWav:
        shape = (1, 24000)

    class FakeModel:
        sr = 24000
        tokenizer = FakeTok()

        def generate(self, text, **kw):
            return FakeWav()

    out = tmp_path / "a.wav"
    res = tts.synth_chatterbox("Çalışan şair", str(out), lang="tr", model=FakeModel())
    assert res["language_id"] == "tr"          # the MTL path was chosen
    assert res["t3_model"] == "v3"
    assert saved["path"] == str(out)


# ---------------------------------------------------------------- long-tail guard

def _stub_chatterbox(monkeypatch, durations):
    """Stubs Chatterbox: returns `durations` in order, _save_wav writes a real file."""
    import sys
    import types

    fake_torch = types.ModuleType("torch")
    fake_torch.manual_seed = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    saved = {}

    def fake_save(wav, path, sr):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"RIFF")
        saved[path] = round(wav.shape[-1] / sr, 3)
        return "stub"

    monkeypatch.setattr(tts, "_save_wav", fake_save)

    class FakeTok:
        def preprocess_text(self, t, language_id=None, lowercase=True, nfkd_normalize=True):
            return t

    calls = {"n": 0}

    class FakeWav:
        def __init__(self, secs):
            self.shape = (1, int(24000 * secs))

    class FakeModel:
        sr = 24000
        tokenizer = FakeTok()

        def generate(self, text, **kw):
            i = min(calls["n"], len(durations) - 1)
            calls["n"] += 1
            return FakeWav(durations[i])

    return FakeModel(), calls, saved


def test_expected_audio_and_guard_limit():
    assert tts.expected_audio_seconds("") == 0.0
    assert tts.expected_audio_seconds("Merhaba!") == pytest.approx(0.5)   # 7 letters / 14
    # for "Merhaba!" the limit = max(3*0.5 ; 0.5+2.0) = 2.5 s
    assert tts.audio_guard_limit("Merhaba!") == pytest.approx(2.5)
    # the limit grows for a long sentence (avoid false positives)
    assert tts.audio_guard_limit("Bugün size nasıl yardımcı olabilirim?") > 4.0


def test_synth_chatterbox_retries_when_audio_too_long(monkeypatch, tmp_path):
    """A 9.6 s 'Merhaba!' (the tts_batch.json case) -> regenerate, keep the shorter one."""
    model, calls, saved = _stub_chatterbox(monkeypatch, [9.6, 0.9])
    out = tmp_path / "m.wav"
    res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model)

    assert calls["n"] == 2                      # generated once more
    assert res["retried"] is True
    assert res["long_tail_guard"] is True
    assert res["audio_seconds"] == pytest.approx(0.9, abs=0.01)   # the shorter one was kept
    assert res["first_audio_seconds"] == pytest.approx(9.6, abs=0.01)
    assert os.path.exists(out)                  # the short output was moved to the real path
    assert not os.path.exists(str(out) + ".retry.wav")
    assert res["out"] == str(out)               # ⚠️ regression: the path must not drift to .retry.wav
    assert res["guard_extra_seconds"] == res["tts_seconds"]   # compensation = the retry generation


def test_synth_chatterbox_keeps_first_when_retry_longer(monkeypatch, tmp_path):
    model, calls, saved = _stub_chatterbox(monkeypatch, [9.6, 12.0])
    out = tmp_path / "m2.wav"
    res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model)

    assert calls["n"] == 2
    assert res["retried"] is True
    assert res["first_audio_seconds"] == pytest.approx(9.6, abs=0.01)   # first attempt
    assert res["audio_seconds"] == pytest.approx(9.6, abs=0.01)   # the first one is shorter
    assert res["retry_audio_seconds"] == pytest.approx(12.0, abs=0.01)
    assert not os.path.exists(str(out) + ".retry.wav")            # temporary file deleted
    assert res["out"] == str(out) and os.path.exists(res["out"])  # the first output is in place
    assert res["guard_extra_seconds"] >= 0                        # compensation cost is recorded


def test_synth_chatterbox_retry_result_points_to_real_file(monkeypatch, tmp_path):
    """In every case `out` must point to a file that EXISTS on disk (the pipeline uses Test-Path)."""
    durations = {"a": ([9.6, 0.9], True), "b": ([9.6, 12.0], True), "c": ([1.0], False)}
    for name, (durs, should_retry) in durations.items():
        model, calls, saved = _stub_chatterbox(monkeypatch, durs)
        out = tmp_path / f"{name}.wav"
        res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model)
        assert bool(res.get("retried", False)) is should_retry
        assert res["out"] == str(out)
        assert os.path.exists(res["out"])           # NOT the stale .retry.wav path


def test_synth_chatterbox_no_retry_when_normal(monkeypatch, tmp_path):
    model, calls, saved = _stub_chatterbox(monkeypatch, [1.2])
    out = tmp_path / "n.wav"
    res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model)

    assert calls["n"] == 1
    assert "retried" not in res
    assert res["audio_seconds"] == pytest.approx(1.2, abs=0.01)


def test_synth_chatterbox_guard_can_be_disabled(monkeypatch, tmp_path):
    model, calls, saved = _stub_chatterbox(monkeypatch, [9.6])
    out = tmp_path / "g.wav"
    res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model, guard=False)

    assert calls["n"] == 1
    assert "retried" not in res
    assert res["audio_seconds"] == pytest.approx(9.6, abs=0.01)


def test_server_texts_normalizes_single_and_list():
    assert tts.server_texts({"texts": "tek"}) == ["tek"]
    assert tts.server_texts({"text": "tek"}) == ["tek"]
    assert tts.server_texts({"texts": ["a", " b ", ""]}) == ["a", "b"]
    assert tts.server_texts({}) == []
    # a non-text item is rejected (malformed input can poison the CUDA context)
    import pytest as _pytest
    with _pytest.raises(ValueError):
        tts.server_texts({"texts": [{"value": "x"}]})


def test_ensure_speakable_rejects_symbol_only():
    """Symbol-only/emoji input NEVER reaches generation (Chatterbox used to crash there)."""
    assert tts.ensure_speakable("Merhaba") == "Merhaba"
    assert tts.ensure_speakable("3 elma") == "3 elma"
    for bad in ("", "   ", "???", "!!! ...", "\U0001f60a"):
        with pytest.raises(ValueError):
            tts.ensure_speakable(bad)


def test_tts_server_health_and_tts(monkeypatch, tmp_path):
    """Persistent server: /health and /tts work (model functions stubbed; no GPU needed)."""
    import threading
    import types

    monkeypatch.setattr(tts, "load_chatterbox", lambda **kw: object())

    def fake_synth(text, out_wav, *a, **k):
        os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
        with open(out_wav, "wb") as f:
            f.write(b"RIFF")
        return {"out": out_wav, "audio_seconds": 1.0, "tts_seconds": 0.5, "text": text}

    monkeypatch.setattr(tts, "synth_chatterbox", fake_synth)

    args = types.SimpleNamespace(backend="chatterbox", lang="tr", device="cpu", t3_model="v3",
                                 exaggeration=0.5, cfg=0.5, seed=None, chatterbox_tr_raw=False,
                                 voice_prompt=None, host="127.0.0.1", port=0)
    srv = tts.create_server(args)
    srv.ensure_model()
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        health = _post_json(f"http://127.0.0.1:{port}/health", None)
        assert health["ok"] is True
        assert health["loaded"] is True

        body = json.dumps({"texts": ["bir", "iki"], "out_dir": str(tmp_path), "prefix": "s_"}).encode()
        out = _post_json(f"http://127.0.0.1:{port}/tts", body)

        # Symbol-only item: item-level error (HTTP 200, ok=True because the other one was generated);
        # this way malformed input neither fails the batch nor poisons the CUDA context.
        body2 = json.dumps({"texts": ["tamam", "???"], "out_dir": str(tmp_path),
                            "prefix": "x_"}).encode()
        out2 = _post_json(f"http://127.0.0.1:{port}/tts", body2)
    finally:
        srv.shutdown()
        srv.server_close()

    assert out["ok"] is True
    assert out["count"] == 2 and out["failed"] == 0
    assert os.path.exists(tmp_path / "s_1.wav")
    assert os.path.exists(tmp_path / "s_2.wav")

    assert out2["ok"] is True and out2["failed"] == 1
    bad = [r for r in out2["results"] if not r["ok"]]
    assert len(bad) == 1 and bad[0]["index"] == 2
    assert "does not contain any valid letters" in bad[0]["error"]
    assert not os.path.exists(tmp_path / "x_2.wav")   # not generated


def test_json_handles_emoji_without_crashing(tmp_path):
    """Emoji in the LLM output must not blow up print on the console encoding (it used to drop batch mode)."""
    out = tmp_path / "j.json"
    tts._json({"ok": True, "text": "merhaba 😊 dünya"}, str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["text"] == "merhaba 😊 dünya"


def test_batch_mode_rejects_non_chatterbox(tmp_path, capsys):
    bf = tmp_path / "b.txt"
    bf.write_text("bir\niki\n", encoding="utf-8")
    code = tts.main(["--backend", "piper", "--batch-file", str(bf),
                     "--out-prefix", str(tmp_path / "o_"), "--piper", "yok"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["ok"] is False
    assert "chatterbox" in payload["error"].lower()


def test_batch_missing_file_reports_error(tmp_path, capsys):
    code = tts.main(["--backend", "chatterbox", "--batch-file", str(tmp_path / "yok.txt"),
                     "--out-prefix", str(tmp_path / "o_")])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert "not found" in payload["error"]


def test_batch_needs_out_prefix_or_out(tmp_path, capsys):
    bf = tmp_path / "b.txt"
    bf.write_text("bir\n", encoding="utf-8")
    code = tts.main(["--backend", "chatterbox", "--batch-file", str(bf)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert "out-prefix" in payload["error"]


def _post_json(url, data):
    # Measured on Windows loopback: ~30% of consecutive requests fail with WinError 10054 (RST)
    # (same with a minimal stdlib http.server + raw socket → environment-related, not server code).
    # Hence generous retries in tests; a repeated request goes out with the same parameters (idempotent).
    import time
    import urllib.request
    last = None
    for attempt in range(10):
        try:
            req = urllib.request.Request(url, data=data, method="POST",
                                         headers={"Content-Type": "application/json"}) if data else url
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (ConnectionError, OSError) as exc:
            last = exc
            time.sleep(0.1 * (attempt + 1))
    raise last


def test_tts_server_piper_dispatch(monkeypatch, tmp_path):
    """piper server mode: no model is loaded into memory; each request goes to synth_piper (no GPU needed)."""
    import threading
    import types

    exe = tmp_path / "piper.exe"
    exe.write_bytes(b"x")
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"y")

    calls = []

    def fake_piper(text, out_wav, model_path=None, piper_exe=None):
        calls.append((text, out_wav, model_path, piper_exe))
        os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
        with open(out_wav, "wb") as f:
            f.write(b"RIFF")
        return {"out": out_wav, "audio_seconds": 1.0, "tts_seconds": 0.1, "rtf": 0.1}

    monkeypatch.setattr(tts, "synth_piper", fake_piper)

    args = types.SimpleNamespace(backend="piper", lang="tr", device="cpu", t3_model="v3",
                                 exaggeration=0.5, cfg=0.5, seed=None, chatterbox_tr_raw=False,
                                 voice_prompt=None, host="127.0.0.1", port=0,
                                 piper=str(exe), piper_model=str(model))
    srv = tts.create_server(args)
    srv.ensure_model()          # no load for piper, validation only
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        health = _post_json(f"http://127.0.0.1:{port}/health", None)
        body = json.dumps({"texts": ["merhaba", "dunya"], "out_dir": str(tmp_path),
                           "prefix": "p_"}).encode()
        out = _post_json(f"http://127.0.0.1:{port}/tts", body)
    finally:
        srv.shutdown()
        srv.server_close()

    assert health["ok"] is True and health["backend"] == "piper"
    assert health["loaded"] is True and health["load_seconds"] == 0.0
    assert out["ok"] is True and out["count"] == 2 and out["failed"] == 0
    # ⚠️ If a reset happens on Windows loopback, _post_json resends the request and the same batch
    # is synthesised twice; so we look at the **first-seen order**, not the raw sequence.
    texts = []
    for c in calls:
        if c[0] not in texts:
            texts.append(c[0])
    assert texts == ["merhaba", "dunya"]
    assert calls[0][2] == str(model) and calls[0][3] == str(exe)
    assert os.path.exists(tmp_path / "p_1.wav")


def test_tts_server_piper_missing_model_raises(tmp_path):
    """piper server mode: a missing binary/voice file gives an honest error (no silent failure)."""
    import types

    args = types.SimpleNamespace(backend="piper", lang="tr", device="cpu", t3_model="v3",
                                 exaggeration=0.5, cfg=0.5, seed=None, chatterbox_tr_raw=False,
                                 voice_prompt=None, host="127.0.0.1", port=0,
                                 piper=str(tmp_path / "yok.exe"),
                                 piper_model=str(tmp_path / "yok.onnx"))
    srv = tts.create_server(args)
    with pytest.raises(RuntimeError):
        srv.ensure_model()


def test_tts_server_passes_respell_switches_per_request(monkeypatch, tmp_path):
    """Per-request A/B wiring: 'softg'/'tr_raw' reach synth_chatterbox correctly.

    {'softg': false} -> only the 'ğ' respell is off (respell=True, softg=False)
    {'tr_raw': true} -> all TR corrections are off (respell=False)
    """
    import threading
    import types

    monkeypatch.setattr(tts, "load_chatterbox", lambda **kw: object())
    seen = []

    def fake_synth(text, out_wav, *a, **k):
        seen.append({"prefix": os.path.basename(out_wav), "text": text,
                     "tr_fix": a[7], "respell": a[8], "softg": k.get("softg")})
        os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
        with open(out_wav, "wb") as f:
            f.write(b"RIFF")
        return {"out": out_wav, "audio_seconds": 1.0, "tts_seconds": 0.1, "text": text}

    monkeypatch.setattr(tts, "synth_chatterbox", fake_synth)

    args = types.SimpleNamespace(backend="chatterbox", lang="tr", device="cpu", t3_model="v3",
                                 exaggeration=0.5, cfg=0.5, seed=None, chatterbox_tr_raw=False,
                                 chatterbox_no_softg=False, no_guard=True,
                                 voice_prompt=None, host="127.0.0.1", port=0)
    srv = tts.create_server(args)
    srv.ensure_model()
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for i, extra in enumerate(({"softg": False}, {"tr_raw": True}, {}), 1):
            body = dict({"texts": ["değil"], "out_dir": str(tmp_path), "prefix": f"r{i}_"}, **extra)
            _post_json(f"http://127.0.0.1:{port}/tts", json.dumps(body).encode())
    finally:
        srv.shutdown()
        srv.server_close()

    def last_call(prefix):
        # ⚠️ On a Windows loopback reset, _post_json resends the request and the same request is
        # synthesised twice; so we verify with the **last** call per request, not by order.
        rows = [s for s in seen if s["prefix"].startswith(prefix)]
        assert rows, f"no synthesis call for the {prefix} request"
        return rows[-1]

    first = last_call("r1_")
    assert first["softg"] is False and first["respell"] is True        # only 'ğ' is off
    second = last_call("r2_")
    assert second["respell"] is False and second["tr_fix"] is False    # tr_raw: everything is off
    third = last_call("r3_")
    assert third["softg"] is True and third["respell"] is True         # default: everything is on
