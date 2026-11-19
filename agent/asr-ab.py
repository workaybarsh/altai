"""asr-ab.py - A/B two faster-whisper models on the same audio (text + latency).

Example:
  python agent/asr-ab.py --wav logs/tts/sample.wav --model-b altintasutku/whisper-large-v3-turkish-ct2-int8

Prints JSON with, for each model: load_seconds, median inference seconds, RTF and transcript.
Requires the faster-whisper venv (run it with %USERPROFILE%\\fw-venv\\Scripts\\python.exe).
"""

from __future__ import annotations

import argparse
import json
import os
import site
import statistics
import sys
import time
import wave

import numpy as np

# CTranslate2 loads its CUDA libraries from PATH; the nvidia-* wheels keep them in site-packages.
for _base in {*site.getsitepackages(), site.getusersitepackages()}:
    for _sub in (("nvidia", "cublas", "bin"), ("nvidia", "cudnn", "bin"), ("nvidia", "cuda_nvrtc", "bin")):
        _d = os.path.join(_base, *_sub)
        if os.path.isdir(_d):
            os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(_d)
            except (AttributeError, OSError):
                pass

from faster_whisper import WhisperModel


def load_audio(path: str):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        channels = w.getnchannels()
        raw = w.readframes(w.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample_poly
        audio = resample_poly(audio, 16000, sr).astype(np.float32)
    return audio


def benchmark(model_id, audio, device, compute, language, repeat):
    t0 = time.perf_counter()
    model = WhisperModel(model_id, device=device, compute_type=compute)
    load = time.perf_counter() - t0

    def once():
        t = time.perf_counter()
        segments, _info = model.transcribe(audio, language=language, beam_size=5, vad_filter=True)
        text = "".join(s.text for s in segments).strip()
        return time.perf_counter() - t, text

    once()  # warm-up
    times, text = [], ""
    for _ in range(max(1, repeat)):
        dt, text = once()
        times.append(dt)
    seconds = len(audio) / 16000.0
    median = statistics.median(times)
    return {
        "model": model_id,
        "load_seconds": round(load, 2),
        "median_seconds": round(median, 3),
        "rtf": round(median / seconds, 3) if seconds else None,
        "audio_seconds": round(seconds, 3),
        "text": text,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="A/B two faster-whisper models on one WAV")
    ap.add_argument("--wav", required=True)
    ap.add_argument("--model-a", default="large-v3-turbo")
    ap.add_argument("--model-b", required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute", default="int8_float16")
    ap.add_argument("--lang", default="tr")
    ap.add_argument("--repeat", type=int, default=2)
    args = ap.parse_args()

    audio = load_audio(args.wav)
    out = {"text": "", "results": []}
    for model_id in (args.model_a, args.model_b):
        try:
            out["results"].append(benchmark(model_id, audio, args.device, args.compute,
                                            args.lang, args.repeat))
        except Exception as exc:  # noqa: BLE001 - report and continue with the other model
            out["results"].append({"model": model_id, "error": f"{type(exc).__name__}: {exc}"})
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if all("error" not in r for r in out["results"]) else 1


if __name__ == "__main__":
    sys.exit(main())
