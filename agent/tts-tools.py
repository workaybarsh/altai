#!/usr/bin/env python3
"""tts-tools.py -- Takas edilebilir TTS araci (aybars_says).

Backend'ler:
  - chatterbox : Resemble AI Chatterbox (Multilingual V3 dahil) -- birincil, en dogal
  - voxcpm     : Trendyol-TTS (openbmb/VoxCPM2 + Turkce LoRA, MIT, ~2B) -- TR native,
                 yuksek kalite ama AGIR (~5,6 GB VRAM, RTF ~3) -> cevrimdisi/yuksek kalite
  - piper      : hizli/CPU yedek (kurulu degilse durustce hata verir)
  - sapi       : Windows SAPI son care

Sozlesme JSON'dur (stdout). Model/binary yoksa `ok=false` doner; uydurmaz.

Ornek:
  python agent/tts-tools.py --backend chatterbox --text "Merhaba dunya" --lang tr --out out.wav
  python agent/tts-tools.py --backend chatterbox --text "Hello" --out en.wav --device cuda
  python agent/tts-tools.py --backend chatterbox --text "..." --voice-prompt ref.wav --out clone.wav
  python agent/tts-tools.py --backend voxcpm --text "Merhaba dunya" --out tr.wav --device cuda
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


def _read_lines(path: str):
    """Coklu cumle dosyasi: her satir bir cumle (bos satirlar atlanir)."""
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


# ------------------------------------------------------------------ Turkce metin (Chatterbox icin)

_TR_UPPER_TO_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def tr_lower(s: str) -> str:
    """Turkce'ye duyarli kucultme: 'I'->'ı' (noktasiz), 'İ'->'i'."""
    return s.translate(_TR_UPPER_TO_LOWER).lower()


def install_tr_tokenizer_fix(tokenizer):
    """Chatterbox cok dilli tokenizer'inda TR on-islemesini duzeltir.

    Kok neden: `MTLTokenizer.preprocess_text` metne her zaman `NFKD` uygular; bu,
    'ş/ğ/ü/ö/ç' harflerini taban harf + birlesen isarete ayirir (ör. 'ş' -> 's'+cedilla).
    Tokenizer sozlugunde bu birlesen isaretler yoksa diakritik kaybolur ('ş'->'s',
    'ü'->'u'). Ayrica `lower()` Turkce'ye duyarsizdir ('I'->'i', 'İ'->'i'+nokta).

    Bu yama, `language_id='tr'` icin NFKD'yi KAPATIR (harfleri NFC/precomposed tutar) ve
    Turkce kucultme uygular. Diger diller icin orijinal davranis korunur.
    """
    import unicodedata
    orig = tokenizer.preprocess_text

    def _pre(raw_text, language_id=None, lowercase=True, nfkd_normalize=True):
        if (language_id or "").lower() == "tr":
            t = tr_lower(raw_text) if lowercase else raw_text
            return unicodedata.normalize("NFC", t)  # NFKD YOK: birlesik harfleri koru
        return orig(raw_text, language_id=language_id, lowercase=lowercase,
                    nfkd_normalize=nfkd_normalize)

    tokenizer.preprocess_text = _pre
    return tokenizer


def tr_respell(s: str) -> str:
    """Chatterbox TR icin fonetik ipucu: 'ş' -> 'sh'.

    Modelin Turkce 'ş' (//ʃ//) sesini yanlis uretmesini (ör. 'çalışan' -> 'çalıyan')
    telafi eder; 'sh' digrafi /ʃ/ olarak okunur. Kulak testiyle dogrulandi (2026-10-17).
    """
    return s.replace("ş", "sh").replace("Ş", "sh")


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


def load_chatterbox(lang=None, device="cuda", t3_model="v3"):
    """Chatterbox modelini bir kez yukler (toplu uretim icin)."""
    uses_mtl = bool(lang)
    if uses_mtl:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        try:
            return ChatterboxMultilingualTTS.from_pretrained(device=device, t3_model=t3_model)
        except TypeError:
            # Kurulu surum t3_model'i tanimiyor olabilir; sade cagri
            return ChatterboxMultilingualTTS.from_pretrained(device=device)
    from chatterbox.tts import ChatterboxTTS
    return ChatterboxTTS.from_pretrained(device=device)


def synth_chatterbox(text, out_wav, lang=None, voice_prompt=None, device="cuda",
                     exaggeration=0.5, cfg=0.5, t3_model="v3", seed=None, tr_fix=True,
                     respell=True, model=None):
    import torch

    if model is None:
        model = load_chatterbox(lang=lang, device=device, t3_model=t3_model)
    if seed is not None:
        torch.manual_seed(seed)

    # TR icin duzeltmeler OTOMATIK (lang='tr'): tokenizer NFKD yamasi + 'ş'->'sh' respell.
    # (kapatmak icin tr_fix/respell = False; CLI: --chatterbox-tr-raw)
    if (lang or "").lower() == "tr":
        if tr_fix:
            install_tr_tokenizer_fix(model.tokenizer)
        if respell:
            text = tr_respell(text)

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


# ------------------------------------------------------------------ voxcpm (Trendyol-TTS, TR)

