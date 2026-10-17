"""llm-stream.py - AKISLI tur: llama-server SSE -> cumle cumle -> TTS sunucusu.

Amaç: LLM yanitinin TAMAMINI beklemek yerine, ilk cumle olusur olusmaz TTS'e
gondermek ve sesleri sirayla (arka planda) calmak. Boylece "ilk ses" gecikmesi
= ASR + ilk token + ilk cumle + ilk cumle TTS'i olur; LLM'in kalanini yazmasi ve
diger cumlelerin sentezi ilk ses CALARKEN olur (boru hatti ilkesi #7).

Girdi: metin (LLM'e kullanici mesaji). Cikti: --json-out ozet (zaman damgalariyla)
+ uretilen WAV'lar (`--out-dir`/`--prefix`).

Bagimlilik yok (stdlib). TTS icin kalici sunucu gerekir (`tts-tools.py --serve`).

Ornek:
  python agent/llm-stream.py --text "Merhaba, nasilsin?" --lang tr ^
      --server http://127.0.0.1:8080 --tts-server http://127.0.0.1:8082 ^
      --out-dir logs\\pipeline-stream --play --json-out logs\\pipeline-stream\\s.json
"""
import argparse
import http.client
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request

# Windows konsolu cp1254 olabilir; emoji/TR karakterler print'i patlatmasin
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SYSTEM_TR = "Sen kisa ve dogal Turkce cevap veren bir sesli asistansin."

# Yeniden denenebilir (gecici) ag hatalari: Windows loopback RST, kopan baglanti,
# yarim okunan govde. HTTP hatalari (4xx/5xx) BURADA DEGIL: onlar istegin reddi.
TRANSIENT = (urllib.error.URLError, ConnectionError, OSError, http.client.HTTPException)


def _post_json(url, payload, timeout=300):
    """UTF-8 JSON POST'u; yaniti sozluk olarak dondurur."""
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

# Cumle sonu: . ! ? … ve ardindan bosluk/satir sonu
_BOUNDARY = re.compile(r"[.!?\u2026](\s|$)")
# Kisa "kaba" bolme: virgul/noktali virgul de kabul (uzun cumleleri erken baslat)
_SOFT = re.compile(r"[,;:](\s|$)")


class SentenceBuffer:
    """Token akisini cumlelere boler (kademeli).

    - Kesin son: `.!?…` + bosluk/son.
    - `force_chars` asilirsa son bosluktan zorla bol (uzun cumleyi bekletme).
    - `soft_chars` asilirsa ve virgul/noktali virgul varsa oradan bol (istege bagli).
    - `min_chars` altindaki parca tek basina gonderilmez (bir sonrakiyle birlesir).
    """

    def __init__(self, min_chars=2, force_chars=180, soft_chars=120):
        self.buf = ""
        self.min_chars = min_chars
        self.force_chars = force_chars
        self.soft_chars = soft_chars

    def feed(self, text):
        """Akisa gelen parcayi ekler; TAMAMLANMIS cumleleri dondurur (0+)."""
        self.buf += text or ""
        out = []
        while True:
            s = self._pop(False)
            if s is None:
                break
            out.append(s)
        return out

    def flush(self):
        """Akis bitti: kalan tamponu (varsa) tek cumle olarak dondurur."""
        out = []
        while True:
            s = self._pop(True)
            if s is None:
                break
            out.append(s)
        return out

    def _pop(self, final):
        buf = self.buf
        if not buf.strip():
            if final:
                self.buf = ""
            return None

        cut = None
        m = _BOUNDARY.search(buf)
        if m:
            cut = m.end()
        elif len(buf) >= self.force_chars:
            sp = buf.rfind(" ", 0, self.force_chars)
            cut = sp + 1 if sp > 0 else None
            if cut is None and final:
                cut = len(buf)
        elif final:
            cut = len(buf)
        elif self.soft_chars and len(buf) >= self.soft_chars:
            m2 = None
            for mm in _SOFT.finditer(buf):
                if mm.end() <= self.soft_chars + 40:
                    m2 = mm
            if m2:
                cut = m2.end()
        if cut is None:
            return None

        piece = buf[:cut].strip()
        self.buf = buf[cut:]
        if len(piece) < self.min_chars:
            # cok kisa parca: bir sonraki akisla birlestir
            self.buf = piece + " " + self.buf if piece else self.buf
            if final:
                self.buf = self.buf.strip()
                if self.buf:
                    p, self.buf = self.buf, ""
                    return p
            return None
        return piece


