#!/usr/bin/env python3
"""asr-tools.py -- whisper.cpp inference tool (Altai, Phase 2 skeleton).

Task:
  1. Converts the audio file (if needed) to 16 kHz mono WAV.
  2. Transcribes it with whisper.cpp (`whisper-cli`).
  3. Returns latency and RTF measurements as JSON.

If the model/binary is missing, it honestly returns `ok=false` (it does not make
things up). The contract is JSON.

Usage:
  python agent/asr-tools.py --wav input.wav --model models/ggml-large-v3-turbo-q5_0.bin
  python agent/asr-tools.py --dir tests/assets --model ... --repeat 10 --out logs/asr.json
  python agent/asr-tools.py --wav input.wav --server-url http://127.0.0.1:8081   # model in memory

Output (stdout, JSON):
  {
    "ok": true,
    "whisper": "...", "model": "...", "language": "tr", "threads": 6, "repeat": 1,
    "results": [
      {"file": "...", "text": "...", "audio_seconds": 4.2, "asr_seconds": 0.31, "rtf": 0.074,
       "load_seconds": 0.52, "encode_seconds": 0.28, "infer_seconds": 0.28}
    ],
    "stats": {"median_asr": 0.31, "p95_asr": 0.35, "mean_rtf": 0.074, "median_infer": 0.28}
  }

Notes:
  - `asr_seconds` = end-to-end wall time (including model load).
  - `infer_seconds` = whisper.cpp encode+decode (EXCLUDING model load) -- so that the
    RTF reads correctly on short audio. The single-shot process reloads the model on
    every call.
  - if `--threads` is not given, the logical core count is used (whisper default is 4).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import wave

DEFAULT_WHISPER = "whisper-cli"
DEFAULT_TMP = os.path.join("logs", "asr-tmp")


# ---------------------------------------------------------------- pure helpers

def audio_seconds(path: str) -> float:
    """Duration of a WAV file in seconds."""
    with wave.open(path, "rb") as w:
        rate = w.getframerate() or 1
        return w.getnframes() / float(rate)


def compute_rtf(asr_seconds: float, audio_sec: float) -> float:
    """Real-time factor = processing time / audio duration."""
    if audio_sec <= 0:
        return float("inf")
    return asr_seconds / audio_sec


def default_threads() -> int:
    """Default thread count = **logical** core count.

    Measured (Ryzen 5 3600, 6C/12T, large-v3-turbo): with q5_0, `-t 12` (10.0 s) <
    `-t 6` (13.1 s) < whisper default `-t 4` (20.9 s, f16). So SMT does help on this
    machine; although the general rule is "physical core", it must be verified by
    measurement (AGENTS pitfall #9). Can be overridden explicitly with `--threads`.
    """
    return max(1, os.cpu_count() or 1)


def parse_whisper_timings(stderr: str) -> dict:
    """Converts whisper.cpp `whisper_print_timings:` lines (ms) to seconds.

    Goal: separate **model loading** from **actual inference**. The single-shot
    process reloads the model on every call; that inflates the RTF on short audio.
    """
    import re

    out = {}
    if not stderr:
        return out
    for key, pat in (("load_seconds", r"load time\s*=\s*([\d.]+)"),
                     ("encode_seconds", r"encode time\s*=\s*([\d.]+)"),
                     ("decode_seconds", r"decode time\s*=\s*([\d.]+)"),
                     ("whisper_total_seconds", r"total time\s*=\s*([\d.]+)")):
        m = re.search(pat, stderr)
        if m:
            out[key] = round(float(m.group(1)) / 1000.0, 4)
    return out


def percentile(values, p: float):
    """Percentile with linear interpolation (p: 0..1). None if empty."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    frac = k - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def build_whisper_command(whisper_exe, model, wav, language="tr", threads=None, extra=None):
    """Builds the whisper.cpp command line (testable, side-effect free)."""
    cmd = [whisper_exe, "-m", model, "-f", wav, "-l", language or "auto", "-nt"]
    if threads:
        cmd += ["-t", str(int(threads))]
    if extra:
        cmd += list(extra)
    return cmd


def find_whisper(explicit: str | None = None):
    """Finds the whisper.cpp binary (given path, PATH, common names)."""
    if explicit:
        if os.path.sep in explicit or (os.altsep and os.altsep in explicit):
            return explicit if os.path.exists(explicit) else None
        return shutil.which(explicit)
    for name in (DEFAULT_WHISPER, "whisper-cli.exe", "main.exe", "whisper"):
        found = shutil.which(name)
        if found:
            return found
    return None


def find_ffmpeg(explicit: str | None = None):
    if explicit:
        if os.path.sep in explicit or (os.altsep and os.altsep in explicit):
            return explicit if os.path.exists(explicit) else None
        return shutil.which(explicit)
    return shutil.which("ffmpeg")


# ---------------------------------------------------------------- audio path

def to_wav_16k_mono(src: str, dst: str, ffmpeg: str = "ffmpeg"):
    """Converts to 16 kHz mono PCM WAV with ffmpeg. Returns (path, error)."""
    exe = find_ffmpeg(ffmpeg)
    if not exe:
        return None, "ffmpeg not found (16 kHz mono conversion is required)"
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    cmd = [exe, "-y", "-i", src, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0 or not os.path.exists(dst):
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-3:])
        return None, f"ffmpeg error: {tail}"
    return dst, None


