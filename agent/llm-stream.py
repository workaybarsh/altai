"""llm-stream.py - STREAMING turn: llama-server SSE -> sentence by sentence -> TTS server.

Goal: instead of waiting for the WHOLE LLM answer, send each sentence to TTS as soon
as it forms and play the audio in order (in the background). That way "first audio"
latency = ASR + first token + first sentence + first sentence TTS; the rest of the LLM
output and the synthesis of the remaining sentences happen WHILE the first audio is
PLAYING (pipeline principle #7).

Input: text (the user message for the LLM). Output: --json-out summary (with timestamps)
+ generated WAVs (`--out-dir`/`--prefix`).

No dependencies (stdlib). TTS needs a persistent server (`tts-tools.py --serve`).

Example:
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

# The Windows console may be cp1254; emoji/TR characters must not break print
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SYSTEM_TR = (
    "Sen Altai'sın: tamamen yerel çalışan, Türkçe konuşan bir sesli asistansın. "
    "Yanıtların hoparlörden sesli okunacak. Bu yüzden:\n"
    "- En fazla 2 cümle, yaklaşık 25 kelime yaz.\n"
    "- Konuşma dilinde, doğal ve akıcı ol; yazı dili kalıpları kullanma.\n"
    "- Madde işareti, başlık, emoji, kod, parantez, tırnak ve markdown kullanma.\n"
    "- Sayıları ve kısaltmaları yazıyla söyle (örnek: '3' değil 'üç', 'vb.' değil 've benzeri').\n"
    "- 'Elbette', 'Tabii ki', 'Harika soru' gibi gereksiz girişler yapma; doğrudan yanıtla.\n"
    "- Emin değilsen tek cümlelik kısa bir netleştirme sorusu sor.\n"
    "- Kullanıcı hangi dilde konuşursa o dilde yanıt ver."
)

SYSTEM_EN = (
    "You are Altai, a fully local voice assistant. Your replies are read aloud through a "
    "speaker, so:\n"
    "- Use at most 2 sentences, about 25 words.\n"
    "- Write in spoken language, natural and fluent; avoid written-style phrasing.\n"
    "- Do not use bullets, headings, emoji, code, parentheses, quotes or markdown.\n"
    "- Spell out numbers and abbreviations (say 'three', not '3').\n"
    "- No filler openers such as 'Sure' or 'Great question'; answer directly.\n"
    "- If unsure, ask one short clarifying question.\n"
    "- Reply in the language the user speaks."
)

# Retryable (transient) network errors: Windows loopback RST, dropped connection,
# half-read body. HTTP errors (4xx/5xx) are NOT listed here: those are request rejections.
TRANSIENT = (urllib.error.URLError, ConnectionError, OSError, http.client.HTTPException)


def _post_json(url, payload, timeout=300):
    """UTF-8 JSON POST; returns the response as a dict."""
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

# Sentence end: . ! ? … followed by whitespace/end of line
_BOUNDARY = re.compile(r"[.!?\u2026](\s|$)")
# Short "rough" split: comma/semicolon is accepted too (start long sentences early)
_SOFT = re.compile(r"[,;:](\s|$)")


class SentenceBuffer:
    """Splits the token stream into sentences (incrementally).

    - Hard end: `.!?…` + whitespace/end.
    - If `force_chars` is exceeded, force a split at the last space (do not hold back a long sentence).
    - If `soft_chars` is exceeded and there is a comma/semicolon, split there (optional).
    - A piece shorter than `min_chars` is not sent on its own (it merges with the next one).
    """

    def __init__(self, min_chars=2, force_chars=180, soft_chars=0, first_chars=0):
        self.buf = ""
        self.min_chars = min_chars
        self.force_chars = force_chars
        self.soft_chars = soft_chars
        self.first_chars = first_chars
        self._first_done = False

    def feed(self, text):
        """Appends the incoming chunk; returns COMPLETED sentences (0+)."""
        self.buf += text or ""
        out = []
        while True:
            s = self._pop(False)
            if s is None:
                break
            out.append(s)
        return out

    def flush(self):
        """Stream ended: returns the remaining buffer (if any) as a single sentence."""
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

        # First chunk: emit early at a comma/space so audio starts sooner (chunked streaming).
        if (not self._first_done and self.first_chars and not final
                and len(buf) >= self.first_chars):
            window = buf[: self.first_chars + 20]
            cut = None
            for mm in _SOFT.finditer(window):
                if mm.end() >= self.min_chars:
                    cut = mm.end()
                    break
            if cut is None:
                sp = window.rfind(" ")
                if sp >= self.min_chars:
                    cut = sp + 1
            if cut is not None:
                piece = buf[:cut].strip()
                if len(piece) >= self.min_chars:
                    self.buf = buf[cut:]
                    self._first_done = True
                    return piece

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
        self._first_done = True
        if len(piece) < self.min_chars:
            # very short piece: merge it with the next incoming text
            self.buf = piece + " " + self.buf if piece else self.buf
            if final:
                self.buf = self.buf.strip()
                if self.buf:
                    p, self.buf = self.buf, ""
                    return p
            return None
        return piece


def is_speakable(text):
    """With no letters/digits (emoji/symbol-only) it is not worth sending to TTS."""
    return any(ch.isalnum() for ch in (text or ""))


def _event(name, **kw):
    """Appends a wall-clock event (JSON line) when ALTAI_EVENTS is set (used by measure-turn)."""
    path = os.environ.get("ALTAI_EVENTS")
    if not path:
        return
    rec = {"event": name, "ts": time.time()}
    rec.update(kw)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_MARKS = re.compile(r"[*_`~]")
_MD_PREFIX = re.compile(r"^\s{0,3}(?:#{1,6}\s+|>\s?|[-+]\s+)")


def strip_markdown(text):
    """Removes markdown noise (emphasis, code ticks, links, headings) before TTS.

    The LLM sometimes answers with `**bold**` or a bullet list; a voice assistant must
    read the words, not the markup.
    """
    t = _MD_LINK.sub(r"\1", text or "")
    t = _MD_MARKS.sub("", t)
    t = _MD_PREFIX.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def iter_deltas(server, messages, max_tokens=1024, think=True, temperature=0.7,
                timeout=300):
    """Yields the llama-server SSE stream as (kind, text).

    kind: 'content' | 'reasoning'. When the first chunk arrives, a 'first' event is
    yielded as well: ('first', 'content'|'reasoning').
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
    """Sends a single sentence to the TTS server; returns the result dict (out, audio_seconds...).

    Windows loopback occasionally throws a socket reset (WinError 10054 / IncompleteRead);
    synthesis is reproducible, so it is attempted `attempts` times. An HTTP error
    (e.g. 400: bad input) is **not retried** - the request has already been rejected.
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
            print(f"[warn] TTS connection dropped ({type(exc).__name__}); "
                  f"retrying ({i + 1}/{attempts})", file=sys.stderr)
    results = (data or {}).get("results") or []
    if not results or not results[0].get("ok"):
        err = (results[0].get("error") if results else (data or {}).get("error")) or "unknown error"
        raise RuntimeError(f"TTS failed: {err}")
    res = results[0]
    res["client_attempts"] = i
    return res


class Player:
    """Plays WAVs in the background (winsound); generation continues WHILE the first audio is PLAYING."""

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
        except Exception as exc:  # pragma: no cover - non-Windows
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
        max_tokens=1024, system=None, play=False, force_chars=180,
        soft_chars=0, first_chars=0, timeout=300, log=None):
    """Streaming turn: LLM stream -> sentences -> TTS -> (optional) playback. Returns a summary."""
    log = log or (lambda *a: None)
    system = system or (SYSTEM_EN if (lang or "").lower().startswith("en") else SYSTEM_TR)
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.perf_counter()
    _event("turn_start")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
    sb = SentenceBuffer(force_chars=force_chars, soft_chars=soft_chars, first_chars=first_chars)
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
        emitted += 1                       # a failed sentence also consumes a number (so names do not collide)
        idx = emitted
        sentence = strip_markdown(sentence)
        if not is_speakable(sentence):
            log(f"  [{idx}] (skipped: no letters/digits) {sentence!r}")
            return
        t_tts = time.perf_counter()
        try:
            res = synth(tts_server, sentence, out_dir, f"{prefix}{idx}_", lang=lang,
                        timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - a single sentence must not drop the turn
            failed.append({"index": idx, "text": sentence,
                           "error": f"{type(exc).__name__}: {exc}"})
            log(f"  [{idx}] TTS FAILED: {type(exc).__name__}: {exc}")
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
            f"{res.get('audio_seconds')}s audio  {sentence!r}")
        player.play(res.get("out"))
        _event("speak", index=idx, audio=res.get("audio_seconds"))

    try:
        try:
            for kind, txt in iter_deltas(server, messages, max_tokens=max_tokens, think=think,
                                         timeout=timeout):
                now = time.perf_counter()
                if kind == "first":
                    first_token, first_token_kind = now, txt
                    log(f"[LLM] first chunk ({txt}) +{now - t0:.2f}s")
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
            # Connection dropped mid-stream: continue with the sentences already obtained
            # (the user has heard something already); reported as `stream_error` in the summary.
            stream_error = f"{type(exc).__name__}: {exc}"
            llm_done = time.perf_counter()
            log(f"[LLM] stream dropped ({stream_error}); continuing with the sentences at hand")
        for s in sb.flush():
            emit(s, llm_done if llm_done else time.perf_counter())
    finally:
        if play:
            player.close()

    answer = "".join(answer_parts).strip()
    done = time.perf_counter()
    _event("turn_end")
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
        summary["error"] = "could not produce an answer (empty or reasoning only)"
    return summary


def _json(payload, path):
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Streaming LLM -> sentence -> TTS turn")
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--server", default="http://127.0.0.1:8080")
    ap.add_argument("--tts-server", required=True)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--system", default=None,
                    help="system prompt (default: built-in TR/EN prompt chosen by --lang)")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--out-dir", default="logs/pipeline-stream")
    ap.add_argument("--prefix", default="s_")
    ap.add_argument("--force-chars", type=int, default=180)
    ap.add_argument("--soft-chars", type=int, default=0,
                    help="also split long sentences at a comma beyond this length (0 = sentence-only mode)")
    ap.add_argument("--first-chars", type=int, default=0,
                    help="cut the FIRST chunk early at a comma/space (chunked streaming; 0 = off)")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--json-out")
    args = ap.parse_args(argv)

    text = args.text
    if args.text_file:
        with open(args.text_file, encoding="utf-8") as f:
            text = f.read().strip()
    if not text:
        _json({"ok": False, "error": "no text (--text/--text-file)"}, args.json_out)
        return 2

    try:
        summary = run(text, args.server, args.tts_server, args.out_dir, prefix=args.prefix,
                      lang=args.lang, think=not args.no_think, max_tokens=args.max_tokens,
                      system=args.system, play=args.play, force_chars=args.force_chars,
                      soft_chars=args.soft_chars, first_chars=args.first_chars,
                      timeout=args.timeout,
                      log=lambda s: print(s, file=sys.stderr))
    except urllib.error.URLError as exc:
        _json({"ok": False, "error": f"server unreachable: {exc}"}, args.json_out)
        return 3
    except Exception as exc:  # noqa: BLE001
        _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, args.json_out)
        return 1
    _json(summary, args.json_out)
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
