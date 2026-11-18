# Phase 2 · whisper.cpp pipeline and `<1 s` measurement plan

## 1. Goal

To measure the **STT leg** of the `<1 s` target on real hardware and answer this question with data:

> Does **whisper.cpp `large-v3-turbo`** on CPU transcribe a chat sentence fast enough,
> or should we drop to **`medium`** or **`small`** (or increase chunk parallelism)?

## 2. Why Phase 2 first

The LLM (fast with MTP) and TTS are fast; the real variable is **STT**. Although whisper.cpp `large-v3-turbo`
takes ~0.2–0.4 s for a typical sentence on CPU, on long sentences it strains the `<1 s` budget; this is the
riskiest link of the target.

## 3. Scope

- **In scope:** whisper.cpp (`large-v3-turbo` / `medium` / `small`), offline (segmented) and chunked
  modes, VAD, dependency-free recording, measurement harness, report.
- **Out of scope:** LLM, TTS, UI.

## 4. Hypothesis

**`large-v3-turbo`** transcribes a typical chat sentence in **~0.2–0.4 s** on CPU; **`medium`** may stay in a
similar band, while **`small`** yields **<300 ms**. Segmentation with VAD reduces perceived latency.

## 5. Measurement setup

| Field | Value |
|---|---|
| Hardware | Target: 8 GB VRAM machine, 16 GB RAM |
| Language model | Off (GPU idle; only ASR is measured) |
| Models | **`large-v3-turbo`** (primary), **`medium`**, **`small`** (comparison) |
| Quant | Q5 / Q8 (size-speed-accuracy balance) |
| Mode | segmented (offline) vs **chunked / stream-like** |
| Threads | 4 / 6 / 8 / physical cores (scaling) |
| VAD | Silero on / off |
| Input | Short (~2 s), medium (~5 s), long (~10 s) × TR/EN |
| Repeats | N = 10; median + p95 |

## 6. Metrics to measure

| Metric | Definition | Target |
|---|---|---|
| ASR latency | audio ready → text ready (end of segment) | ≤ 400 ms (turbo); measure (all) |
| RTF | compute / audio duration | < 1.0 |
| VAD endpoint | last word → "done" | ≤ 200 ms |
| Accuracy | WER (TR), manual reference | Acceptable for chat |
| Thread scaling | threads → speed curve | Find the saturation point |
| Memory | process peak RAM | Reasonable |

## 7. Scenarios

1. **Push-to-talk (PTT)** — short/medium/long, quiet environment.
2. **Continuous listening (VAD)** — endpoint latency.
3. **Noisy environment** — real-world robustness.
4. **turbo vs medium vs small** — speed/accuracy balance.
5. **Thread count** — physical core scaling.

## 8. Success criteria

- [ ] **ASR ≤ 400 ms** for a medium-length sentence in PTT (`large-v3-turbo`).
- [ ] VAD endpoint ≤ 200 ms; no sentence truncation.
- [ ] Turkish WER acceptable for chat.
- [ ] Memory allows running alongside the LLM on the GPU.

**Decision gate:** if `large-v3-turbo` meets the target it stays; if not, **drop to `medium`/`small`** or
tune chunk parallelism/VAD segmentation.

## 9. Output

- `docs/phase2-results.md`: measurement tables + WER notes.
- `docs/decisions.md`: the decision "turbo or medium/small, is streaming required".

## 10. Risks

- **CPU variance:** a laptop CPU changes the results.
- **VAD threshold:** aggressive → truncation, slow → latency.
- **Noise:** real-environment testing is mandatory.
- **Thread excess:** too many threads can reduce speed; tune by measurement.

## 11. Next phase

Once Phase 2 passes → **Phase 3** (LLM 9B i1-Q5_K_M + MTP + prefix cache) → **Phase 4** (TTS) → **Phase 5**
(UI + barge-in).

## 12. Tools (existing)

| Tool | Job |
|---|---|
| `agent/asr-tools.py` | 16 kHz mono conversion + whisper.cpp inference + latency/RTF measurement (JSON) |
| `scripts/asr-benchmark.ps1` | Batch measurement harness; writes `logs\phase2-asr-results.json` |

```powershell
pwsh -File scripts/asr-benchmark.ps1 -WavDir "tests\assets" -Model "models\ggml-large-v3-turbo-q5_0.bin" -Repeat 10
```

If real whisper.cpp is absent the tool **honestly** returns `ok=false` (it does not fabricate). Tests: `python -m pytest -q`.