def prepare_wav(src: str, workdir: str, ffmpeg: str = "ffmpeg"):
    """Leaves the file untouched if it is already 16 kHz mono; otherwise converts it.

    Returns (path, error).
    """
    try:
        with wave.open(src, "rb") as w:
            if w.getframerate() == 16000 and w.getnchannels() == 1:
                return src, None
    except wave.Error:
        pass
    os.makedirs(workdir, exist_ok=True)
    dst = os.path.join(workdir, os.path.splitext(os.path.basename(src))[0] + ".16k.wav")
    return to_wav_16k_mono(src, dst, ffmpeg)


def transcribe_once(whisper_exe, model, wav, language="tr", threads=None, extra=None):
    """Single inference; measures duration and text.

    `asr_seconds` = end-to-end wall time (including model load). If the whisper.cpp
    timing lines can be parsed, **inference without loading** (`infer_seconds`) is also
    reported along with `load_seconds` / `encode_seconds` / `decode_seconds` (prevents
    RTF inflation on short audio).
    """
    cmd = build_whisper_command(whisper_exe, model, wav, language, threads, extra)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"whisper exit code {proc.returncode}: {(proc.stderr or '').strip()[:400]}")
    audio = audio_seconds(wav)
    res = {
        "text": (proc.stdout or "").strip(),
        "audio_seconds": round(audio, 3),
        "asr_seconds": round(dt, 4),
        "rtf": round(compute_rtf(dt, audio), 4),
    }
    res.update(parse_whisper_timings(proc.stderr or ""))
    if "encode_seconds" in res:
        res["infer_seconds"] = round(res["encode_seconds"] + res.get("decode_seconds", 0.0), 4)
        res["infer_rtf"] = round(compute_rtf(res["infer_seconds"], audio), 4)
    return res


def transcribe_server(server_url, wav, language="tr", timeout=600):
    """Transcribes through whisper-server (`/inference`).

    The model **stays loaded** on the server; therefore `asr_seconds` = pure inference
    (no loading). Uses no external dependency (multipart with urllib).
    """
    import urllib.request
    import uuid

    url = server_url.rstrip("/") + "/inference"
    boundary = "----altai" + uuid.uuid4().hex
    with open(wav, "rb") as f:
        audio_bytes = f.read()

    def field(name, value):
        return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                f"{value}\r\n").encode("utf-8")

    body = b""
    body += field("response_format", "json")
    body += field("language", language or "auto")
    body += field("temperature", "0.0")
    body += field("no_timestamps", "true")
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n").encode("utf-8")
    body += audio_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    dt = time.perf_counter() - t0

    try:
        parsed = json.loads(raw)
        text = (parsed.get("text") or "").strip()
    except Exception:
        text = raw.strip()

    audio = audio_seconds(wav)
    return {
        "text": text,
        "audio_seconds": round(audio, 3),
        "asr_seconds": round(dt, 4),
        "rtf": round(compute_rtf(dt, audio), 4),
        "server": url,
    }


def transcribe(whisper_exe, model, wav, language="tr", threads=None, extra=None, server_url=None):
    """Inference router: whisper-server if a server URL is given, otherwise single-shot whisper-cli."""
    if server_url:
        return transcribe_server(server_url, wav, language)
    return transcribe_once(whisper_exe, model, wav, language, threads, extra)


