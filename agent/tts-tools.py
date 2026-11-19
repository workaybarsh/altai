#!/usr/bin/env python3
"""tts-tools.py -- swappable TTS tool (Altai).

Backends:
  - chatterbox : Resemble AI Chatterbox (including Multilingual V3) -- primary, most natural
  - voxcpm     : Trendyol-TTS (openbmb/VoxCPM2 + Turkish LoRA, MIT, ~2B) -- TR native,
                 high quality but HEAVY (~5.6 GB VRAM, RTF ~3) -> offline/high quality
  - piper      : fast/CPU fallback (fails honestly if it is not installed)
  - sapi       : Windows SAPI last resort

The contract is JSON (stdout). If the model/binary is missing it returns `ok=false`;
it does not make things up.

Example:
  python agent/tts-tools.py --backend chatterbox --text "Merhaba dunya" --lang tr --out out.wav
  python agent/tts-tools.py --backend chatterbox --text "Hello" --out en.wav --device cuda
  python agent/tts-tools.py --backend chatterbox --text "..." --voice-prompt ref.wav --out clone.wav
  python agent/tts-tools.py --backend voxcpm --text "Merhaba dunya" --out tr.wav --device cuda

Batch (the model is loaded ONCE; the default for the pipeline):
  python agent/tts-tools.py --backend chatterbox --lang tr --batch-file cumleler.txt \
      --out-prefix logs/pipeline/tts_ --json-out logs/pipeline/tts_batch.json

Persistent server (the model stays in memory; no reload on every turn):
  python agent/tts-tools.py --serve --backend chatterbox --lang tr --device cuda --port 8082
  # GET  /health          -> {"ok":true,"loaded":true,...}
  # POST /tts  {"texts":["..."],"lang":"tr","out_dir":"<absolute>","prefix":"tts_"}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import wave

# Console encoding (Windows cp125x) can make `print` blow up on non-UTF-8 characters
# (e.g. an emoji 😊 in LLM output). That would drop the WHOLE batch run -> switch stdout to UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ------------------------------------------------------------------ helpers

def _json(payload: dict, out_path_json: str | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        # If stdout is still not UTF-8 (rare), fall back to raw bytes so we do not crash
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")
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
    """Multi-sentence file: each line is one sentence (empty lines are skipped)."""
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


# ------------------------------------------------------------------ Turkish text (for Chatterbox)

_TR_UPPER_TO_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def tr_lower(s: str) -> str:
    """Turkish-aware lowercasing: 'I'->'ı' (dotless), 'İ'->'i'."""
    return s.translate(_TR_UPPER_TO_LOWER).lower()


def install_tr_tokenizer_fix(tokenizer):
    """Fixes the TR preprocessing in the Chatterbox multilingual tokenizer.

    Root cause: `MTLTokenizer.preprocess_text` always applies `NFKD` to the text; this splits
    the letters 'ş/ğ/ü/ö/ç' into a base letter plus a combining mark (e.g. 'ş' -> 's'+cedilla).
    If the tokenizer vocabulary has no such combining marks the diacritic is lost ('ş'->'s',
    'ü'->'u'). In addition `lower()` is not Turkish-aware ('I'->'i', 'İ'->'i'+dot).

    This patch TURNS NFKD OFF for `language_id='tr'` (keeping letters in NFC/precomposed form) and
    applies Turkish lowercasing. The original behaviour is preserved for other languages.
    """
    import unicodedata
    orig = tokenizer.preprocess_text

    def _pre(raw_text, language_id=None, lowercase=True, nfkd_normalize=True):
        if (language_id or "").lower() == "tr":
            t = tr_lower(raw_text) if lowercase else raw_text
            return unicodedata.normalize("NFC", t)  # NO NFKD: keep composed letters
        return orig(raw_text, language_id=language_id, lowercase=lowercase,
                    nfkd_normalize=nfkd_normalize)

    tokenizer.preprocess_text = _pre
    return tokenizer


_TR_VOWELS = "aeıioöuü"


def tr_softg(s: str) -> str:
    """Pronunciation hint for 'ğ' (soft g).

    Root cause (2026-10-18): 'ğ' IS present in the Chatterbox grapheme vocabulary (U+011F), so the
    tokenizer recognises it; but the acoustic model voices it wrongly -- 'çalıştığı' sounds like
    'çalıştı ki' to the ear. (The same vocabulary has no NFKD-decomposed 'g'+breve, which is why
    turning NFKD off in tr_fix is correct.)

    The Turkish soft-g rule is written out into the spelling:
      - between two vowels         -> 'y'      (değil -> deyil, çalıştığı -> çalıştıyı)
      - after a vowel, consonant/finally -> previous vowel repeated
                                   (dağ -> daa, yağmur -> yaamur)
      - after a consonant (rare)   -> 'g'      (mağdur -> magdur)
    """
    if "ğ" not in s and "Ğ" not in s:
        return s
    out = []
    for i, ch in enumerate(s):
        if ch in "ğĞ":
            prev = s[i - 1] if i else ""
            nxt = s[i + 1] if i + 1 < len(s) else ""
            # note: '' is a substring of every string -> handle the empty side separately
            p_vow = bool(prev) and prev.lower() in _TR_VOWELS
            n_vow = bool(nxt) and nxt.lower() in _TR_VOWELS
            if p_vow and n_vow:
                out.append("y")
            elif p_vow:
                out.append(prev.upper() if ch == "Ğ" else prev.lower())
            else:
                out.append("G" if ch == "Ğ" else "g")
            continue
        out.append(ch)
    return "".join(out)


def tr_respell(s: str, softg: bool = True) -> str:
    """Phonetic hint for Chatterbox TR: 'ş' -> 'sh', 'ğ' -> tr_softg().

    For 'ş' (//ʃ//): the model used to produce the 'ş' sound wrongly (e.g. 'çalışan' -> 'çalıyan');
    the 'sh' digraph is read as /ʃ/. Confirmed by a listening test (2026-10-17).
    For 'ğ': tr_softg() (see the root-cause note there); turned off with `softg=False`
    (for A/B and rollback -- CLI: --chatterbox-no-softg).
    """
    if softg:
        s = tr_softg(s)
    return s.replace("ş", "sh").replace("Ş", "sh")


# ------------------------------------------------------------------ chatterbox

def expected_audio_seconds(text, chars_per_sec=14.0, min_seconds=0.4):
    """Rough expectation for speech duration (TR ~14 characters/s). 0 if there are no letters/digits."""
    n = sum(1 for ch in text if ch.isalnum())
    if n == 0:
        return 0.0
    return max(min_seconds, n / float(chars_per_sec))


def ensure_speakable(text):
    """Is the text suitable for generation? ValueError if it has no letters/digits (emoji/symbols only).

    Empty sentences are already filtered out upstream (pipeline '\\p{L}|\\p{N}', `_read_lines`,
    `server_texts`); this check catches the remaining symbol-only input: Chatterbox used to
    blow up on such input (IndexError: max() on a zero-size input; on long broken text a CUDA
    device-side assert -> context poisoning). In batch mode the error is returned per item, on the server per
    request; the rest keep generating.
    """
    if not any(ch.isalnum() for ch in text):
        raise ValueError("text does not contain any valid letters (emoji/symbol?)")
    return text


def audio_guard_limit(text, factor=3.0, slack=2.0, chars_per_sec=14.0):
    """If the generated audio exceeds this limit it counts as 'long tail / hallucination'.

    limit = max(factor * expected, expected + slack). In a short sentence (e.g. "Merhaba!")
    expected ~0.5 s -> limit 2.5 s; the 9.6 s overflow is caught, a normal 1.9 s
    variance passes. (Doc: tts-benchmark.md §3/§9.3, the 9.6 s case in tts_batch.json.)
    """
    exp = expected_audio_seconds(text, chars_per_sec)
    return max(factor * exp, exp + slack)


def _save_wav(wav, path, sr):
    """Writes a WAV. torchaudio.save requires torchcodec in some versions; try soundfile first."""
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
    """Loads the Chatterbox model once (for batch generation)."""
    uses_mtl = bool(lang)
    if uses_mtl:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        try:
            return ChatterboxMultilingualTTS.from_pretrained(device=device, t3_model=t3_model)
        except TypeError:
            # The installed version may not know t3_model; plain call
            return ChatterboxMultilingualTTS.from_pretrained(device=device)
    from chatterbox.tts import ChatterboxTTS
    return ChatterboxTTS.from_pretrained(device=device)


def synth_chatterbox(text, out_wav, lang=None, voice_prompt=None, device="cuda",
                     exaggeration=0.5, cfg=0.5, t3_model="v3", seed=None, tr_fix=True,
                     respell=True, model=None, guard=True, softg=True):
    """Synthesises a single sentence with Chatterbox.

    `guard=True` (default): if the generated audio exceeds the `audio_guard_limit`, it generates the same text
    ONE more time and keeps the **shorter one** (long-tail/hallucination compensation;
    Chatterbox's own `alignment_stream_analyzer` guard is not always enough).
    The `retried` / `audio_limit_seconds` fields are added to the result.
    """
    import torch

    # Multilingual (MTL) model? Yes if lang is given. (Same rule as load_chatterbox;
    # it must be defined here too -- otherwise the `if uses_mtl` below raises NameError.)
    uses_mtl = bool(lang)

    if model is None:
        model = load_chatterbox(lang=lang, device=device, t3_model=t3_model)

    out_dir = os.path.dirname(os.path.abspath(out_wav))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # TR fixes are AUTOMATIC (lang='tr'): tokenizer NFKD patch + 'ş'->'sh' + 'ğ' respell.
    # (to turn off: tr_fix/respell = False; CLI: --chatterbox-tr-raw, for 'ğ' --chatterbox-no-softg)
    if (lang or "").lower() == "tr":
        if tr_fix:
            install_tr_tokenizer_fix(model.tokenizer)
        if respell:
            text = tr_respell(text, softg=softg)

    kwargs = {}
    if voice_prompt:
        kwargs["audio_prompt_path"] = voice_prompt
    if uses_mtl:
        kwargs["language_id"] = lang

    def _once(out_path, use_seed):
        if use_seed is not None:
            torch.manual_seed(use_seed)
        # Parameter names may differ between API versions: try the rich form first, else the plain one.
        t0 = time.perf_counter()
        # Chatterbox hardcodes max_new_tokens=1000 inside generate(); a short sentence can then
        # spend 10-20 s before EOS. Budget the sampler from the expected duration (~30 tokens/s).
        cap = max(120, int(expected_audio_seconds(text) * 30) + 48)
        t3 = getattr(model, "t3", None)
        original = getattr(t3, "inference", None)

        def capped(*a, **kw):
            kw["max_new_tokens"] = min(int(kw.get("max_new_tokens") or cap), cap)
            return original(*a, **kw)

        if t3 is not None and original is not None:
            t3.inference = capped
        try:
            try:
                wav = model.generate(text, **{**kwargs, "exaggeration": exaggeration, "cfg_weight": cfg})
            except TypeError:
                try:
                    wav = model.generate(text, **{**kwargs, "exaggeration": exaggeration})
                except TypeError:
                    wav = model.generate(text, **kwargs)
        finally:
            if t3 is not None and original is not None:
                t3.inference = original
        dt = time.perf_counter() - t0
        writer = _save_wav(wav, out_path, model.sr)
        secs = wav.shape[-1] / float(model.sr)
        return {"out": out_path, "sample_rate": int(model.sr),
                "audio_seconds": round(secs, 3), "tts_seconds": round(dt, 3),
                "rtf": round((dt / secs) if secs else float("inf"), 3), "writer": writer}

    res = _once(out_wav, seed)
    limit = audio_guard_limit(text)
    res.update({"voice_prompt": voice_prompt, "language_id": lang,
                "t3_model": t3_model if uses_mtl else None,
                "audio_limit_seconds": round(limit, 2)})

    if guard and res["audio_seconds"] > limit:
        # Long tail: generate once more with different sampling, keep the shorter one.
        retry_path = out_wav + ".retry.wav"
        retry_seed = (seed + 1) if seed is not None else None
        try:
            res2 = _once(retry_path, retry_seed)
        except Exception as exc:
            res["retried"] = True
            res["retry_error"] = f"{type(exc).__name__}: {exc}"
            return res
        res["retried"] = True
        res["long_tail_guard"] = True
        res["first_audio_seconds"] = res["audio_seconds"]   # reported in both branches
        res["guard_extra_seconds"] = res2["tts_seconds"]    # compensation cost (for measurement)
        if res2["audio_seconds"] < res["audio_seconds"]:
            os.replace(retry_path, out_wav)
            # NOTE: the file is now at the out_wav path; `out` must not point at the retry path
            # (the pipeline uses res.out with Test-Path -> on a false result the sentence was dropped).
            res2["out"] = out_wav
            res2["retry_out"] = retry_path
            res = {**res, **res2}
        else:
            res["retry_audio_seconds"] = res2["audio_seconds"]
            try:
                os.remove(retry_path)
            except OSError:
                pass
    return res


# ------------------------------------------------------------------ voxcpm (Trendyol-TTS, TR)

def synth_voxcpm(text, out_wav, model_id="Trendyol/Trendyol-TTS", cfg=2.0, timesteps=16,
                 device=None, optimize=True, load_denoiser=False, max_len=4096,
                 normalize=True, denoise=False):
    """VoxCPM2-based TR TTS (Trendyol-TTS). TR native; MIT. HEAVY (VRAM + RTF)."""
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


# ------------------------------------------------------------------ piper (fallback)

def _local_piper(name):
    """Default piper location installed by scripts/install-piper.ps1 (ASCII path)."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    p = os.path.join(base, "altai", "piper", name)
    return p if os.path.exists(p) else None


def synth_piper(text, out_wav, model_path=None, piper_exe=None):
    import shutil
    import subprocess
    exe = piper_exe or shutil.which("piper") or _local_piper("piper.exe")
    if not exe:
        raise RuntimeError("piper not found (pass PATH or --piper; see scripts/install-piper.ps1)")
    if not os.path.exists(exe):
        exe = shutil.which(exe)
        if not exe:
            raise RuntimeError(f"piper not found: {piper_exe}")
    model_path = model_path or _local_piper("voice.onnx")
    if not model_path or not os.path.exists(model_path):
        raise RuntimeError(f"piper model not found: {model_path}")
    t0 = time.perf_counter()
    proc = subprocess.run([exe, "-m", model_path, "-f", out_wav], input=text,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"piper error: {(proc.stderr or '').strip()[:300]}")
    with wave.open(out_wav, "rb") as w:
        secs = w.getnframes() / float(w.getframerate() or 1)
        sr = w.getframerate()
    return {"out": out_wav, "sample_rate": int(sr), "audio_seconds": round(secs, 3),
            "tts_seconds": round(dt, 3), "rtf": round((dt / secs) if secs else float("inf"), 3)}


# ------------------------------------------------------------------ sapi (last resort)

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
        raise RuntimeError(f"SAPI error: {(proc.stderr or '').strip()[:300]}")
    with wave.open(out_wav, "rb") as w:
        secs = w.getnframes() / float(w.getframerate() or 1)
        sr = w.getframerate()
    return {"out": out_wav, "sample_rate": int(sr), "audio_seconds": round(secs, 3),
            "tts_seconds": round(dt, 3), "rtf": round((dt / secs) if secs else float("inf"), 3)}


# ------------------------------------------------------------------ HTTP server (resident model)

def server_texts(req: dict):
    """Extracts the sentence list from a `/tts` request (single text / array / 'texts'/'text').

    Note: `ConvertTo-Json` sometimes collapses a single-element array into a plain string -> normalised here.
    Only **str** items are accepted; anything else is rejected with 400 (broken input can poison the CUDA
    context).
    """
    texts = req.get("texts")
    if texts is None:
        texts = req.get("text")
    if texts is None:
        return []
    if isinstance(texts, str):
        texts = [texts]
    out = []
    for t in texts:
        if not isinstance(t, str):
            raise ValueError(f"non-text item in the text list: {type(t).__name__}")
        t = t.strip()
        if t:
            out.append(t)
    return out


def _apply_tf32(enabled):
    """TF32 matmul: on Blackwell/Ampere it is a free speed-up for fp32 models like Chatterbox."""
    if not enabled:
        return
    try:
        import torch
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.set_float32_matmul_precision("high")
    except Exception:
        pass


def create_server(args):
    """Creates the HTTP server (`serve_forever` is NOT called; keeps it testable)."""
    import http.server

    state = {"model": None, "load_seconds": None, "fatal": None}
    _apply_tf32(getattr(args, "tf32", False))

    def ensure_model():
        if state["model"] is None:
            if args.backend == "piper":
                # for piper no "model" is held in memory: each request runs a short-lived piper.exe
                # (~0.27 s voice load). Only the binary + voice file are validated here.
                import shutil
                exe = args.piper or shutil.which("piper") or _local_piper("piper.exe")
                if exe and not os.path.exists(exe):
                    exe = shutil.which(exe)
                if not exe:
                    raise RuntimeError(f"piper not found (PATH or --piper): {args.piper}")
                args.piper_model = args.piper_model or _local_piper("voice.onnx")
                if not args.piper_model or not os.path.exists(args.piper_model):
                    raise RuntimeError(f"piper model not found: {args.piper_model}")
                state["model"] = {"piper": exe}
                state["load_seconds"] = 0.0
                return state["model"]
            if args.backend != "chatterbox":
                raise RuntimeError("server mode supports chatterbox and piper")
            t0 = time.perf_counter()
            state["model"] = load_chatterbox(lang=args.lang, device=args.device,
                                             t3_model=args.t3_model)
            state["load_seconds"] = round(time.perf_counter() - t0, 2)
        return state["model"]

    def _is_fatal(exc) -> bool:
        """A CUDA/accelerator error poisons the context: the server must be restarted."""
        s = f"{type(exc).__name__}: {exc}".lower()
        return "cuda" in s or "acceleratorerror" in s or "device-side assert" in s

    class Handler(http.server.BaseHTTPRequestHandler):
        # HTTP/1.0 (default): the connection closes on every request -> prevents rare
        # socket resets caused by keep-alive; no cost with 1 request per turn.
        def _send(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/") == "/health":
                fatal = state["fatal"]
                self._send(200, {"ok": fatal is None, "backend": args.backend,
                                 "loaded": state["model"] is not None,
                                 "load_seconds": state["load_seconds"],
                                 "fatal": fatal})
            else:
                self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/tts":
                self._send(404, {"ok": False, "error": "not found"})
                return
            n = int(self.headers.get("Content-Length", 0) or 0)
            try:
                req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception as exc:
                self._send(400, {"ok": False, "error": f"invalid JSON: {exc}"})
                return
            try:
                texts = server_texts(req)
            except Exception as exc:
                self._send(400, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            if not texts:
                self._send(400, {"ok": False, "error": "text is empty (text/texts)"})
                return
            out_dir = req.get("out_dir") or "."
            prefix = req.get("prefix") or "tts_"
            lang = req.get("lang", args.lang)
            voice_prompt = req.get("voice_prompt", args.voice_prompt)
            # per-request A/B: {"softg": false} -> 'ğ' respell off, {"tr_raw": true} -> all TR fixes off
            tr_raw = bool(req["tr_raw"]) if "tr_raw" in req else bool(getattr(args, "chatterbox_tr_raw", False))
            softg = bool(req["softg"]) if "softg" in req else not bool(getattr(args, "chatterbox_no_softg", False))
            try:
                model = ensure_model()
                os.makedirs(out_dir, exist_ok=True)
                results = []
                for i, t in enumerate(texts, 1):
                    out_i = os.path.join(out_dir, f"{prefix}{i}.wav")
                    try:
                        ensure_speakable(t)
                        if args.backend == "piper":
                            r = synth_piper(t, out_i, args.piper_model, args.piper)
                        else:
                            r = synth_chatterbox(t, out_i, lang, voice_prompt, args.device,
                                                args.exaggeration, args.cfg, args.t3_model, args.seed,
                                                not tr_raw, not tr_raw,
                                                model=model, guard=not getattr(args, "no_guard", False),
                                                softg=softg)
                        r["ok"] = True
                    except Exception as exc:
                        r = {"ok": False, "out": out_i,
                             "error": f"{type(exc).__name__}: {exc}"}
                        if _is_fatal(exc):
                            # CUDA context is broken: later requests fail too -> mark it
                            state["fatal"] = r["error"]
                    r["index"] = i
                    r["text"] = t[:200]
                    results.append(r)
                good = [r for r in results if r.get("ok")]
                total_audio = round(sum(o.get("audio_seconds", 0) or 0 for o in good), 3)
                total_gen = round(sum(o.get("tts_seconds", 0) or 0 for o in good), 3)
                self._send(200, {"ok": bool(good), "backend": args.backend, "batch": True,
                                 "count": len(results), "failed": len(results) - len(good),
                                 "load_seconds": state["load_seconds"],
                                 "total_tts_seconds": total_gen,
                                 "total_audio_seconds": total_audio,
                                 "rtf": round(total_gen / total_audio, 3) if total_audio else None,
                                 "results": results})
            except Exception as exc:
                self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

        def log_message(self, *a):  # silent (tqdm is already there)
            pass

    srv = http.server.ThreadingHTTPServer((args.host, args.port), Handler)
    srv.ensure_model = ensure_model   # to warm up at server start
    return srv


def serve(args) -> int:
    """Loads the model ONCE and serves it over HTTP (persistent process; no reload)."""
    try:
        srv = create_server(args)
        srv.ensure_model()   # load the model now (so the first request is not slow)
        if getattr(args, "backend", "") == "chatterbox":
            # Warm-up: the first generation pays CUDA graph/kernel setup (~5-12 s). Doing one
            # throwaway sentence here keeps the first real turn fast.
            try:
                import tempfile
                t_warm = time.perf_counter()
                wav = os.path.join(tempfile.gettempdir(), "altai-tts-warmup.wav")
                synth_chatterbox(
                    "Merhaba.", wav, lang=args.lang, device=args.device,
                    exaggeration=args.exaggeration, cfg=args.cfg, t3_model=args.t3_model,
                    seed=args.seed, tr_fix=not args.chatterbox_tr_raw,
                    respell=not args.chatterbox_tr_raw, softg=not args.chatterbox_no_softg,
                    guard=False)
                print(f"warmup {time.perf_counter() - t_warm:.1f} s", flush=True)
            except Exception as exc:  # noqa: BLE001 - a failed warm-up must not block the server
                print(f"warmup skipped: {type(exc).__name__}: {exc}", flush=True)
            # Give the memory reserved by the warm-up back to the driver (Chatterbox keeps a large
            # caching-allocator arena; without this the process sits ~3 GB above its real need).
            try:
                import torch
                torch.cuda.empty_cache()
                print(f"vram allocated {torch.cuda.memory_allocated() / 1e9:.2f} GB, "
                      f"reserved {torch.cuda.memory_reserved() / 1e9:.2f} GB", flush=True)
            except Exception:
                pass
    except Exception as exc:
        _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, args.json_out)
        return 3
    print(json.dumps({"ok": True, "serving": True, "backend": args.backend,
                      "host": srv.server_address[0], "port": srv.server_address[1]},
                     ensure_ascii=False))
    sys.stdout.flush()
    srv.serve_forever()
    return 0


# ------------------------------------------------------------------ CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Swappable TTS (Altai)")
    ap.add_argument("--backend", default="chatterbox", choices=["chatterbox", "voxcpm", "piper", "sapi"])
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--out", default=None, help="output wav in single mode (in batch mode use --out-prefix)")
    ap.add_argument("--lang", default=None, help="chatterbox multilingual: tr, en, ...")
    ap.add_argument("--voice-prompt", default=None, help="reference wav for cloning")
    ap.add_argument("--device", default="cuda", help="cuda | cpu")
    ap.add_argument("--tf32", action="store_true",
                    help="enable TF32 matmul (Ampere+): faster, negligible precision loss")
    ap.add_argument("--exaggeration", type=float, default=0.5)
    ap.add_argument("--cfg", type=float, default=0.5)
    ap.add_argument("--t3-model", default="v3", help="chatterbox multilingual checkpoint: v3 | v2")
    ap.add_argument("--chatterbox-tr-raw", action="store_true",
                    help="TURN OFF the chatterbox TR fixes (tr_fix+respell); for testing/AB")
    ap.add_argument("--chatterbox-no-softg", action="store_true",
                    help="TURN OFF only the 'ğ' respell ('ş'->'sh' stays); for A/B and rollback")
    ap.add_argument("--no-guard", action="store_true",
                    help="TURN OFF the long-tail (hallucination) compensation retry")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--voxcpm-model", default="Trendyol/Trendyol-TTS", help="voxcpm HF model id")
    ap.add_argument("--voxcpm-cfg", type=float, default=2.0)
    ap.add_argument("--voxcpm-steps", type=int, default=16)
    ap.add_argument("--no-optimize", action="store_true", help="disable voxcpm optimize")
    ap.add_argument("--piper", default=None)
    ap.add_argument("--piper-model", default=None)
    ap.add_argument("--json-out", default=None)
    # --- batch generation (the model is loaded ONCE) ---
    ap.add_argument("--batch-file", default=None,
                    help="one sentence per line; used together with --out-prefix")
    ap.add_argument("--out-prefix", default=None,
                    help="output prefix in batch mode: <prefix>1.wav, <prefix>2.wav ...")
    # --- persistent server (the model stays in memory; no reload) ---
    ap.add_argument("--serve", action="store_true",
                    help="run as an HTTP server (the model is loaded once); /health and /tts")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8082)
    args = ap.parse_args(argv)
    _apply_tf32(getattr(args, "tf32", False))

    if args.serve:
        return serve(args)

    # ---------------- BATCH MODE (chatterbox): single model load ----------------
    if args.batch_file:
        if not os.path.exists(args.batch_file):
            _json({"ok": False, "error": f"batch file not found: {args.batch_file}"}, args.json_out)
            return 2
        lines = _read_lines(args.batch_file)
        if not lines:
            _json({"ok": False, "error": "batch file is empty"}, args.json_out)
            return 2
        prefix = args.out_prefix or (os.path.splitext(args.out)[0] if args.out else None)
        if not prefix:
            _json({"ok": False, "error": "batch mode requires --out-prefix (or --out)"}, args.json_out)
            return 2
        os.makedirs(os.path.dirname(os.path.abspath(prefix)) or ".", exist_ok=True)
        try:
            if args.backend != "chatterbox":
                raise RuntimeError("batch mode currently supports chatterbox only")
            t0 = time.perf_counter()
            model = load_chatterbox(lang=args.lang, device=args.device, t3_model=args.t3_model)
            load_s = time.perf_counter() - t0
            outs = []
            for i, line in enumerate(lines, 1):
                out_i = f"{prefix}{i}.wav"
                try:
                    ensure_speakable(line)
                    r = synth_chatterbox(line, out_i, args.lang, args.voice_prompt, args.device,
                                         args.exaggeration, args.cfg, args.t3_model, args.seed,
                                         not args.chatterbox_tr_raw, not args.chatterbox_tr_raw,
                                         model=model, guard=not args.no_guard,
                                         softg=not args.chatterbox_no_softg)
                    r["ok"] = True
                except Exception as exc:  # if one sentence blows up, batch generation continues
                    r = {"ok": False, "out": out_i,
                         "error": f"{type(exc).__name__}: {exc}"}
                r["index"] = i
                r["text"] = line[:200]
                outs.append(r)
        except Exception as exc:
            _json({"ok": False, "backend": args.backend,
                   "error": f"{type(exc).__name__}: {exc}"}, args.json_out)
            return 3
        good = [o for o in outs if o.get("ok")]
        total_audio = round(sum(o.get("audio_seconds", 0) or 0 for o in good), 3)
        total_gen = round(sum(o.get("tts_seconds", 0) or 0 for o in good), 3)
        payload = {"ok": bool(good), "backend": args.backend, "batch": True,
                   "count": len(outs), "failed": len(outs) - len(good),
                   "load_seconds": round(load_s, 2),
                   "total_tts_seconds": total_gen, "total_audio_seconds": total_audio,
                   "rtf": round(total_gen / total_audio, 3) if total_audio else None,
                   "results": outs}
        _json(payload, args.json_out)
        return 0 if good else 3

    if not args.out:
        _json({"ok": False, "error": "--out is required (or --batch-file + --out-prefix)"}, args.json_out)
        return 2
    text = _read_text(args)
    if not text:
        _json({"ok": False, "error": "text is empty (pass --text or --text-file)"}, args.json_out)
        return 2

    try:
        if args.backend == "chatterbox":
            res = synth_chatterbox(text, args.out, args.lang, args.voice_prompt, args.device,
                                   args.exaggeration, args.cfg, args.t3_model, args.seed,
                                   not args.chatterbox_tr_raw, not args.chatterbox_tr_raw,
                                   guard=(not args.no_guard),
                                   softg=not args.chatterbox_no_softg)
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