def is_speakable(text):
    """Harf/rakam yoksa (emoji/sembol-only) TTS'e gondermeye degmez."""
    return any(ch.isalnum() for ch in (text or ""))


def iter_deltas(server, messages, max_tokens=1024, think=True, temperature=0.7,
                timeout=300):
    """llama-server SSE akisini (kind, text) olarak uretir.

    kind: 'content' | 'reasoning'. Ilk parca geldiginde 'first' olayi da uretilir:
    ('first', 'content'|'reasoning').
    """
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": bool(think)},
    }
    req = urllib.request.Request(
        f"{server.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST")
    first = True
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            for kind in ("reasoning", "content"):
                key = "reasoning_content" if kind == "reasoning" else "content"
                txt = delta.get(key)
                if txt:
                    if first:
                        first = False
                        yield ("first", kind)
                    yield (kind, txt)
            if choice.get("finish_reason"):
                yield ("finish", choice["finish_reason"])


def synth(tts_server, text, out_dir, prefix, lang=None, timeout=300, attempts=2):
    """TTS sunucusuna tek cumle gonderir; sonuc sozlugu (out, audio_seconds...) doner.

    Windows loopback'te nadir socket reset'i olusuyor (WinError 10054 / IncompleteRead);
    sentez tekrar uretilebilir oldugu icin `attempts` kez denenir. HTTP hatasi
    (or. 400: bozuk girdi) **tekrar denenmez** - istek zaten reddedilmistir.
    """
    body = {"texts": [text], "out_dir": out_dir, "prefix": prefix}
    if lang:
        body["lang"] = lang
    url = f"{tts_server.rstrip('/')}/tts"
    data = None
    for i in range(1, max(1, attempts) + 1):
        try:
            data = _post_json(url, body, timeout=timeout)
            break
        except urllib.error.HTTPError:
            raise
        except TRANSIENT as exc:
            if i >= max(1, attempts):
                raise
            time.sleep(0.4 * i)
            print(f"[uyari] TTS baglantisi koptu ({type(exc).__name__}); "
                  f"yeniden deneniyor ({i + 1}/{attempts})", file=sys.stderr)
    results = (data or {}).get("results") or []
    if not results or not results[0].get("ok"):
        err = (results[0].get("error") if results else (data or {}).get("error")) or "bilinmeyen hata"
        raise RuntimeError(f"TTS basarisiz: {err}")
    res = results[0]
    res["client_attempts"] = i
    return res


