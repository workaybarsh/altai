# TTS-TR · Trendyol-TTS evaluation (2026-10-16)

This document collects the measurement and quality results for the Turkish TTS candidate
**Trendyol-TTS** (`openbmb/VoxCPM2` + Turkish LoRA, **MIT**, ~2B). Decision:
[`decisions.md`](decisions.md) → **#16**.

> ⚠️ The measurement was made on the development machine (RTX 5060 Ti **16 GB**), not on the project's
> target hardware. On the target 8 GB card the VRAM situation is even more critical.

## 1. Environment

| Field | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti (16,283 MiB) |
| Runtime | `%TEMP%\opencode\tts-venv` — `voxcpm 2.0.3`, `torch 2.11.0+cu128` |
| Model | `Trendyol/Trendyol-TTS` (in the HF cache; ~4.8 GB on disk) |
| Generation settings | `cfg_value=2.0`, `inference_timesteps=16`, `optimize=True` (model card recommendation) |
| Output | 48 kHz mono WAV |

## 2. Resource usage

| Metric | Value | Note |
|---|---|---|
| **VRAM (alloc after load)** | **5,248 MiB (~5.1 GB)** | `torch.cuda.memory_allocated` |
| **VRAM (peak alloc)** | **5,458 MiB (~5.3 GB)** | peak across all generation |
| **VRAM (peak reserved)** | **5,688 MiB (~5.6 GB)** | CUDA allocator reserve |
| nvidia-smi peak (including 510 MiB desktop) | 6,223 MiB | independent verification |
| Load (warm disk) | **17.5 s** | first load on a cold disk **575 s (~9.6 min)** |
| RTF | **2.9 – 3.3** | **~3× slower** than real time |

> **Critical:** ~5.6 GB VRAM conflicts with the project's rule that "the GPU belongs to the LLM only".
> Together with the resident 9B LLM (~6.6 GB) it needs ≈12 GB → **it does not fit on the 8 GB target
> card**. RTF ~3, meanwhile, directly tramples the `<1 s` target (TTS first audio ≤150 ms).

## 3. Turkish intelligibility (round-trip)

Method: the generated audio was transcribed back with `openai/whisper-large-v3-turbo`, **from the same
family as the project's STT**, and compared against the reference text with WER (word error rate).
Diacritics were folded for a fair comparison (reference in ASCII, the model produced correct Turkish).

| # | Reference | Round-trip (Whisper) | WER |
|---|---|---|---|
| 1 | Merhaba! Ben tamamen yerel calisan bir sesli asistanim. Bugun size nasil yardimci olabilirim? | Merhaba, ben tamamen yerel calisan bir **sessi** asistanım. Bugün size nasil yardımcı olabilirim. | **0.08** |
| 2 | Saat su anda on dort otuz. Istanbul'da hava bugun cok guzel ve gunesli. | Saat **şoğanda** 14.30 İstanbul'da hava bugün çok güzel ve güneşli. | **~0.43**\* |

\* In example 2 the number was written as `14.30` (digits), which inflated the WER; there is also a
genuine pronunciation corruption, **"şu anda" → "şoğanda"**. Samples: `logs\tts\trendyol-tr.wav`,
`logs\tts\trendyol-tr2.wav`.

**Comment:** generally **intelligible** and correct Turkish (diacritics included), but individual
words can show pronunciation corruption. Judging naturalness by ear is left to the user.

> ⚠️ **Critical warning:** the **input text of these samples was ASCII** (`bugun`, `nasil`, `yardimci`,
> `calisan`) and in the second sample `guneşli` went through console encoding. So these are **not a
> diacritic-handling test**. For a fair Turkish test the text must be supplied with **`ı ş ğ ü ö ç`**
> (UTF-8) and on Windows **`--text-file`** must be used instead of `--text` (the PowerShell argument
> corrupts it). The chat observation that "Trendyol suffers from the same problem" is therefore most
> likely **input-related**; it must be verified with correct Turkish text + A/B (see
> [`tts-benchmark.md`](tts-benchmark.md) §9).

## 4. Conclusion / decision

| Dimension | Assessment |
|---|---|
| Turkish quality | ✅ Intelligible (WER ~0.08 on a clean sample); occasional pronunciation error |
| License | ✅ MIT |
| VRAM | ❌ ~5.6 GB → violates the "GPU for the LLM only" rule; does not fit on an 8 GB card with the LLM |
| Latency | ❌ RTF ~3 → incompatible with the `<1 s` target |
| **Verdict** | **NOT the default for the live `<1 s` pipeline.** Added as an **offline/high-quality TR engine** via `tts-tools.py --backend voxcpm` (decision #16) |

## 5. Reproducing

```powershell
# Generation (needs a venv: voxcpm + torch-cu128 + soundfile)
python scripts\tts-trendyol-test.py                 # -> logs\tts\trendyol-tr.wav
python agent\tts-tools.py --backend voxcpm --text "Merhaba dunya" --out out.wav

# Round-trip (intelligibility) — needs Whisper
python tts-roundtrip.py --wav logs\tts\trendyol-tr.wav --ref "<reference text>"
```

> Setup: `pip install voxcpm soundfile` (CUDA-enabled torch separately). The model is downloaded from
> Hugging Face on first use (~4.8 GB).
