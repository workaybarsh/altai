#!/usr/bin/env python3
"""asr-tools.py -- whisper.cpp cikarim araci (aybars_says, Faz 2 iskeleti).

Gorev:
  1. Ses dosyasini (gerekirse) 16 kHz mono WAV'a cevirir.
  2. whisper.cpp (`whisper-cli`) ile yaziya cevirir.
  3. Gecikme ve RTF olcumlerini JSON olarak dondurur.

Model/binary yoksa durustce `ok=false` doner (uydurmaz). Sozlesme JSON'dur.

Kullanim:
  python agent/asr-tools.py --wav girdi.wav --model models/ggml-large-v3-turbo.bin
  python agent/asr-tools.py --dir tests/assets --model ... --repeat 10 --out logs/asr.json

Cikti (stdout, JSON):
  {
    "ok": true,
    "whisper": "...", "model": "...", "language": "tr", "repeat": 1,
    "results": [
      {"file": "...", "text": "...", "audio_seconds": 4.2, "asr_seconds": 0.31, "rtf": 0.074}
    ],
    "stats": {"median_asr": 0.31, "p95_asr": 0.35, "mean_rtf": 0.074}
  }
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


# ---------------------------------------------------------------- saf yardimcilar

def audio_seconds(path: str) -> float:
    """WAV dosyasinin sure saniyesi."""
    with wave.open(path, "rb") as w:
        rate = w.getframerate() or 1
        return w.getnframes() / float(rate)


def compute_rtf(asr_seconds: float, audio_sec: float) -> float:
    """Gercek zaman carpani = islem suresi / ses suresi."""
    if audio_sec <= 0:
        return float("inf")
    return asr_seconds / audio_sec


def percentile(values, p: float):
    """Lineer interpolasyonlu yuzdelik (p: 0..1). Bos ise None."""
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
    """whisper.cpp komut satirini kurar (test edilebilir, yan etkisiz)."""
    cmd = [whisper_exe, "-m", model, "-f", wav, "-l", language or "auto", "-nt"]
    if threads:
        cmd += ["-t", str(int(threads))]
    if extra:
        cmd += list(extra)
    return cmd


def find_whisper(explicit: str | None = None):
    """whisper.cpp ikilisini bulur (verilen yol, PATH, yaygin adlar)."""
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


# ---------------------------------------------------------------- ses hatti

def to_wav_16k_mono(src: str, dst: str, ffmpeg: str = "ffmpeg"):
    """ffmpeg ile 16 kHz mono PCM WAV'a cevirir. (yol, hata) doner."""
    exe = find_ffmpeg(ffmpeg)
    if not exe:
        return None, "ffmpeg bulunamadi (16 kHz mono donusum gerekli)"
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    cmd = [exe, "-y", "-i", src, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode != 0 or not os.path.exists(dst):
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-3:])
        return None, f"ffmpeg hatasi: {tail}"
    return dst, None


def prepare_wav(src: str, workdir: str, ffmpeg: str = "ffmpeg"):
    """Zaten 16 kHz mono ise dokunmaz; degilse donusturur. (yol, hata) doner."""
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
    """Tek cikarim; sure ve metni olcer."""
    cmd = build_whisper_command(whisper_exe, model, wav, language, threads, extra)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"whisper cikis kodu {proc.returncode}: {(proc.stderr or '').strip()[:400]}")
    audio = audio_seconds(wav)
    return {
        "text": (proc.stdout or "").strip(),
        "audio_seconds": round(audio, 3),
        "asr_seconds": round(dt, 4),
        "rtf": round(compute_rtf(dt, audio), 4),
    }


def benchmark_file(whisper_exe, model, wav, language="tr", threads=None, repeat=1, extra=None):
    runs = [transcribe_once(whisper_exe, model, wav, language, threads, extra) for _ in range(max(1, repeat))]
    asr = [r["asr_seconds"] for r in runs]
    return {
        "file": wav,
        "text": runs[-1]["text"],
        "audio_seconds": runs[-1]["audio_seconds"],
        "asr_seconds": round(min(asr), 4),
        "runs": [r["asr_seconds"] for r in runs],
        "median_asr": round(percentile(asr, 0.5), 4) if asr else None,
        "p95_asr": round(percentile(asr, 0.95), 4) if asr else None,
        "rtf": runs[-1]["rtf"],
    }


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
    ap = argparse.ArgumentParser(description="whisper.cpp cikarim + gecikme olcumu (Faz 2)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--wav", help="tek ses dosyasi")
    src.add_argument("--dir", help="ses dosyalari klasoru")
    ap.add_argument("--model", required=True, help="whisper.cpp model dosyasi (.bin)")
    ap.add_argument("--whisper", default=None, help="whisper-cli yolu (varsayilan: PATH)")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--lang", default="tr")
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out", default=None, help="JSON cikti dosyasi")
    ap.add_argument("--tmp", default=DEFAULT_TMP, help="donusum icin gecici klasor")
    args = ap.parse_args(argv)

    whisper = find_whisper(args.whisper)
    if not whisper:
        _emit({"ok": False, "error": "whisper.cpp ikilisi bulunamadi",
               "ipucu": "whisper-cli'yi PATH'e ekle ya da --whisper ver",
               "beklenen": DEFAULT_WHISPER}, args.out)
        return 3
    if not args.model or not os.path.exists(args.model):
        _emit({"ok": False, "error": f"model bulunamadi: {args.model}"}, args.out)
        return 3

    files = collect_wavs(args.wav or args.dir)
    if not files:
        _emit({"ok": False, "error": "ses dosyasi bulunamadi"}, args.out)
        return 4

    results, errors = [], []
    for f in files:
        wav, err = prepare_wav(f, args.tmp, args.ffmpeg)
        if err:
            errors.append({"file": f, "error": err})
            continue
        try:
            results.append(benchmark_file(whisper, args.model, wav, args.lang,
                                          args.threads, args.repeat))
        except Exception as exc:  # cikarim hatasi turu durdurmaz
            errors.append({"file": f, "error": str(exc)})

    asr_all = [r["median_asr"] for r in results if r["median_asr"] is not None]
    payload = {
        "ok": bool(results),
        "whisper": whisper,
        "model": args.model,
        "language": args.lang,
        "threads": args.threads,
        "repeat": args.repeat,
        "results": results,
        "errors": errors,
        "stats": {
            "median_asr": round(percentile(asr_all, 0.5), 4) if asr_all else None,
            "p95_asr": round(percentile(asr_all, 0.95), 4) if asr_all else None,
            "mean_rtf": round(sum(r["rtf"] for r in results) / len(results), 4) if results else None,
        },
    }
    _emit(payload, args.out)
    return 0 if results else 5


if __name__ == "__main__":
    sys.exit(main())