class Player:
    """Arka planda WAV calar (winsound); ilk ses CALARKEN uretim devam eder."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.q = queue.Queue()
        self.thread = None
        self.errors = []
        if enabled:
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def play(self, path):
        if self.enabled:
            self.q.put(path)

    def _loop(self):
        try:
            import winsound
        except Exception as exc:  # pragma: no cover - Windows disi
            self.errors.append(str(exc))
            return
        while True:
            path = self.q.get()
            if path is None:
                return
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME)
            except Exception as exc:  # pragma: no cover
                self.errors.append(f"{type(exc).__name__}: {exc}")

    def close(self):
        if self.enabled and self.thread:
            self.q.put(None)
            self.thread.join(timeout=600)


def run(text, server, tts_server, out_dir, prefix="s_", lang=None, think=True,
        max_tokens=1024, system=SYSTEM_TR, play=False, force_chars=180,
        soft_chars=120, timeout=300, log=None):
    """Akisli tur: LLM akisi -> cumleler -> TTS -> (opsiyonel) oynatma. Ozet doner."""
    log = log or (lambda *a: None)
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.perf_counter()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
    sb = SentenceBuffer(force_chars=force_chars, soft_chars=soft_chars)
    player = Player(enabled=play)

    sentences = []
    failed = []
    answer_parts = []
    first_token = None
    first_token_kind = None
    first_sentence = None
    first_wav = None
    llm_done = None
    finish_reason = None
    reasoning_chars = 0
    stream_error = None
    emitted = 0

    def emit(sentence, at):
        nonlocal first_sentence, first_wav, emitted
        if first_sentence is None:
            first_sentence = at
        emitted += 1                       # basarisiz cumle de numarayi tuketir (ad karismasin)
        idx = emitted
        if not is_speakable(sentence):
            log(f"  [{idx}] (atlandi: harf/rakam yok) {sentence!r}")
            return
        t_tts = time.perf_counter()
        try:
            res = synth(tts_server, sentence, out_dir, f"{prefix}{idx}_", lang=lang,
                        timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - tek cumle turu dusurmesin
            failed.append({"index": idx, "text": sentence,
                           "error": f"{type(exc).__name__}: {exc}"})
            log(f"  [{idx}] TTS BASARISIZ: {type(exc).__name__}: {exc}")
            return
        ready = time.perf_counter()
        if first_wav is None:
            first_wav = ready
        sentences.append({
            "index": idx, "text": sentence, "out": res.get("out"),
            "audio_seconds": res.get("audio_seconds"),
            "tts_seconds": round(ready - t_tts, 3),
            "llm_at": round(at, 3), "ready_at": round(ready - t0, 3),
            "retried": bool(res.get("retried")),
            "client_attempts": res.get("client_attempts", 1),
        })
        log(f"  [{idx}] +{ready - t0:5.1f}s  TTS {ready - t_tts:4.1f}s  "
            f"{res.get('audio_seconds')}s ses  {sentence!r}")
        player.play(res.get("out"))

    try:
        try:
            for kind, txt in iter_deltas(server, messages, max_tokens=max_tokens, think=think,
                                         timeout=timeout):
                now = time.perf_counter()
                if kind == "first":
                    first_token, first_token_kind = now, txt
                    log(f"[LLM] ilk parca ({txt}) +{now - t0:.2f}s")
                elif kind == "reasoning":
                    reasoning_chars += len(txt)
                elif kind == "content":
                    answer_parts.append(txt)
                    for s in sb.feed(txt):
                        emit(s, time.perf_counter())
                elif kind == "finish":
                    finish_reason = txt
            llm_done = time.perf_counter()
        except TRANSIENT as exc:
            # Akis ortasinda kopma: elde edilen cumlelerle devam et (kullanici zaten
            # bir seyler duydu); durum ozette `stream_error` olarak bildirilir.
            stream_error = f"{type(exc).__name__}: {exc}"
            llm_done = time.perf_counter()
            log(f"[LLM] akis koptu ({stream_error}); eldeki cumlelerle devam ediliyor")
        for s in sb.flush():
            emit(s, llm_done if llm_done else time.perf_counter())
    finally:
        if play:
            player.close()

    answer = "".join(answer_parts).strip()
    done = time.perf_counter()
    summary = {
        "ok": bool(sentences),
        "answer": answer,
        "finish_reason": finish_reason,
        "reasoning_chars": reasoning_chars,
        "stream_error": stream_error,
        "first_token_seconds": round(first_token - t0, 3) if first_token else None,
        "first_token_kind": first_token_kind,
        "first_sentence_seconds": round(first_sentence - t0, 3) if first_sentence else None,
        "first_audio_seconds": round(first_wav - t0, 3) if first_wav else None,
        "llm_seconds": round(llm_done - t0, 3) if llm_done else None,
        "total_seconds": round(done - t0, 3),
        "sentences": sentences,
        "failed_sentences": failed,
        "play_errors": player.errors,
    }
    if answer and not sentences:
        summary["error"] = "yanit uretilemedi (bos ya da yalniz dusunme)"
    return summary


def _json(payload, path):
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Akisli LLM -> cumle -> TTS turu")
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--server", default="http://127.0.0.1:8080")
    ap.add_argument("--tts-server", required=True)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--system", default=SYSTEM_TR)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--out-dir", default="logs/pipeline-stream")
    ap.add_argument("--prefix", default="s_")
    ap.add_argument("--force-chars", type=int, default=180)
    ap.add_argument("--soft-chars", type=int, default=120)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--json-out")
    args = ap.parse_args(argv)

    text = args.text
    if args.text_file:
        with open(args.text_file, encoding="utf-8") as f:
            text = f.read().strip()
    if not text:
        _json({"ok": False, "error": "metin yok (--text/--text-file)"}, args.json_out)
        return 2

    try:
        summary = run(text, args.server, args.tts_server, args.out_dir, prefix=args.prefix,
                      lang=args.lang, think=not args.no_think, max_tokens=args.max_tokens,
                      system=args.system, play=args.play, force_chars=args.force_chars,
                      soft_chars=args.soft_chars, timeout=args.timeout,
                      log=lambda s: print(s, file=sys.stderr))
    except urllib.error.URLError as exc:
        _json({"ok": False, "error": f"sunucuya ulasilamadi: {exc}"}, args.json_out)
        return 3
    except Exception as exc:  # noqa: BLE001
        _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, args.json_out)
        return 1
    _json(summary, args.json_out)
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
