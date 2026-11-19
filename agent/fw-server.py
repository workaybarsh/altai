"""fw-server.py - persistent faster-whisper (CTranslate2) STT server for Altai.

Why: whisper.cpp on CPU takes ~10 s for a 7 s Turkish utterance; the same model on the
GPU through CTranslate2 takes ~0.27 s (RTF 0.04). This server keeps the model resident,
so a turn pays only the inference cost.

Endpoints:
  GET  /health                     -> {"ok": true, "model": ..., "device": ...}
  POST /transcribe?lang=tr         -> body: 16 kHz mono 16-bit WAV bytes
                                      {"ok": true, "text": ..., "audio_seconds": ...}

Usage:
  python agent/fw-server.py --model large-v3-turbo --device cuda --compute int8_float16 --port 8083

Notes:
- CTranslate2 needs cuBLAS/cuDNN DLLs on PATH; when they come from the `nvidia-*` wheels the
  paths are added automatically below.
- Text output is JSON, UTF-8.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import site
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

SAMPLE_RATE = 16000


def _add_cuda_dlls():
    """Adds the DLL folders of the nvidia-* wheels to the process search path."""
    candidates = []
    for base in {*site.getsitepackages(), site.getusersitepackages()}:
        for sub in (("nvidia", "cublas", "bin"), ("nvidia", "cudnn", "bin"),
                    ("nvidia", "cuda_nvrtc", "bin")):
            candidates.append(os.path.join(base, *sub))
    for d in candidates:
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(d)
            except (AttributeError, OSError):
                pass


def decode_wav(raw: bytes):
    """Returns (float32 mono samples, sample_rate) from a WAV byte string."""
    with wave.open(io.BytesIO(raw), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        width = w.getsampwidth()
        data = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit PCM, got {width * 8}-bit")
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != SAMPLE_RATE:
        # linear resampling is enough here: whisper resamples internally as well
        n = int(round(len(audio) * SAMPLE_RATE / sr))
        idx = np.linspace(0, len(audio) - 1, n)
        audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
    return audio, sr


class State:
    model = None
    model_name = ""
    device = ""
    compute = ""
    lock = threading.Lock()


def transcribe(audio, language):
    with State.lock:
        segments, _info = State.model.transcribe(
            audio, language=language or "tr", beam_size=5, vad_filter=False)
        return "".join(s.text for s in segments).strip()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"ok": State.model is not None, "model": State.model_name,
                             "device": State.device, "compute": State.compute})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        url = urlparse(self.path)
        if url.path != "/transcribe":
            self._json(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._json(400, {"ok": False, "error": "empty body"})
            return
        raw = self.rfile.read(length)
        lang = (parse_qs(url.query).get("lang") or ["tr"])[0]
        try:
            audio, _sr = decode_wav(raw)
        except Exception as exc:  # noqa: BLE001 - report, do not crash the server
            self._json(400, {"ok": False, "error": f"bad wav: {exc}"})
            return
        t0 = time.perf_counter()
        try:
            text = transcribe(audio, lang)
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        dt = time.perf_counter() - t0
        self._json(200, {"ok": True, "text": text, "language": lang,
                         "audio_seconds": round(len(audio) / SAMPLE_RATE, 3),
                         "infer_seconds": round(dt, 4)})

    def log_message(self, fmt, *args):  # keep the console clean
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Persistent faster-whisper STT server")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--compute", default="int8_float16",
                    help="float16 / int8_float16 / int8 / float32")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8083)
    args = ap.parse_args()

    _add_cuda_dlls()
    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    print(f"loading {args.model} on {args.device} ({args.compute})...", flush=True)
    State.model = WhisperModel(args.model, device=args.device, compute_type=args.compute)
    State.model_name = args.model
    State.device = args.device
    State.compute = args.compute
    print(f"model loaded in {time.perf_counter() - t0:.1f} s", flush=True)

    # Warm-up: the first transcribe pays kernel/algorithm selection (measured up to ~28 s).
    t1 = time.perf_counter()
    try:
        transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), "tr")
        print(f"warmup {time.perf_counter() - t1:.2f} s", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"warmup skipped: {type(exc).__name__}: {exc}", flush=True)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"READY: http://{args.host}:{args.port} (POST /transcribe)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
