#!/usr/bin/env python3
"""tts-tools.py -- Takas edilebilir TTS araci (aybars_says).

Backend'ler:
  - chatterbox : Resemble AI Chatterbox (Multilingual V3 dahil) -- birincil, en dogal
  - piper      : hizli/CPU yedek (kurulu degilse durustce hata verir)
  - sapi       : Windows SAPI son care

Sozlesme JSON'dur (stdout). Model/binary yoksa `ok=false` doner; uydurmaz.

Ornek:
  python agent/tts-tools.py --backend chatterbox --text "Merhaba dunya" --lang tr --out out.wav
  python agent/tts-tools.py --backend chatterbox --text "Hello" --out en.wav --device cuda
  python agent/tts-tools.py --backend chatterbox --text "..." --voice-prompt ref.wav --out clone.wav
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import wave

# ------------------------------------------------------------------ yardimcilar

def _json(payload: dict, out_path_json: str | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if out_path_json:
        os.makedirs(os.path.dirname(os.path.abspath(out_path_json)), exist_ok=True)
        with open(out_path_json, "w", encoding="utf-8") as f:
            f.write(text + "\n")


def _read_text(args) -> str:
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return (args.text or "").strip()


# ------------------------------------------------------------------ chatterbox

def _save_wav(wav, path, sr):
    """WAV yazar. torchaudio.save bazi surumlerde torchcodec ister; once soundfile dene."""
    try:
        import soundfile as sf
        arr = wav.detach().cpu().numpy() if hasattr(wav, "detach") else wav
        try:
            arr = arr.squeeze()
        except Exception:
            pass
        sf.write(path, arr, int(sr))
        return "soundfile"
    except Exception:
        import torchaudio as ta
        ta.save(path, wav, sr)
        return "torchaudio"


def synth_chatterbox(text, out_wav, lang=None, voice_prompt=None, device="cuda",
                     exaggeration=0.5, cfg=0.5, t3_model="v3", seed=None):
    import torch

    if seed is not None:
        torch.manual_seed(seed)

    uses_mtl = bool(lang)
    if uses_mtl:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        try:
            model = ChatterboxMultilingualTTS.from_pretrained(device=device, t3_model=t3_model)
        except TypeError:
            # Kurulu surum t3_model'i tanimiyor olabilir; sade cagri
            model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    else:
        from chatterbox.tts import ChatterboxTTS
        model = ChatterboxTTS.from_pretrained(device=device)

    kwargs = {}
    if voice_prompt:
        kwargs["audio_prompt_path"] = voice_prompt
    if uses_mtl:
        kwargs["language_id"] = lang

    def _gen(extra):
        return model.generate(text, **{**kwargs, **extra})

    # API surumleri arasinda parametre adlari degisebilir: once zengin, olmazsa sade dene.
    t0 = time.perf_counter()
    try:
        wav = _gen({"exaggeration": exaggeration, "cfg_weight": cfg})
    except TypeError:
        try:
            wav = _gen({"exaggeration": exaggeration})
        except TypeError:
            wav = _gen({})
    dt = time.perf_counter() - t0

    writer = _save_wav(wav, out_wav, model.sr)
    secs = wav.shape[-1] / float(model.sr)
    return {"out": out_wav, "sample_rate": int(model.sr), "audio_seconds": round(secs, 3),
            "tts_seconds": round(dt, 3), "rtf": round((dt / secs) if secs else float("inf"), 3),
            "voice_prompt": voice_prompt, "language_id": lang,
            "t3_model": t3_model if uses_mtl else None, "writer": writer}


# ------------------------------------------------------------------ piper (yedek)

def synth_piper(text, out_wav, model_path=None, piper_exe=None):
    import shutil
    import subprocess
    exe = piper_exe or shutil.which("piper")
    if not exe:
        raise RuntimeError("piper bulunamadi (PATH ya da --piper ver)")
    if not model_path or not os.path.exists(model_path):
        raise RuntimeError(f"piper modeli bulunamadi: {model_path}")
    t0 = time.perf_counter()
    proc = subprocess.run([exe, "-m", model_path, "-f", out_wav], input=text,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"piper hatasi: {(proc.stderr or '').strip()[:300]}")
    with wave.open(out_wav, "rb") as w:
        secs = w.getnframes() / float(w.getframerate() or 1)
        sr = w.getframerate()
    return {"out": out_wav, "sample_rate": int(sr), "audio_seconds": round(secs, 3),
            "tts_seconds": round(dt, 3), "rtf": round((dt / secs) if secs else float("inf"), 3)}


# ------------------------------------------------------------------ sapi (son care)

def synth_sapi(text, out_wav):
    import subprocess
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SetOutputToWaveFile('{out_wav}');"
        f"$s.Speak('{(text or '').replace(chr(39), chr(39)*2)}');"
        "$s.Dispose()"
    )
    t0 = time.perf_counter()
    proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                          capture_output=True, text=True, errors="replace")
    dt = time.perf_counter() - t0
    if proc.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError(f"SAPI hatasi: {(proc.stderr or '').strip()[:300]}")
    with wave.open(out_wav, "rb") as w:
        secs = w.getnframes() / float(w.getframerate() or 1)
        sr = w.getframerate()
    return {"out": out_wav, "sample_rate": int(sr), "audio_seconds": round(secs, 3),
            "tts_seconds": round(dt, 3), "rtf": round((dt / secs) if secs else float("inf"), 3)}


# ------------------------------------------------------------------ CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Takas edilebilir TTS (aybars_says)")
    ap.add_argument("--backend", default="chatterbox", choices=["chatterbox", "piper", "sapi"])
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default=None, help="chatterbox coklu dil: tr, en, ...")
    ap.add_argument("--voice-prompt", default=None, help="klonlama icin referans wav")
    ap.add_argument("--device", default="cuda", help="cuda | cpu")
    ap.add_argument("--exaggeration", type=float, default=0.5)
    ap.add_argument("--cfg", type=float, default=0.5)
    ap.add_argument("--t3-model", default="v3", help="chatterbox coklu dil checkpoint: v3 | v2")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--piper", default=None)
    ap.add_argument("--piper-model", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    text = _read_text(args)
    if not text:
        _json({"ok": False, "error": "metin bos (--text ya da --text-file ver)"}, args.json_out)
        return 2

    try:
        if args.backend == "chatterbox":
            res = synth_chatterbox(text, args.out, args.lang, args.voice_prompt, args.device,
                                   args.exaggeration, args.cfg, args.t3_model, args.seed)
        elif args.backend == "piper":
            res = synth_piper(text, args.out, args.piper_model, args.piper)
        else:
            res = synth_sapi(text, args.out)
    except Exception as exc:
        _json({"ok": False, "backend": args.backend, "error": f"{type(exc).__name__}: {exc}"}, args.json_out)
        return 3

    res["ok"] = True
    res["backend"] = args.backend
    res["text"] = text[:200]
    _json(res, args.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
