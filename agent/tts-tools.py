#!/usr/bin/env python3
"""tts-tools.py -- Takas edilebilir TTS araci (aybars_speaks).

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

Toplu (model BIR KEZ yuklenir; pipeline icin varsayilan):
  python agent/tts-tools.py --backend chatterbox --lang tr --batch-file cumleler.txt \
      --out-prefix logs/pipeline/tts_ --json-out logs/pipeline/tts_batch.json

Kalici sunucu (model bellekte kalir; her turda yukleme tekrari olmaz):
  python agent/tts-tools.py --serve --backend chatterbox --lang tr --device cuda --port 8082
  # GET  /health          -> {"ok":true,"loaded":true,...}
  # POST /tts  {"texts":["..."],"lang":"tr","out_dir":"<mutlak>","prefix":"tts_"}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import wave

# Konsol kodlamasi (Windows cp125x) UTF-8 disi karakterlerde `print`'i patlatabilir
# (or. LLM ciktisindaki emoji 😊). Bu, toplu uretimin TAMAMINI dusururdu -> stdout'u UTF-8'e cevir.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ------------------------------------------------------------------ yardimcilar

def _json(payload: dict, out_path_json: str | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        # stdout hala UTF-8 degilse (nadir) ham baytlara dus, cokmeyi onle
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


_TR_VOWELS = "aeıioöuü"


def tr_softg(s: str) -> str:
    """'ğ' (yumusak g) icin telaffuz ipucu.

    Kok neden (2026-10-18): Chatterbox grapheme sozlugunde 'ğ' VAR (U+011F), yani
    tokenizer taniyor; ama akustik model onu yanlis seslendiriyor -- 'çalıştığı' ->
    kulakta 'çalıştı ki'. (Ayni sozlukte NFKD ile ayrilmis 'g'+breve YOK, bu yuzden
    tr_fix'in NFKD'yi kapatmasi dogru.)

    Turkce yumusak-g kurali yaziya cevrilir:
      - iki unlu arasinda          -> 'y'      (değil -> deyil, çalıştığı -> çalıştıyı)
      - unluden sonra, onsoz/sonda -> onceki unlu tekrarlanir (dağ -> daa, yağmur -> yaamur)
      - onsozden sonra (nadir)     -> 'g'      (mağdur -> magdur)
    """
    if "ğ" not in s and "Ğ" not in s:
        return s
    out = []
    for i, ch in enumerate(s):
        if ch in "ğĞ":
            prev = s[i - 1] if i else ""
            nxt = s[i + 1] if i + 1 < len(s) else ""
            # dikkat: '' her string'in alt dizisidir -> bos tarafi ayrica ele
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
    """Chatterbox TR icin fonetik ipucu: 'ş' -> 'sh', 'ğ' -> tr_softg().

    'ş' (//ʃ//) icin: model 'ş' sesini yanlis uretiyordu (ör. 'çalışan' -> 'çalıyan');
    'sh' digrafi /ʃ/ olarak okunur. Kulak testiyle dogrulandi (2026-10-17).
    'ğ' icin: tr_softg() (bkz. oradaki kok neden notu); `softg=False` ile kapatilir
    (A/B ve geri donus icin -- CLI: --chatterbox-no-softg).
    """
    if softg:
        s = tr_softg(s)
    return s.replace("ş", "sh").replace("Ş", "sh")


# ------------------------------------------------------------------ chatterbox

def expected_audio_seconds(text, chars_per_sec=14.0, min_seconds=0.4):
    """Kaba konusma suresi beklentisi (TR ~14 harf/sn). Harf/rakam yoksa 0."""
    n = sum(1 for ch in text if ch.isalnum())
    if n == 0:
        return 0.0
    return max(min_seconds, n / float(chars_per_sec))


def ensure_speakable(text):
    """Metin uretime uygun mu? Harf/rakam yoksa (emoji/sembol-only) ValueError.

    Bos cumleler zaten filtrelerden gecer (pipeline '\\p{L}|\\p{N}', `_read_lines`,
    `server_texts`); bu kontrol ARTAN sembol-only girdiyi yakalar: Chatterbox boyle
    girdide patliyordu (IndexError: max() non-zero size; uzun bozuk metinde CUDA
    device-side assert -> baglam zehirlenmesi). Toplu modda oge bazli, sunucuda
    istek-bazli hata doner; digerleri uretilmeye devam eder.
    """
    if not any(ch.isalnum() for ch in text):
        raise ValueError("metin gecerli harf icermiyor (emoji/sembol?)")
    return text


def audio_guard_limit(text, factor=3.0, slack=2.0, chars_per_sec=14.0):
    """Uretilen ses bu siniri asarsa 'uzun kuyruk / halusinasyon' sayilir.

    sinir = max(factor * beklenen, beklenen + slack). Kisa cumlede (or. "Merhaba!")
    beklenen ~0,5 sn -> sinir 2,5 sn; 9,6 sn'lik tasma yakalanir, 1,9 sn'lik normal
    varyans gecer. (Dokuman: tts-kiyaslama.md §3/§9.3, tts_batch.json'daki 9,6 sn vaka.)
    """
    exp = expected_audio_seconds(text, chars_per_sec)
    return max(factor * exp, exp + slack)


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
                     respell=True, model=None, guard=True, softg=True):
    """Chatterbox ile tek cumle sentezler.

    `guard=True` (varsayilan): uretilen ses `audio_guard_limit` sinirini asarsa ayni metni
    BIR KEZ daha uretir ve **kisa olani** tutar (uzun-kuyruk/halusinasyon telafisi;
    Chatterbox'in kendi `alignment_stream_analyzer` guard'i her zaman yetmiyor).
    Sonuca `retried` / `audio_limit_seconds` alanlari eklenir.
    """
    import torch

    # Cok dilli (MTL) model mi? lang verilirse evet. (load_chatterbox ile ayni kural;
    # burada da tanimli olmali -- aksi halde asagidaki `if uses_mtl` NameError verir.)
    uses_mtl = bool(lang)

    if model is None:
        model = load_chatterbox(lang=lang, device=device, t3_model=t3_model)

    out_dir = os.path.dirname(os.path.abspath(out_wav))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # TR icin duzeltmeler OTOMATIK (lang='tr'): tokenizer NFKD yamasi + 'ş'->'sh' + 'ğ' respell.
    # (kapatmak icin tr_fix/respell = False; CLI: --chatterbox-tr-raw, 'ğ' icin --chatterbox-no-softg)
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
        # API surumleri arasinda parametre adlari degisebilir: once zengin, olmazsa sade dene.
        t0 = time.perf_counter()
        try:
            wav = model.generate(text, **{**kwargs, "exaggeration": exaggeration, "cfg_weight": cfg})
        except TypeError:
            try:
                wav = model.generate(text, **{**kwargs, "exaggeration": exaggeration})
            except TypeError:
                wav = model.generate(text, **kwargs)
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
        # Uzun kuyruk: farkli ornekleme ile bir kez daha uret, kisa olani tut.
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
        res["first_audio_seconds"] = res["audio_seconds"]   # her iki dalda da raporlanir
        res["guard_extra_seconds"] = res2["tts_seconds"]    # telafi maliyeti (olcum icin)
        if res2["audio_seconds"] < res["audio_seconds"]:
            os.replace(retry_path, out_wav)
            # DIKKAT: dosya artik out_wav yolunda; `out` retry yolunu gostermemeli
            # (pipeline res.out'u Test-Path ile kullaniyor -> yanlissa cumle dusuyordu).
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


# ------------------------------------------------------------------ HTTP sunucu (kalici model)

def server_texts(req: dict):
    """`/tts` isteğinden cumle listesini cikarir (tek metin / dizi / 'texts'/'text').

    Not: `ConvertTo-Json` tek elemanli diziyi bazen duz metne indirir -> burada normalize edilir.
    Yalnizca **str** ogeler kabul edilir; aksi halde 400 ile reddedilir (bozuk girdi, CUDA
    baglamini zehirleyebiliyor).
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
            raise ValueError(f"metin listesinde metin olmayan oge: {type(t).__name__}")
        t = t.strip()
        if t:
            out.append(t)
    return out


def create_server(args):
    """HTTP sunucusunu olusturur (`serve_forever` CAGRILMAZ; test edilebilir)."""
    import http.server

    state = {"model": None, "load_seconds": None, "fatal": None}

    def ensure_model():
        if state["model"] is None:
            if args.backend == "piper":
                # piper'da "model" bellekte tutulmaz: her istek kisa omurlu piper.exe calistirir
                # (~0,27 sn ses yukleme). Burada yalnizca ikili + ses dosyasi dogrulanir.
                import shutil
                exe = args.piper or shutil.which("piper")
                if not exe or not os.path.exists(exe):
                    raise RuntimeError(f"piper bulunamadi (PATH ya da --piper): {args.piper}")
                if not args.piper_model or not os.path.exists(args.piper_model):
                    raise RuntimeError(f"piper modeli bulunamadi: {args.piper_model}")
                state["model"] = {"piper": exe}
                state["load_seconds"] = 0.0
                return state["model"]
            if args.backend != "chatterbox":
                raise RuntimeError("sunucu modu chatterbox ve piper icin destekler")
            t0 = time.perf_counter()
            state["model"] = load_chatterbox(lang=args.lang, device=args.device,
                                             t3_model=args.t3_model)
            state["load_seconds"] = round(time.perf_counter() - t0, 2)
        return state["model"]

    def _is_fatal(exc) -> bool:
        """CUDA/accelerator hatasi baglami zehirler: sunucu yeniden baslatilmali."""
        s = f"{type(exc).__name__}: {exc}".lower()
        return "cuda" in s or "acceleratorerror" in s or "device-side assert" in s

    class Handler(http.server.BaseHTTPRequestHandler):
        # HTTP/1.0 (varsayilan): her istekte baglanti kapanir -> keep-alive kaynakli
        # nadir socket reset'lerini onler; turn basina 1 istek icin maliyet yok.
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
                self._send(404, {"ok": False, "error": "bulunamadi"})

        def do_POST(self):
            if self.path.rstrip("/") != "/tts":
                self._send(404, {"ok": False, "error": "bulunamadi"})
                return
            n = int(self.headers.get("Content-Length", 0) or 0)
            try:
                req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception as exc:
                self._send(400, {"ok": False, "error": f"gecersiz JSON: {exc}"})
                return
            try:
                texts = server_texts(req)
            except Exception as exc:
                self._send(400, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            if not texts:
                self._send(400, {"ok": False, "error": "metin bos (text/texts)"})
                return
            out_dir = req.get("out_dir") or "."
            prefix = req.get("prefix") or "tts_"
            lang = req.get("lang", args.lang)
            voice_prompt = req.get("voice_prompt", args.voice_prompt)
            # istek basina A/B: {"softg": false} -> 'ğ' respell kapali, {"tr_raw": true} -> tum TR duzeltmeleri kapali
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
                            # CUDA baglami bozuldu: sonraki istekler de basarisiz olur -> isaretle
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

        def log_message(self, *a):  # sessiz (tqdm zaten var)
            pass

    srv = http.server.ThreadingHTTPServer((args.host, args.port), Handler)
    srv.ensure_model = ensure_model   # sunucu acilisinda isitmak icin
    return srv


def serve(args) -> int:
    """Modeli BIR KEZ yukler ve HTTP ile hizmet verir (kalici surec; yukleme tekrari yok)."""
    try:
        srv = create_server(args)
        srv.ensure_model()   # modeli istekleri beklemeden simdi yukle (ilk istek yavas olmasin)
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
    ap = argparse.ArgumentParser(description="Takas edilebilir TTS (aybars_speaks)")
    ap.add_argument("--backend", default="chatterbox", choices=["chatterbox", "voxcpm", "piper", "sapi"])
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--out", default=None, help="tekli modda cikti wav (toplu modda --out-prefix ile)")
    ap.add_argument("--lang", default=None, help="chatterbox coklu dil: tr, en, ...")
    ap.add_argument("--voice-prompt", default=None, help="klonlama icin referans wav")
    ap.add_argument("--device", default="cuda", help="cuda | cpu")
    ap.add_argument("--exaggeration", type=float, default=0.5)
    ap.add_argument("--cfg", type=float, default=0.5)
    ap.add_argument("--t3-model", default="v3", help="chatterbox coklu dil checkpoint: v3 | v2")
    ap.add_argument("--chatterbox-tr-raw", action="store_true",
                    help="chatterbox TR duzeltmelerini KAPAT (tr_fix+respell); test/AB icin")
    ap.add_argument("--chatterbox-no-softg", action="store_true",
                    help="yalniz 'ğ' respell'ini KAPAT ('ş'->'sh' kalir); A/B ve geri donus icin")
    ap.add_argument("--no-guard", action="store_true",
                    help="uzun-kuyruk (halusinasyon) telafi retry'sini KAPAT")
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
    # --- kalici sunucu (model bellekte kalir; yukleme tekrari yok) ---
    ap.add_argument("--serve", action="store_true",
                    help="HTTP sunucusu olarak calis (model bir kez yuklenir); /health ve /tts")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8082)
    args = ap.parse_args(argv)

    if args.serve:
        return serve(args)

    # ---------------- TOPLU MOD (chatterbox): model tek yukleme ----------------
    if args.batch_file:
        if not os.path.exists(args.batch_file):
            _json({"ok": False, "error": f"batch dosyasi bulunamadi: {args.batch_file}"}, args.json_out)
            return 2
        lines = _read_lines(args.batch_file)
        if not lines:
            _json({"ok": False, "error": "batch dosyasi bos"}, args.json_out)
            return 2
        prefix = args.out_prefix or (os.path.splitext(args.out)[0] if args.out else None)
        if not prefix:
            _json({"ok": False, "error": "toplu modda --out-prefix (ya da --out) gerekli"}, args.json_out)
            return 2
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
                try:
                    ensure_speakable(line)
                    r = synth_chatterbox(line, out_i, args.lang, args.voice_prompt, args.device,
                                         args.exaggeration, args.cfg, args.t3_model, args.seed,
                                         not args.chatterbox_tr_raw, not args.chatterbox_tr_raw,
                                         model=model, guard=not args.no_guard,
                                         softg=not args.chatterbox_no_softg)
                    r["ok"] = True
                except Exception as exc:  # tek cumle patlarsa toplu uretim devam eder
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
        _json({"ok": False, "error": "--out gerekli (ya da --batch-file + --out-prefix)"}, args.json_out)
        return 2
    text = _read_text(args)
    if not text:
        _json({"ok": False, "error": "metin bos (--text ya da --text-file ver)"}, args.json_out)
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
