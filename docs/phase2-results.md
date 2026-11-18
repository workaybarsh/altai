# Phase 2 · Results

This document collects the **measurement results** for the `<1 s` STT target. Measurement plan:
[`phase2-measurement-plan.md`](phase2-measurement-plan.md).

> ⚠️ The smoke test below is a **mechanism verification** (does the pipeline work?); it is **not the final
> measurement** on the target hardware + `large-v3-turbo`.

## Smoke test — 2026-10-16 (pipeline verification)

**Purpose:** to prove that the `asr-tools.py` + `asr-benchmark.ps1` pipeline runs end to end with real
whisper.cpp.

| Field | Value |
|---|---|
| Engine | whisper.cpp (official Windows CPU build, b5454) |
| Model | `ggml-base.en.bin` (~141 MB) — **smoke test only** |
| Input | Speech generated with Windows SAPI (Zira, en-US), converted to 16 kHz |
| Audio duration | 7.16 s |
| Threads | 4 |
| Repeats | 3 |

**Result:**

| Metric | Value |
|---|---|
| Transcript | "Hello, this is a test of the Local Voice Assistant. The quick brown fox jumps over the lazy dog." |
| ASR (median) | **1.39 s** |
| p95 | 1.39 s |
| RTF | **0.19** |
| Status | ✅ Pipeline works; transcript correct |

**Takeaways:**

- Conversion (ffmpeg → 16 kHz mono), inference, timing and the JSON contract all behave **correctly**.
- With `base.en` RTF 0.19 → 7 s of audio transcribed in 1.4 s. The **`large-v3-turbo` target is far heavier**
  (≈10×); the real latency must be measured on this machine (the actual Phase 2 work).
- "Honest failure" verified: if whisper is not present the tool returns `ok=false`; it does not fabricate.

## Final measurement — 2026-10-17 (`large-v3-turbo`, real hardware, CPU)

**Hardware:** AMD Ryzen 5 3600 (6C/12T), RTX 5060 Ti 16 GB, Windows. **Engine:** whisper.cpp 1.9.5
(b5454, CPU backend `ggml-cpu-haswell.dll`). **Input:** 5.56 s Turkish speech (16 kHz mono).
**whisper-cli default:** `-t 4`, `-fa` on.

### 1) Model (f16 → q5_0) and threads

| Model | Threads | encode | total (wall) | RTF |
|---|---|---|---|---|
| f16 | 4 (default) | 20.9 s | 23.0 s | ~4.2 |
| f16 | 6 | 15.8 s | 17.8 s | 3.2 |
| f16 | 12 | 13.3 s | 15.1 s | 2.7 |
| **q5_0** | 6 | 13.1 s | 14.2 s | 2.6 |
| **q5_0** | **12** | **10.0 s** | **11.0 s** | **~1.9** |

- The model file was **f16** (`ftype=1`); on CPU F16 GEMM **~127 GFLOPS**, Q8_0 **~252**, Q4_0 **~231**
  (`whisper-bench -w 2`) → `ggml-large-v3-turbo-q5_0.bin` (574 MB) **was produced with `whisper-quantize`**.
  **Transcript identical.** Q5_0 reduced both encode time and load time (~1.2 → ~0.5 s).
- **Threads:** `-t 12` > `-t 6` > `-t 4`. So on this machine **SMT helps**
  (the "physical cores" general rule does not apply here) → the default of `asr-tools.py` was made
  **logical core count** (can be overridden with `--threads`).

### 2) The real bottleneck: the fixed 30 s encode window

whisper encodes the **30 s mel window** on every request; the cost is constant even for a short sentence.
For 5.56 s of audio encode takes ~10 s (q5_0, 12 threads) → **RTF is artificially high on short audio**.
That is why `asr-tools.py` now reports the `load_seconds` / `infer_seconds` / `infer_rtf` fields
(the `whisper_print_timings` lines from whisper.cpp are parsed).

### 2) Model comparison (all q5_0, `-t 12`, same 5.6 s TR audio)

| Model | Size | load | encode | total | RTF | Transcript quality |
|---|---|---|---|---|---|---|
| `base` | 53 MB | 0.07 s | 0.47 s | **0.84 s** | **0.15** | ❌ poor ("yere çalışan bir sesde aslanım") |
| `small` | 167 MB | 0.16 s | 1.73 s | 2.53 s | 0.45 | ❌ poor ("yere… sesti aslı tanım") |
| `medium` | 514 MB | 0.42 s | 5.51 s | 7.51 s | 1.35 | ✅ good (only "asistanım"→"aslanım") |
| `turbo` | 547 MB | 0.46 s | 10.08 s | **11.00 s** | 1.98 | ✅ best (identical) |

- **Only `base` meets the `<1 s` target on its own** — but its Turkish accuracy is unacceptable for chat.
  `small` ~2.5 s and still poor; `medium`/`turbo` are correct but take 7.5–11 s.
- So on this CPU **accuracy and `<1 s` do not hold together** → an explicit decision (smaller model,
  whisper on GPU, or revise the target?).

### 3) ❌ `-ac` (audio context) WAS TRIED and REJECTED

Trimming the encoder window with `-ac` looks tempting (q5_0 t=12: `-ac 768` → encode 4.9 s;
`-ac 512` → 3.2 s). **But it is not safe:** it produces wrong/partial transcripts and **repetition loops**
("asistanım"→"hastanım"; on 11 s of audio the sentence repeats 5×, on 22 s of audio it balloons to 115 words).
**Will not be used.**

### 4) Persistent process (whisper-server) — ends repeated model loading

`whisper-cli` reloads the model on every invocation (q5_0 ~0.5 s, f16 ~1.2 s). With `scripts/whisper-server.ps1`
+ `asr-tools.py --server-url http://127.0.0.1:8081` the model **stays in memory** → every request is pure inference.
Measurement (turbo q5_0, server mode): **9.94 s** (single-shot 10.48 s; the difference is ~0.5 s of loading).
⚠️ The server must be started with **`-ng`** (if it tries the GPU it crashes with `0xC0000409`) and since the
repository path is non-ASCII, **a relative model path + `-WorkingDirectory`** must be used.

> **Result:** with safe settings (`q5_0` + 12 threads) RTF **~4.2 → ~1.9**; the model comparison for
> `base`/`small`/`medium`/`turbo` is above. **The `<1 s` target cannot be met on this CPU with acceptable Turkish
> accuracy** (the turbo encoder alone is ~10 s; whisper encodes a 30 s window on every request).
> Decision: smaller model / whisper on GPU / revise the target.

## To do (target hardware)

- [x] Measurement with `large-v3-turbo` (5.6 s TR, N=3, median + p95) — 2026-10-17
- [x] **Thread scaling** (4/6/12) — `-t 12` fastest (SMT helps)
- [x] `medium`/`small`/`base` comparison — 2026-10-17 (table above)
- [x] Persistent `whisper-server` mode measurement
- [ ] Turkish WER (real speech, manual reference)
- [ ] VAD endpoint latency + streaming window
- [ ] Short/medium/long × TR/EN extended measurement (N=10)
- [ ] Final decision (model + CPU/GPU) → [`decisions.md`](decisions.md)
