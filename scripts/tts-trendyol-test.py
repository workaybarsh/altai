#!/usr/bin/env python3
"""Trendyol-TTS (openbmb/VoxCPM2 + Turkce LoRA) hizli test betigi.

Amac: Turkce kalitesini degerlendirmek icin ornek uretmek.

Kurulum (bir kez):
    pip install voxcpm soundfile

Kullanim:
    python scripts/tts-trendyol-test.py
    python scripts/tts-trendyol-test.py --text "Baska bir cumle" --out logs/tts/trendyol-tr2.wav

Cikti: logs/tts/trendyol-tr.wav (+ JSON ozet stdout'a)

Not: Trendyol-TTS Turkce-odaklidir (MIT, ~2B). Taban: openbmb/VoxCPM2.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import wave

MODEL_ID = "Trendyol/Trendyol-TTS"
DEFAULT_TEXT = ("Merhaba! Ben tamamen yerel calisan bir sesli asistanim. "
                "Bugun size nasil yardimci olabilirim?")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default=DEFAULT_TEXT)
    ap.add_argument("--out", default=os.path.join("logs", "tts", "trendyol-tr.wav"))
    ap.add_argument("--cfg", type=float, default=2.0)
    ap.add_argument("--timesteps", type=int, default=16)
    args = ap.parse_args()

    try:
        import soundfile as sf
        from voxcpm.core import VoxCPM
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"bagimlilik eksik: {exc}",
                          "ipucu": "pip install voxcpm soundfile"}, ensure_ascii=False, indent=2))
        return 3

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    t0 = time.time()
    model = VoxCPM.from_pretrained(hf_model_id=MODEL_ID, load_denoiser=False, optimize=True)
    load_s = time.time() - t0

    t1 = time.time()
    audio = model.generate(text=args.text, cfg_value=args.cfg,
                           inference_timesteps=args.timesteps, max_len=4096,
                           normalize=True, denoise=False)
    gen_s = time.time() - t1

    sf.write(args.out, audio, model.tts_model.sample_rate)
    with wave.open(args.out) as w:
        secs = w.getnframes() / float(w.getframerate() or 1)
        sr = w.getframerate()

    print(json.dumps({
        "ok": True, "out": os.path.abspath(args.out), "model": MODEL_ID,
        "sample_rate": int(sr), "audio_seconds": round(secs, 2),
        "load_seconds": round(load_s, 1), "tts_seconds": round(gen_s, 2),
        "rtf": round(gen_s / secs, 2) if secs else None, "text": args.text,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
