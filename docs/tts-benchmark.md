# TTS benchmark · Turkish (Chatterbox-centric, excluding Fish)

> **Note (2026-11-19):** the CPU TTS engine evaluated in the early sections was dropped; the project
> now uses **Chatterbox only**. Those measurements are kept as historical evidence.

This document compares **Chatterbox** with other modern engines for Turkish TTS. **Fish S2 Pro is out
of scope** (decision #15 — it is not entering the project).

## 1. Source and scope

| Field | Value |
|---|---|
| Primary source | **arXiv:2610.06057v1** — *"A Comprehensive Objective Evaluation of Modern Text-to-Speech for Turkish"* (Sestek, 05 Oct 2026) |
| Method | 100 short + 100 medium + 100 long Turkish sentences; **18 objective metrics** + natural ("gold") reference anchor |
| Systems compared | **Chatterbox** (zero-shot), **CosyVoice** (finetuned, raw text), **OmniVoice** (finetuned + zero-shot), **VoxCPM2** (zero-shot), **VITS** (finetuned, no cloning) |
| Excluded | **Fish S2 Pro** |
| Code/results | `github.com/EmreOzkose/tr-tts-eval` |

> **Config note:** Chatterbox and VoxCPM2 are **zero-shot** only; CosyVoice/OmniVoice are **finetuned**;
> VITS is **finetuned** and does not clone. The VoxCPM2 column is the **multilingual base** model; the
> project's candidate is **Trendyol-TTS = VoxCPM2 + Turkish LoRA** (finetuned), so it is expected to be
> **better** than the base in Turkish.

## 2. Overall averages (full test set)

> In each row the best **synthetic** system is bold; Gold is only an anchor, not a competitor.

| Metric (direction) | Chatterbox | CosyVoice | OmniVoice (ZS) | **VoxCPM2** | VITS | Gold |
|---|---|---|---|---|---|---|
| **speaker-similarity ↑** | 0.873 | 0.878 | 0.870 | **0.881** | 0.875 | 0.894 |
| UTMOS-v2 (naturalness) ↑ | 3.092 | **3.441** | 3.105 | 2.886 | 3.064 | 3.079 |
| DNSMOS-Pro ↑ | 3.564 | 3.770 | 3.808 | 3.902 | **4.225** | 3.601 |
| SQUIM SI-SDR (intelligibility) ↑ | 24.94 | 25.74 | **28.52** | 27.05 | 25.21 | 24.46 |
| SQUIM STOI ↑ | 3.762 | 3.753 | **3.926** | 3.788 | 3.690 | 3.639 |
| WhisQA ↑ | 4.341 | **4.720** | 4.448 | 4.575 | 4.515 | 4.331 |
| SCOREQ ↑ | 3.697 | **4.063** | 4.059 | 3.907 | 3.740 | 3.782 |
| NatScore ↑ | −1.447 | −1.233 | −1.128 | **−0.917** | −1.616 | −1.384 |
| Brouhaha ↑ | 50.13 | 60.25 | 58.07 | **62.47** | 59.51 | 55.31 |
| AudioBox-PQ ↑ | 7.643 | 7.793 | **7.831** | 7.793 | 7.654 | 7.657 |
| TTSDS ↑ | 77.01 | **79.74** | 78.58 | 79.16 | 78.28 | 77.86 |

**Reading:** The leaders split by metric family —
**VITS** on DNSMOS-Pro, **OmniVoice(ZS)** on intelligibility/signal (SQUIM), **CosyVoice** on
naturalness/distribution (UTMOS/WhisQA/SCOREQ/TTSDS), **VoxCPM2** on speaker similarity + NatScore +
Brouhaha. 👉 **Chatterbox wins no metric at all.**

## 3. Sentence length — critical for a voice assistant (**short** sentences)

A voice assistant typically produces **short** replies (0–50 characters). The paper's most striking
finding: **Chatterbox collapses on short sentences.**

| Short sentence (0–50 chars) | Chatterbox | CosyVoice | OmniVoice (ZS) | VoxCPM2 | Gold |
|---|---|---|---|---|---|
| speaker-similarity ↑ | 0.825 | 0.814 | 0.818 | **0.830** | 0.827 |
| SQUIM SI-SDR ↑ | **20.36** ⬅ worst | 26.03 | **28.54** | 26.91 | 25.80 |
| DNSMOS-Pro ↑ | **3.335** ⬅ worst | 3.621 | 3.784 | **3.805** | 3.412 |
| WhisQA ↑ | **3.607** ⬅ worst | 4.546 | 4.118 | 4.307 | 4.058 |
| UTMOS-v2 ↑ | 2.766 | **3.350** | 2.927 | 2.776 | 2.909 |
| NatScore ↑ | **−2.221** ⬅ worst | −1.250 | −1.675 | −1.556 | −1.501 |

> Paper: *"Deployments dominated by short prompts (voice assistants, IVR, command responses) should
> weight the short-group results far more heavily than the overall averages."*
> CosyVoice/OmniVoice/VoxCPM2 are length-robust; **Chatterbox only recovers on medium/long inputs.**

## 4. Long-form stability (identity + naturalness drift)

| System | Identity std ↓ | Identity drift → 0 | Identity Δfirst-last → 0 | Naturalness drift | Naturalness Δfirst-last |
|---|---|---|---|---|---|
| **Chatterbox (ZS)** | 0.0325 | −0.0391 | **−0.0613** (worst) | **−0.149** | **−0.321** (worst) |
| **CosyVoice** | **0.0212** | **−0.0077** | **−0.0094** | −0.041 | −0.067 |
| OmniVoice (ZS) | 0.0282 | −0.0184 | −0.0276 | −0.063 | −0.090 |
| **VoxCPM2 (ZS)** | 0.0233 | −0.0115 | **−0.0003** (≈zero) | −0.001 | −0.039 |
| VITS | 0.0226 | −0.0125 | −0.0175 | −0.118 | −0.147 |

**Reading:** Most stable in identity are **CosyVoice** and **VITS**; **VoxCPM2** has almost zero identity
drift (ideal for long text). **Chatterbox** is the least stable on both axes (naturalness drops
noticeably).

## 5. The project's own measurements (manual, this machine)

| Engine | VRAM | RTF | TR intelligibility (round-trip WER) |
|---|---|---|---|
| **Trendyol-TTS** (=VoxCPM2 + TR LoRA) | ~5.3–5.6 GB | ~3.0 (~3× slower than real time) | ~0.08 (clean sample) |
| Chatterbox | **~3.3 GB** (measured) | **RTF ~1.1** (measured) | ✅ good (with tr-fix+respell) |
| SAPI | 0 (CPU) | very fast | ❌ **no Turkish voice on this machine** (only Zira en-US) |

> **Historical note:** a CPU TTS engine was evaluated here (RTF ~0.19, round-trip WER 0.000) and was
> fast, but robotic. It was **dropped on 2026-11-19**; the project uses **Chatterbox only**.

## 6. Conclusion and impact on the project

| Need | Winner (per the evidence) | Chatterbox |
|---|---|---|
| Naturalness / perceived quality | **CosyVoice** | ✗ (wins no metric) |
| **Speaker similarity / clone** | **VoxCPM2** | ✗ |
| Intelligibility / signal cleanliness | **OmniVoice (ZS)** / VITS | ✗ |
| **Short sentence (voice assistant)** | CosyVoice / OmniVoice / VoxCPM2 | ✗ **collapses** |
| Long-form identity stability | **VoxCPM2** (≈0 drift) | ✗ |
| Long-form naturalness stability | **CosyVoice** | ✗ |

**Reflection on our decisions:**
1. **Chatterbox is eliminated as the primary Turkish engine** — it wins no metric, collapses on short
   sentences, and its naturalness degrades over time. (This independently confirms our finding.)
2. **The VoxCPM2 family (→ Trendyol-TTS) is the strongest candidate for Turkish** (clone/similarity +
   NatScore + long-form stability). However, it is still too heavy for **live `<1 s`** (RTF ~3,
   ~5.6 GB VRAM) → offline engine (decision #16).
3. **CosyVoice** is best on naturalness and length-robust → **first fallback candidate for live TR**
   (speed/VRAM must be measured). **OmniVoice(ZS)** is interesting for intelligibility (can be watched
   as a Turkish cloning candidate).
4. VITS does not clone; in a voice-focused project it is only a reference point.

> ⚠️ This source is entirely based on **objective metrics** (a single Turkish test set, limited
> speakers). Absolute values must be read against gold; an **ear (MOS/preference) test** is mandatory
> for a final verdict.

## 7. References

- Özköse, Y. E., Kahraman, A., Haznedaroğlu, A. (Sestek). *A Comprehensive Objective Evaluation of
  Modern Text-to-Speech for Turkish Using Speech Quality Assessment Models.* **arXiv:2610.06057v1**, 2026.

## 8. Source usage (research; no local runs)

> This section is compiled from **published sources** (not yet measured on our own hardware). Goal: to
> compare the engines' **parameter / VRAM / speed / license** profiles.

| Engine | Parameters | VRAM (inference) | RTF (high-end GPU) | First audio (streaming) | TR zero-shot | License |
|---|---|---|---|---|---|---|
| **Chatterbox Multilingual v3** | 0.5B | **~2 GB** (min) – ~4 GB | **~0.05–0.2** | yes (chunked) | ✅ (but diacritic bug) | **MIT** |
| **VoxCPM2** (→ Trendyol-TTS) | 2B (2.3B) | ~5 (bf16) – ~8 GB | ~0.30 (4090) / ~0.13 Nano-vLLM | yes (chunk) | ✅ | Apache-2.0 |
| **CosyVoice 1** (CosyVoice-300M) | 0.3B | ~2–6 GB (source) | old/mid (2024-07) | ~150 ms | ❌ no TR (5 languages: zh/en/ja/ko/yue) | Apache-2.0 |
| **CosyVoice 2** | 0.5B | ~4–8 GB (source) | good (streaming) | **~150 ms** | ❌ no TR (zh/en/ja/ko/yue) → finetune | Apache-2.0 |
| **CosyVoice 3** (Fun-CosyVoice3-0.5B) | 0.5B (1.5B **not open**) | ~4–10 GB (source) | **SOTA (at 0.5B)** | **~150 ms** | ❌ **no TR** (9 languages: zh/en/ja/ko/de/es/fr/it/ru) → finetune | Apache-2.0 |
| **OmniVoice** | 0.81B | **~2.3 GB** (fp16) | **~0.04** (L40S) / ~0.025 (H100) | NAR (batch) | ✅ (600+ languages) | Apache-2.0 |

Sources: VoxCPM2 README/technical report (arXiv:2606.06928) + voxcpm.readthedocs; OmniVoice paper
(arXiv:2604.00688) + k2-fsa/OmniVoice + L40S/Jetson measurements; CosyVoice2 (arXiv:2412.10117) +
fun-audiollm; Chatterbox (Resemble AI, GitHub/HF). VRAM figures vary with model cards/releases;
**the exact value must be measured on our own card**.

**Chatterbox stands out:** smallest (0.5B), **lowest VRAM (~2 GB)**, MIT, and RTF <1 (faster than real
time). Consistent with our observation: **quality is good**, the only problem is Turkish characters.

**CosyVoice 3 (2025-05, arXiv:2505.17589):** 0.5B open (**1.5B only in the paper — no weights**),
Apache-2.0, **native streaming ~150 ms**, 25 Hz, ~4× with TensorRT-LLM. SOTA quality at 0.5B
(test-zh CER 1.21 / test-en WER 2.24). **But the official languages are 9** (zh/en/ja/ko/de/es/fr/it/ru
+ 18 Chinese dialects) → **NO Turkish** (requested via GitHub **#1904**). For TR **finetuning is
mandatory**; the Sestek benchmark also made CosyVoice the naturalness leader in TR by **finetuning** it.
So it is **not a zero-shot TR engine**, but "the strongest candidate to finetune for TR".

### 8.1 VoxCPM2 RTF discrepancy (important open question)

| Source | RTF |
|---|---|
| Official (RTX 4090, 10 steps, torch.compile) | ~0.30 |
| **Our measurement (RTX 5060 Ti, 16 steps, `optimize=True`)** | **~3.0** (10× slower) |

Likely causes: (a) 16 steps vs 10 steps (~1.6×); (b) **`torch.compile`/Triton may not be kicking in
on Windows/sm_120** (VoxCPM FAQ), falling back to pure eager mode; (c) the 5060 Ti is slower than a
4090. So **our RTF ~3 measurement is probably pessimistic, not optimistic**; it must be **re-measured**
with `inference_timesteps=10` and the compilation verified to work.

## 9. The Chatterbox Turkish problem and its fix

**Problem (with evidence):** Chatterbox's multilingual tokenizer processes Turkish as **graphemes**;
`ç, ş, ü, ğ, ö` (and `ı`) are either skipped or mispronounced — exactly the user's observation
("bugün→bugun", "nasıl→nasil"). Official records: resemble-ai/chatterbox **#261**, HF
**discussion #33** ("Turkish characters skipped"), and #550 (phoneme/IPA input requested — not yet
available).

**Why it happens:** if the reference voice is not Turkish + the tokenizer does not know the diacritics,
letters are dropped and stress shifts to the wrong place. Turkish's **agglutinative** structure and
pronunciation rules (soft ğ, dotless ı, vowel harmony) break down in a grapheme model.

**Root cause (at code level, confirmed):** the `chatterbox` multilingual tokenizer
(`MTLTokenizer.preprocess_text`) **always applies `NFKD`** to the text; `generate()` does **not**
disable this with `nfkd_normalize=False`. NFKD splits `ş/ğ/ü/ö/ç` into *base letter + combining mark*
(`ş`→`s`+U+0327, `ü`→`u`+U+0308). If the vocabulary lacks these combining marks, **the diacritic is
lost** (`ş`→`s`, `ü`→`u`). Also `lower()` is not Turkish-aware (`I`→`i`, `İ`→`i`+dot). External
record: `jamiepine/voicebox` **#846** — *"Incorrect pronunciation of Turkish vowels (ı, ö, ü)"*.

**Patch applied (offline, tested):** `agent/tts-tools.py` → `install_tr_tokenizer_fix()` + `tr_lower()`.
With `--backend chatterbox --lang tr --chatterbox-tr-fix`, **NFKD is disabled** for TR
(NFC/precomposed preserved) and **Turkish lowercasing** is applied; other languages are unaffected.
`python -m pytest -q` → **19 tests** (2 new). ⏳ The effect (audio) will be measured **when the GPU is
free**.

> 📌 In the same source a user reports that **XTTS-v2** is **clearly better** than Chatterbox in Turkish
> (ı/ö/ü + word separation + prosody). XTTS-v2 (non-commercial license, slow on CPU) may need to be
> **re-evaluated** for TR.

### 9.1 A/B plan to run when the GPU is free

Goal: "is the problem the input (ASCII), the engine (tokenizer), or does the patch fix it?" Same
sentence, 4 conditions:

```powershell
# texts (UTF-8, via --text-file) :
#  A) correct TR : "Merhaba! Ben tamamen yerel çalışan bir sesli asistanım. Bugün size nasıl yardımcı olabilirim?"
#  B) ASCII      : "Merhaba! Ben tamamen yerel calisan bir sesli asistanim. Bugun size nasil yardimci olabilirim?"

$py = "$env:TEMP\opencode\tts-venv\Scripts\python.exe"
# 1) correct TR + patch
& $py agent\tts-tools.py --backend chatterbox --lang tr --chatterbox-tr-fix --text-file logs\tts\ab-tr.txt  --out logs\tts\cb-tr-fix.wav
# 2) correct TR + no patch
& $py agent\tts-tools.py --backend chatterbox --lang tr                      --text-file logs\tts\ab-tr.txt  --out logs\tts\cb-tr-raw.wav
# 3) ASCII + patch
& $py agent\tts-tools.py --backend chatterbox --lang tr --chatterbox-tr-fix --text-file logs\tts\ab-ascii.txt --out logs\tts\cb-ascii-fix.wav
```

Then measure each WAV with **Whisper round-trip + WER** (see the method in `docs/tts-tr-results.md` §3)
and listen by ear. Expectation: if **(1) ≫ (2)** the patch works; if **(1) ≈ (3)** the problem was only
the input.

> ⚠️ Prerequisite: Chatterbox weights are downloaded on the first run (~2 GB, `ResembleAI/chatterbox`).

### 9.2 Ear test + vocabulary inspection (2026-10-17)

Samples generated from the same **correct Turkish** sentence were listened to:

| Result | Sample |
|---|---|
| ✅ **Good** | **Chatterbox (patch on)**, **Trendyol (VoxCPM2 + TR LoRA)** |
| ❌ Broken | Chatterbox **without the patch**, **ASCII** samples, old (ASCII) Trendyol samples |

- ⚠️ **The only remaining flaw:** Chatterbox turns "**çalışan**" into "**çalıyan**" (i.e. **"ş"** is
  wrong). Whisper round-trip also heard "çalayan" → **ear + ASR agree**.
- **Tokenizer vocabulary** (`grapheme_mtl_merged_expanded_v1.json`, 2454 tokens): `ş, ç, ğ, ı, ö, ü, â`
  **and** the combining marks (`U+0327/U+0308/U+0306/U+0307`) are **present**. → So the problem is not
  "the letter is missing": **NFKD** splits the text into **two tokens** such as `s`+cedilla, and the
  model does not read it as a single letter. **The patch** preserves the precomposed **single token** →
  that is where the improvement comes from.
- **The leftover "ş" → an acoustic error** (the model's Turkish phoneme quality), not the tokenizer.
  Fixes: (a) a small **respell / G2P-lite** layer (like ş→"sh"), (b) Turkish **fine-tune / LoRA**.

**Decision (by ear test, 2026-10-17):** **both are good** — **Chatterbox (tr-fix + respell)** and
**Trendyol**. The other variants (no patch / ASCII) were eliminated. The difference:
- **Chatterbox** → **light + fast** (measured: ~3.3 GB, RTF ~1.1) ⇒ **live-path candidate** (good in
  English too).
- **Trendyol** → **native TR** but **heavy + slow** (~5.6 GB, RTF ~3.4) ⇒ **offline / high quality**.

### 9.3 Respell fix for "ş" (2026-10-17)

For the only remaining error ("çalışan"→"çalıyan"), **respell** was tried: **`ş` → `sh`**.
- `respell-base` (normal "ş") → still "çalıyan" ❌
- **`respell-main-sh2` (ş→sh)** → **correct** ✅ (ear test)

→ Preprocessing was added to `agent/tts-tools.py` **automatically**: with
`--backend chatterbox --lang tr`, **tr_fix + respell are applied on their own** (to disable, use
`--chatterbox-tr-raw`). Offline test: `python -m pytest -q` → **20 tests**.

> Note: in some generations the model warns "forcing EOS" and can garble a word (generation variance) →
> on a suspicious sample the same sentence is generated again. **2026-10-17: this is now in code** —
> the long-tail guard (duration limit + 1 retry) [`§11`](#11-long-tail-hallucination-guard-2026-10-17).
> Respell fixes "ş"; **for ğ it was needed on 2026-10-18 and was added** →
> [`§9.4`](#94-respell-fix-for-ğ--measured-verification-2026-10-18).

**Solution paths (easy to heavy):**

| Path | What it does | Effort | Expectation |
|---|---|---|---|
| **1. UTF-8 text + current version** | Correct Turkish characters + tokenizer fixes (multilingual v2/v3; "problem solved" note on HF) | Low | Partial improvement |
| **2. Turkish pre-normalisation / respelling (G2P-lite)** | Convert the text into the form the model reads correctly (e.g. `ç→ch`, `ş→sh`, `ı→ı`→phonetic hint); a lexicon for problematic words | Medium | **Most practical**; measured with CER/WER |
| **3. espeak-ng based G2P** | Convert Turkish text to IPA/phonemes | Medium | Chatterbox **does not accept phonemes** (#550) → limited for now |
| **4. Turkish fine-tune / LoRA** | Train Chatterbox on Turkish data (as Trendyol did with VoxCPM2) | High | Best result, but costly |

**Conclusion:** it would be **wrong** to consider Chatterbox "eliminated for Turkish" — the problem is
**not quality but text preprocessing**. Since it is the cheapest (0.5B, ~2 GB, MIT) and fastest
(RTF <1) engine, it can be seriously reclaimed with **Turkish pre-normalisation (path 2)**. Also, part
of the "collapses on short sentences" finding in the benchmark above may stem from this
diacritic/tokenizer bug.

### 9.4 Respell fix for "ğ" + measured verification (2026-10-18)

**User finding (by ear):** the word `çalıştığı` came out like "çalıştı ki", i.e. **`ğ` was broken**.
**Objective verification:** we round-tripped the audio with whisper turbo and compared it with the
source text:

```
source : Tam yerel çalıştığı için cevaplarım hem hızlı hem de gizli.
heard  : Tam yarar  çalıştı ki işin cevaplarım hem hızlı hem de gizli.      (Chatterbox, old patch)
```

**Root cause (measured, no GPU needed):** in Chatterbox's grapheme vocabulary
(`grapheme_mtl_merged_expanded_v1.json`, 2.454 tokens) **`ğ` (U+011F) IS present**, but its
NFKD-decomposed form (`g`+breve) is **not** — the same holds for ş/ü/ö/ç/ı:

| Letter | NFC (composed) | NFKD (decomposed) |
|---|---|---|
| ş, ğ, ü, ö, ç, ı, İ | ✅ present | ❌ missing |

So `tr_fix` disabling NFKD is **correct**; the tokenizer does know `ğ` — the error is made by the
**acoustic model**. The fix is the sibling of the `ş→sh` patch: **a phonetic hint for `ğ`**
(`tr_softg()`):

```
ğ  between two vowels             -> y               değil -> deyil, çalıştığı -> çalıştıyı
ğ  after a vowel, consonant/final -> previous vowel  dağ -> daa, yağmur -> yaamur, öğretmen -> ööretmen
ğ  after a consonant (rare)       -> g               (in Turkish ğ always follows a vowel; safety net only)
```

Apply order: `tr_softg()` → then `ş→sh`. To disable: `--chatterbox-no-softg` (on the server, per request
`{"softg": false}`); to disable everything: `--chatterbox-tr-raw`.

**A/B measurement** (Chatterbox, `--seed 42`, same texts, round-trip: whisper turbo CPU):

| Case | a) OLD (`ş→sh` only) | b) NEW (`ş→sh` + `ğ`) | c) RAW (no patch) |
|---|---|---|---|
| "Tam yerel **çalıştığı için**…" | "çalış dışı işin" ❌ | **"çalıştığı"** ✅ | "çalıtıcı işin" ❌ |
| 9-word list (word-correct) | 44% | **67%** | 44% |
| "Harika Aybars!" (word-correct) | 50% | 50% | 50% |
| Generation time (1st sentence) | 23.2 s (guard retry) | **5.0 s** | 4.2 s |

Word list detail (b): `öğretmen` ✅ · `mağdur` ✅ · `buğday` ✅ · `kağıt`→"kayıt" ✅ (**correct
pronunciation** in Turkish) · `ağaç`→"ayaç" ✅ (ğ = y glide) · `değil`/`dağ`/`yağmur` ✅ · `iğne`→"yine"
⚠️ (respell "iine"; the weakest link). The patch also **reduces guard retries** (23.2 s → 5.0 s).

**Chatterbox TR flaws that remain independent of `ğ`** (the patch gives the same output in all three
variants — unrelated to `ğ`):

| Word | Heard | Note |
|---|---|---|
| `yerel` | "gereğe" / "geri" / "genel" | the model garbles the word entirely |
| `için` | "işin" | `ç`→`ş` shift |
| `Aybars` | "haybars" / "aybaş" | proper noun; varies from generation to generation |

→ The patch **closes the `ğ` class**; but Chatterbox's TR pronunciation is still **fragile** (errors of
the yerel/için/Aybars kind are not solved by the patch). This is the limit of the "not the engine but
preprocessing for TR" thesis in §6 and §9: every word needs a lexicon/exception. Measurement files:
`logs/softg-bench/` (producer `logs/softg-bench.py`, verifier `logs/softg-asr.py`), listening set:
desktop `aybars-tts-test\`.
**EAR TEST ✅ (2026-10-18):** for variant b the user said **"yeni olan güzel"** → the `ğ` patch was
accepted (decision #23), on by default with `--lang tr`.

## 10. Pipeline TTS run modes (2026-10-17)

The same 4 sentences (LLM output), RTX 5060 Ti, `--lang tr` (tr-fix + respell automatic):

| Mode | Total (4 sentences) | Note |
|---|---|---|
| Sentence by sentence (separate process per sentence) | **106.6 s** | per sentence the torch import (~8 s) + model load (~13 s) **repeat** |
| Batch (`--batch-file`, single process) | **48.4 s** | load (19.8 s) **once** + generation 28.6 s |
| **Persistent server (`--serve`, warm)** | **16.6–18.5 s** | **no** load; generation only |

**Full pipeline** (ASR → LLM → TTS) with persistent servers (`whisper-server` + `tts-server` +
`llama-server`): **~23–27 s per turn** (3 sentences: ASR ~10 s + LLM ~4 s + TTS ~9–12 s), no model
loading at all.

- Chatterbox generation **RTF ~1.2–1.4** (slower than real time) → generation takes longer than the
  output audio; the `<1 s` first-audio target is not met on the TTS side either.
- ⚠️ On a very short sentence ("Merhaba!") RTF rises to ~3.7 and 9.6 s of audio can be produced
  (short-sentence instability, see §3). **Fix: the long-tail guard → §11.**
- ⚠️ **CUDA pitfall:** corrupted/unsuitable input **permanently** corrupts the CUDA context with
  `device-side assert`; the server must be restarted. Therefore `tts-server` now rejects non-text items
  with **400** and reports this in `/health` via the `fatal` field.

## 11. Long-tail (hallucination) guard (2026-10-17)

**Question:** "We solved hallucination by not sending the empty ones" — is that correct?

**Answer: two separate mechanisms are being conflated.** Separated by measurement + code review:

| Mechanism | What it prevents | Evidence |
|---|---|---|
| **Empty/symbol-only filtering** (`pipeline.ps1` `\p{L}\|\p{N}`, `_read_lines`, `server_texts`, `ensure_speakable`) | **Crash**: emoji-only sentence → `IndexError: max(): Expected reduction dim 1 to have non-zero size`; long corrupted text → `CUDA device-side assert` (context is permanently poisoned) | Error logs; lines no longer go to the model **at all** |
| **Chatterbox `alignment_stream_analyzer`** (the model's own guard) | **Overflowing/fabricated audio** (long tail, token repetition) | Log on every generation: `forcing EOS token, long_tail=tensor(True)`; in an early test `Detected 2x repetition of token 6405` → EOS was forced |

So "not sending the empty ones" was a **robustness** protection; what cuts the overflow is the model's
own guard. But that guard is **not deterministic** — the same sentence comes out with different
durations (`logs\pipeline\tts_batch.json`):

| Sentence (chars) | Generated audio |
|---|---|
| **"Merhaba!"** (7) | **9.60 s** ⚠️ |
| "Benim için tam bir karşılama." (26) | 4.96 s |
| "Sanki bir yedek ses çıkmış gibi duyuluyor ama neyse." (49) | 4.24 s |
| "Bugün size nasıl yardımcı olabilirim?" (33) | 3.44 s |

An 8-character sentence produced 9.6 s of audio while a 33-character sentence stayed at 3.4 s →
**short-sentence instability** (consistent with §3).

### 11.1 Fix: duration sanity guard + 1 retry

`synth_chatterbox(..., guard=True)` (default; `--no-guard` disables it):
- `expected ≈ char_count / 14` s (TR, min 0.4) → `audio_guard_limit = max(3×expected, expected + 2)`
- if the generated audio exceeds the limit the **same sentence is generated ONE more time** and the
  **shorter** one is kept (retry seed `seed+1`; `retried` / `long_tail_guard` / `audio_limit_seconds` /
  `first_audio_seconds` / `retry_audio_seconds` / `guard_extra_seconds` are written to the result)

### 11.2 GPU measurement (24 generations: 6 short sentences × 4 seeds)

| Sentence | seed | limit | first generation | after guard |
|---|---|---|---|---|
| Tamam. | 100 | 2.40 | 2.76 | **0.68** |
| Peki, anladım. | 100 | 2.79 | 4.92 | **1.12** |
| Evet. | 101 | 2.40 | 2.56 | 2.56 *(retry 2.60 → the first was kept)* |
| Tamam. | 102 | 2.40 | 3.56 | **1.12** |
| Evet. | 102 | 2.40 | 2.60 | **1.44** |
| Peki, anladım. | 102 | 2.79 | 6.04 | **3.00** |
| Peki, anladım. | 103 | 2.79 | 3.00 | **1.96** |

- The guard **triggered 7/24 (29%)**, **longest caught tail 6.04 s**, **0 errors/crashes**.
- On long sentences (limit 4.9–6.9 s) it **never** triggered → no false positives.
- **Cost:** ~1 extra generation per triggered sentence (7 extra out of 24 generations) — average
  generation 3.44 s, i.e. ~30% extra time on short sentences; zero on long sentences.
- ⚠️ **Not a guarantee:** sometimes the limit is still exceeded (the 2.56 and 3.00 s rows) because both
  generations can be long; the guard *reduces* it. If needed, a 2nd retry or a hard cap can be added
  (risk of cutting speech off).
- **Live path (persistent server) verified:** `Merhaba!` → 2.72 s *(retried)*, `Evet.` → 1.12 s,
  0 errors; `/health` `ok:true`, `fatal:null`. A symbol-only item returns a **per-item** error
  (HTTP 200, `failed` increments, the batch does not fail) → corrupted input does not poison the CUDA
  context.

**Review (self-audit) — bug found and fixed:** when a guard retry won, `res["out"]` pointed at the
**deleted** `.retry.wav` path (it was not updated after `os.replace`). Because `pipeline.ps1` used that
field with `Test-Path`, **the fixed sentence could silently fail to play** (**6 records** were affected
in the 24-generation measurement). Fixed: `out` now points to the real file (the old path is in
`retry_out`), a **defence** was added to the pipeline for the case where the filename is missing; the
compensation cost is written to the `guard_extra_seconds` field. Regression net: **with the fix removed
3 tests fail**, with the fix **39 tests** pass. The GPU run was **repeated** after the fix: **24/24
`out` files EXIST on disk**, `retry_out` only holds the old temporary path, no leftover `.retry.wav`
(**7 triggers, 0 errors**).

Offline tests: **39** (`python -m pytest -q`); the guard scenarios (retry / keep-the-shorter /
disabled / path integrity) are covered with a mock model, no GPU needed.