def synth_voxcpm(text, out_wav, model_id="Trendyol/Trendyol-TTS", cfg=2.0, timesteps=16,
                 device=None, optimize=True, load_denoiser=False, max_len=4096,
                 normalize=True, denoise=False):
    """VoxCPM2 tabanli TR TTS (Trendyol-TTS). TR native; MIT. AGIR (VRAM + RTF)."""
    import soundfile as sf
    from voxcpm.core import VoxCPM

    t0 = time.perf_counter()
    kwargs = {"hf_model_id": model_id, "load_denoiser": load_denoiser, "optimize": optimize}
    if device:
        kwargs["device"] = device
    model = VoxCPM.from_pretrained(**kwargs)
    load_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    audio = model.generate(text=text, cfg_value=cfg, inference_timesteps=timesteps,
                           max_len=max_len, normalize=normalize, denoise=denoise)
    gen_s = time.perf_counter() - t1

    sr = int(model.tts_model.sample_rate)
    os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
    sf.write(out_wav, audio, sr)
    with wave.open(out_wav, "rb") as w:
        secs = w.getnframes() / float(w.getframerate() or 1)

    return {"out": out_wav, "sample_rate": sr, "audio_seconds": round(secs, 3),
            "load_seconds": round(load_s, 2), "tts_seconds": round(gen_s, 3),
            "rtf": round((gen_s / secs) if secs else float("inf"), 3),
            "model": model_id, "cfg": cfg, "inference_timesteps": timesteps}


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
    ap.add_argument("--backend", default="chatterbox", choices=["chatterbox", "voxcpm", "piper", "sapi"])
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default=None, help="chatterbox coklu dil: tr, en, ...")
    ap.add_argument("--voice-prompt", default=None, help="klonlama icin referans wav")
    ap.add_argument("--device", default="cuda", help="cuda | cpu")
    ap.add_argument("--exaggeration", type=float, default=0.5)
    ap.add_argument("--cfg", type=float, default=0.5)
    ap.add_argument("--t3-model", default="v3", help="chatterbox coklu dil checkpoint: v3 | v2")
    ap.add_argument("--chatterbox-tr-raw", action="store_true",
                    help="chatterbox TR duzeltmelerini KAPAT (tr_fix+respell); test/AB icin")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--voxcpm-model", default="Trendyol/Trendyol-TTS", help="voxcpm HF model id")
    ap.add_argument("--voxcpm-cfg", type=float, default=2.0)
    ap.add_argument("--voxcpm-steps", type=int, default=16)
    ap.add_argument("--no-optimize", action="store_true", help="voxcpm optimize kapat")
    ap.add_argument("--piper", default=None)
    ap.add_argument("--piper-model", default=None)
    ap.add_argument("--json-out", default=None)
    # --- toplu uretim (model BIR KEZ yuklenir) ---
    ap.add_argument("--batch-file", default=None,
                    help="her satirda bir cumle; --out-prefix ile birlikte kullanilir")
    ap.add_argument("--out-prefix", default=None,
                    help="toplu modda cikti oneki: <onek>1.wav, <onek>2.wav ...")
    args = ap.parse_args(argv)

    # ---------------- TOPLU MOD (chatterbox): model tek yukleme ----------------
    if args.batch_file:
        lines = _read_lines(args.batch_file)
        if not lines:
            _json({"ok": False, "error": "batch dosyasi bos"}, args.json_out)
            return 2
        prefix = args.out_prefix or os.path.splitext(args.out)[0]
        os.makedirs(os.path.dirname(os.path.abspath(prefix)) or ".", exist_ok=True)
        try:
            if args.backend != "chatterbox":
                raise RuntimeError("toplu mod su an yalnizca chatterbox icin")
            t0 = time.perf_counter()
            model = load_chatterbox(lang=args.lang, device=args.device, t3_model=args.t3_model)
            load_s = time.perf_counter() - t0
            outs = []
            for i, line in enumerate(lines, 1):
                out_i = f"{prefix}{i}.wav"
                r = synth_chatterbox(line, out_i, args.lang, args.voice_prompt, args.device,
                                     args.exaggeration, args.cfg, args.t3_model, args.seed,
                                     not args.chatterbox_tr_raw, not args.chatterbox_tr_raw,
                                     model=model)
                r["index"] = i
                r["text"] = line[:200]
                outs.append(r)
        except Exception as exc:
            _json({"ok": False, "backend": args.backend,
                   "error": f"{type(exc).__name__}: {exc}"}, args.json_out)
            return 3
        total_audio = round(sum(o["audio_seconds"] for o in outs), 3)
        total_gen = round(sum(o["tts_seconds"] for o in outs), 3)
        payload = {"ok": True, "backend": args.backend, "batch": True,
                   "count": len(outs), "load_seconds": round(load_s, 2),
                   "total_tts_seconds": total_gen, "total_audio_seconds": total_audio,
                   "rtf": round(total_gen / total_audio, 3) if total_audio else None,
                   "results": outs}
        _json(payload, args.json_out)
        return 0

    text = _read_text(args)
    if not text:
        _json({"ok": False, "error": "metin bos (--text ya da --text-file ver)"}, args.json_out)
        return 2

    try:
        if args.backend == "chatterbox":
            res = synth_chatterbox(text, args.out, args.lang, args.voice_prompt, args.device,
                                   args.exaggeration, args.cfg, args.t3_model, args.seed,
                                   not args.chatterbox_tr_raw, not args.chatterbox_tr_raw)
        elif args.backend == "voxcpm":
            res = synth_voxcpm(text, args.out, args.voxcpm_model, args.voxcpm_cfg,
                               args.voxcpm_steps, args.device, not args.no_optimize)
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