def benchmark_file(whisper_exe, model, wav, language="tr", threads=None, repeat=1, extra=None,
                   server_url=None):
    runs = [transcribe(whisper_exe, model, wav, language, threads, extra, server_url)
            for _ in range(max(1, repeat))]
    asr = [r["asr_seconds"] for r in runs]
    infer = [r["infer_seconds"] for r in runs if "infer_seconds" in r]
    out = {
        "file": wav,
        "text": runs[-1]["text"],
        "audio_seconds": runs[-1]["audio_seconds"],
        "asr_seconds": round(min(asr), 4),
        "runs": [r["asr_seconds"] for r in runs],
        "median_asr": round(percentile(asr, 0.5), 4) if asr else None,
        "p95_asr": round(percentile(asr, 0.95), 4) if asr else None,
        "rtf": runs[-1]["rtf"],
        "model_load_seconds": runs[-1].get("load_seconds"),
    }
    if server_url:
        out["server"] = runs[-1].get("server")
    if infer:
        out["median_infer"] = round(percentile(infer, 0.5), 4)
        out["infer_rtf"] = runs[-1].get("infer_rtf")
    return out


def collect_wavs(path: str):
    if os.path.isdir(path):
        out = []
        for name in sorted(os.listdir(path)):
            if name.lower().endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus")):
                out.append(os.path.join(path, name))
        return out
    return [path]


# ---------------------------------------------------------------- CLI

def _emit(payload: dict, out_path: str | None):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="whisper.cpp inference + latency measurement (Phase 2)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--wav", help="single audio file")
    src.add_argument("--dir", help="folder of audio files")
    ap.add_argument("--model", default=None,
                    help="whisper.cpp model file (.bin); not needed if --server-url is given")
    ap.add_argument("--whisper", default=None, help="path to whisper-cli (default: PATH)")
    ap.add_argument("--server-url", default=None,
                    help="whisper-server base URL (e.g. http://127.0.0.1:8081); if given, the model stays in memory")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--lang", default="tr")
    ap.add_argument("--threads", type=int, default=None,
                    help="whisper.cpp -t value (default: logical core count)")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out", default=None, help="JSON output file")
    ap.add_argument("--tmp", default=DEFAULT_TMP, help="temporary folder for conversion")
    args = ap.parse_args(argv)

    if args.server_url:
        whisper = args.server_url          # server mode: no binary needed
    else:
        whisper = find_whisper(args.whisper)
        if not whisper:
            _emit({"ok": False, "error": "whisper.cpp binary not found",
                   "hint": "add whisper-cli to PATH or pass --whisper",
                   "expected": DEFAULT_WHISPER}, args.out)
            return 3
        if not args.model or not os.path.exists(args.model):
            _emit({"ok": False, "error": f"model not found: {args.model}"}, args.out)
            return 3

    # threads: logical core count if not given (whisper default is 4; tuned by measurement)
    threads = args.threads if (args.threads and args.threads > 0) else default_threads()

    files = collect_wavs(args.wav or args.dir)
    if not files:
        _emit({"ok": False, "error": "no audio files found"}, args.out)
        return 4

    results, errors = [], []
    for f in files:
        wav, err = prepare_wav(f, args.tmp, args.ffmpeg)
        if err:
            errors.append({"file": f, "error": err})
            continue
        try:
            results.append(benchmark_file(whisper, args.model, wav, args.lang,
                                          threads, args.repeat, server_url=args.server_url))
        except Exception as exc:  # an inference error does not abort the run
            errors.append({"file": f, "error": str(exc)})

    asr_all = [r["median_asr"] for r in results if r["median_asr"] is not None]
    infer_all = [r["median_infer"] for r in results if r.get("median_infer") is not None]
    payload = {
        "ok": bool(results),
        "whisper": whisper,
        "model": args.model,
        "language": args.lang,
        "threads": threads,
        "repeat": args.repeat,
        "server_url": args.server_url,
        "results": results,
        "errors": errors,
        "stats": {
            "median_asr": round(percentile(asr_all, 0.5), 4) if asr_all else None,
            "p95_asr": round(percentile(asr_all, 0.95), 4) if asr_all else None,
            "mean_rtf": round(sum(r["rtf"] for r in results) / len(results), 4) if results else None,
            "median_infer": round(percentile(infer_all, 0.5), 4) if infer_all else None,
        },
    }
    _emit(payload, args.out)
    return 0 if results else 5


if __name__ == "__main__":
    sys.exit(main())
