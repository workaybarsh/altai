#!/usr/bin/env python3
"""asr-tools.py -- whisper.cpp cikarim araci (aybars_speaks, Faz 2 iskeleti).

Gorev:
  1. Ses dosyasini (gerekirse) 16 kHz mono WAV'a cevirir.
  2. whisper.cpp (`whisper-cli`) ile yaziya cevirir.
  3. Gecikme ve RTF olcumlerini JSON olarak dondurur.

Model/binary yoksa durustce `ok=false` doner (uydurmaz). Sozlesme JSON'dur.

Kullanim:
  python agent/asr-tools.py --wav girdi.wav --model models/ggml-large-v3-turbo-q5_0.bin
  python agent/asr-tools.py --dir tests/assets --model ... --repeat 10 --out logs/asr.json
  python agent/asr-tools.py --wav girdi.wav --server-url http://127.0.0.1:8081   # model bellekte

Cikti (stdout, JSON):
  {
    "ok": true,
    "whisper": "...", "model": "...", "language": "tr", "threads": 6, "repeat": 1,
    "results": [
      {"file": "...", "text": "...", "audio_seconds": 4.2, "asr_seconds": 0.31, "rtf": 0.074,
       "load_seconds": 0.52, "encode_seconds": 0.28, "infer_seconds": 0.28}
    ],
    "stats": {"median_asr": 0.31, "p95_asr": 0.35, "mean_rtf": 0.074, "median_infer": 0.28}
  }

Notlar:
  - `asr_seconds` = uctan uca duvar suresi (model yukleme dahil).
  - `infer_seconds` = whisper.cpp encode+decode (model yukleme HARIC) -- kisa seslerde
    RTF'i dogru okumak icin. Tek-atim surec her cagride modeli yeniden yukler.
  - `--threads` verilmezse mantiksal cekirdek sayisi kullanilir (whisper varsayilani 4).
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


def default_threads() -> int:
    """Varsayilan thread sayisi = **mantiksal** cekirdek sayisi.

    Olculdu (Ryzen 5 3600, 6C/12T, large-v3-turbo): q5_0 ile `-t 12` (10,0 sn) <
    `-t 6` (13,1 sn) < whisper varsayilani `-t 4` (20,9 sn, f16). Yani bu makinede
    SMT kazanc sagliyor; genel kural "fiziksel cekirdek" olsa da olcumle dogrulanmali
    (AGENTS tuzak #9). `--threads` ile acikca gecersiz kilinabilir.
    """
    return max(1, os.cpu_count() or 1)


def parse_whisper_timings(stderr: str) -> dict:
    """whisper.cpp `whisper_print_timings:` satirlarini (ms) saniyeye cevirir.

    Amac: **model yukleme** ile **gercek cikarim**i ayirmak. Tek-atim sureci her
    cagrida modeli yeniden yukler; bu, kisa seslerde RTF'i sisirir.
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
    """Tek cikarim; sure ve metni olcer.

    `asr_seconds` = uctan uca duvar suresi (model yukleme dahil). whisper.cpp
    zamanlama satirlari ayristirilirsa `load_seconds` / `encode_seconds` / `decode_seconds`
    ile **yuklemesiz cikarim** (`infer_seconds`) de raporlanir (kisa seslerde RTF sisirmesini onler).
    """
    cmd = build_whisper_command(whisper_exe, model, wav, language, threads, extra)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"whisper cikis kodu {proc.returncode}: {(proc.stderr or '').strip()[:400]}")
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
    """whisper-server (`/inference`) uzerinden yaziya cevirir.

    Model sunucuda **yuklu kalir**; bu yuzden `asr_seconds` = saf cikarim (yukleme yok).
    Harici bagimlilik kullanmaz (urllib ile multipart).
    """
    import urllib.request
    import uuid

    url = server_url.rstrip("/") + "/inference"
    boundary = "----aybars" + uuid.uuid4().hex
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
    """Cikarim yonlendiricisi: sunucu verilirse whisper-server, yoksa tek-atim whisper-cli."""
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
    ap = argparse.ArgumentParser(description="whisper.cpp cikarim + gecikme olcumu (Faz 2)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--wav", help="tek ses dosyasi")
    src.add_argument("--dir", help="ses dosyalari klasoru")
    ap.add_argument("--model", default=None,
                    help="whisper.cpp model dosyasi (.bin); --server-url verilirse gerekmez")
    ap.add_argument("--whisper", default=None, help="whisper-cli yolu (varsayilan: PATH)")
    ap.add_argument("--server-url", default=None,
                    help="whisper-server taban URL (or. http://127.0.0.1:8081); verilirse model bellekte kalir")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--lang", default="tr")
    ap.add_argument("--threads", type=int, default=None,
                    help="whisper.cpp -t degeri (varsayilan: mantiksal cekirdek sayisi)")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out", default=None, help="JSON cikti dosyasi")
    ap.add_argument("--tmp", default=DEFAULT_TMP, help="donusum icin gecici klasor")
    args = ap.parse_args(argv)

    if args.server_url:
        whisper = args.server_url          # sunucu modu: ikili gerekmez
    else:
        whisper = find_whisper(args.whisper)
        if not whisper:
            _emit({"ok": False, "error": "whisper.cpp ikilisi bulunamadi",
                   "ipucu": "whisper-cli'yi PATH'e ekle ya da --whisper ver",
                   "beklenen": DEFAULT_WHISPER}, args.out)
            return 3
        if not args.model or not os.path.exists(args.model):
            _emit({"ok": False, "error": f"model bulunamadi: {args.model}"}, args.out)
            return 3

    # thread: verilmezse mantiksal cekirdek sayisi (whisper varsayilani 4; olcumle ayarlanir)
    threads = args.threads if (args.threads and args.threads > 0) else default_threads()

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
                                          threads, args.repeat, server_url=args.server_url))
        except Exception as exc:  # cikarim hatasi turu durdurmaz
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
