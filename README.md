# Altai — local AI chatbot assistant (on-device voice assistant for Windows)

**Altai** is a real-time, **fully local**, AI-powered **voice** chat assistant for Windows:
you speak into the microphone and the assistant answers **out loud**.

> This repository is primarily a **plan**; the first working tool added was
> `agent/mtp_inject.py` (MTP header injection).
>
> Repository: `github.com/workaybarsh/altai` — former name `aybars_speaks`; old links keep
> working through GitHub redirects (decision #25).

## Quick start (GPU stack, 16 GB card)

```powershell
# Everything at once: loads llama-server, the faster-whisper server and Chatterbox,
# then "Click to speak" records and answers. Closing the window stops every service.
pwsh -File altai-desktop.ps1
```

Manual start (same order):

```powershell
pwsh -File scripts\fw-server.ps1                     # GPU STT  :8083 (~1.2 GB)
pwsh -File scripts\tts-server.ps1 -Backend chatterbox -Lang tr -Tf32 -Python "$env:USERPROFILE\tts-venv\Scripts\python.exe"   # TTS :8082 (~3.3 GB)
.\tools\llama\llama-server.exe -m models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf -c 4096 -ngl 99 --parallel 1 -ctk q8_0 -ctv q8_0 --host 127.0.0.1 --port 8080 --spec-type draft-mtp --reasoning on --reasoning-budget 128 --reasoning-format deepseek
```

Measured on an RTX 5060 Ti 16 GB: ASR 0.3-0.5 s, LLM TTFT ~0.3 s, Chatterbox RTF 1.1-1.4,
first audio ~5 s, ~11.6 GB VRAM. The CPU-only path (whisper.cpp + Piper) is still supported.

## Status

**Draft (planning) — `v0.2-plan`. Working tools: `agent/mtp_inject.py`, `agent/asr-tools.py`,
`agent/tts-tools.py`, `agent/pipeline.ps1` (end-to-end ASR→LLM→batch TTS) and the **streaming
pipeline** `agent/llm-stream.py` + `agent/pipeline-stream.ps1` (TTS as soon as the first sentence
exists, principle #7).**


- This repository is primarily a **design/plan document**; the working tools live under `agent/`.
- Every decision, its rationale and the **rejected alternative** are recorded here (see
  [`docs/decisions.md`](docs/decisions.md)).
- The same documents are updated as measurements and R&D results come in.
- ⚠️ **Measured (2026-10-17/18): the only real bottleneck is now STT.**
  STT `large-v3-turbo` takes ~10 s on CPU (q5_0, 30 s encoder window); `base`/`small` are fast but
  weak on Turkish. **The TTS side is solved:** streaming pipeline + **Piper** (CPU, RTF 0.19,
  round-trip WER 0.000) brings **first audio (LLM+TTS) to 0.77–0.90 s** (Chatterbox 4.2–7.6 s).
  End to end (ASR + Piper) **~11.7 s** → the remaining bottleneck is **ASR (~85%)**. Details:
  [`docs/streaming-pipeline.md`](docs/streaming-pipeline.md) §5,
  [`docs/phase2-results.md`](docs/phase2-results.md), [`docs/decisions.md`](docs/decisions.md) #19/#22.

## Goal

The first audio must come out **within 1 second** after the user stops speaking.

- **t₀** = the moment the user's last word ends
- **t₁** = the moment the first audio leaves the speaker
- **Target:** `t₁ − t₀ < 1000 ms`

The metric is **when the audio starts**, not when text appears on screen. Detailed budget:
[`docs/architecture.md`](docs/architecture.md).

## The product in one paragraph

In a single WinForms window the user speaks into the microphone; the application transcribes the
speech (**whisper.cpp**), passes it to a local language model
(**Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** — imatrix quant; **MTP always on**) and reads the
answer out loud (TTS). Everything is offline; no data leaves the machine. Push-to-talk and
continuous listening (VAD) modes are available.

## Architecture at a glance

**Main rule: only the language model runs on the GPU; STT and TTS run on the CPU.**

```
Microphone → VAD/record → whisper.cpp (CPU) → text
           → Huihui-Qwen3.5-9B (GPU, MTP) → response text
           → TTS (CPU) → speaker
```

| Component | Where | Why |
|---|---|---|
| **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** + MTP | **GPU (8 GB)** | Local imatrix quant (~6.6 GB); good size/quality balance; stays resident |
| **whisper.cpp** (`large-v3-turbo`) | **CPU** | Leaves the GPU to the LLM; Turkish + multilingual, fast on CPU, mature C/C++ ecosystem |
| TTS (Piper / Chatterbox / VoxCPM / SAPI) | **CPU** | Does not touch VRAM; swappable layer (VoxCPM/Trendyol is heavy → offline) |

The reason this project is separate: the existing work (MamidLabs) has other VRAM consumers such as
ComfyUI, OCR and mmproj. Here a **single-owner** pipeline is built.

## Hard rules

- **STT: whisper.cpp.** Default model **large-v3-turbo**; drop to `medium`/`small` when speed
  demands it.
- **Model: Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (GGUF, imatrix quant).
  Source: `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF`; base: `huihui-ai/Huihui-Qwen3.5-9B-abliterated`.
  File: `Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf` (~6.6 GB). The MTP header is added by `mtp_inject.py`.
- **MTP is always on.** `--spec-type draft-mtp`; it is never disabled. Speed with lossless output.
  The quant GGUF does **not** contain the MTP header; `mtp_inject.py` re-adds it from the base
  `huihui-ai` repository (source tensors verified). Verification + acceptance tests:
  [`docs/mtp-verification.md`](docs/mtp-verification.md).
- **The GPU belongs to the LLM only.** STT and TTS run on the CPU; the language model stays
  resident and is never evicted.

## Technology decisions (summary)

| Topic | Decision |
|---|---|
| Stack | PowerShell 7 + WinForms |
| Interaction | Push-to-talk **and** continuous listening (selected in settings) |
| STT | **whisper.cpp** (`large-v3-turbo`; CPU) |
| LLM | **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (imatrix), **MTP always on**, resident on the GPU |
| TTS | Swappable: Chatterbox v3 (EN) / Trendyol-TTS `voxcpm` (TR, heavy → offline) / Piper (fast) / SAPI |
| Language | Turkish + English (two versions) |
| Usage | Personal / open source (**MIT**) |
| Target latency | < 1 s |

All decisions: [`docs/decisions.md`](docs/decisions.md).

## The first working tool: MTP injection

The quant GGUF does **not** include the MTP/`nextn` header; that is why `--spec-type draft-mtp`
alone does not start llama.cpp. `agent/mtp_inject.py` re-adds the header from the base `huihui-ai`
repository (lossless; only 15 MTP tensors, the main weights are untouched).

```powershell
# Status check
pwsh -File scripts/mtp-verify.ps1 -Gguf "models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf"

# Inject if missing
pwsh -File scripts/mtp-verify.ps1 -Gguf "models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf" -Inject
```

Details, acceptance tests (T1–T7) and backups: [`docs/mtp-verification.md`](docs/mtp-verification.md).

## Phase plan

| Phase | Content | Status |
|---|---|---|
| 0 | Decisions | ✅ |
| 1 | Architecture + latency budget | 🔄 |
| 2 | STT (whisper.cpp) pipeline + < 1 s measurement | ⬜ |
| 3 | LLM (9B i1-Q5_K_M + MTP) + prefix cache | ⬜ |
| 4 | TTS layer | ⬜ |
| 5 | WinForms UI + PTT/VAD + barge-in | ⬜ |
| 6 | TR/ENG versions + packaging | ⬜ |

**Why phase 2 first?** The fate of the `<1 s` target is decided in STT; that is where whisper.cpp's
CPU speed is measured (whether `large-v3-turbo` suffices, or `medium`/`small` is needed).

## Documents

| Path | Content |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Architecture, data flow, turn sequence, responsibility table, latency budget |
| [`docs/mtp-verification.md`](docs/mtp-verification.md) | MTP verification + injection plan (acceptance tests, backups) |
| [`docs/phase2-measurement-plan.md`](docs/phase2-measurement-plan.md) | Phase 2: whisper.cpp pipeline and the `<1 s` measurement plan |
| [`docs/phase2-results.md`](docs/phase2-results.md) | Phase 2 measurement results (smoke-test record) |
| [`docs/tts-tr-results.md`](docs/tts-tr-results.md) | Turkish TTS (Trendyol-TTS) evaluation: VRAM, RTF, round-trip WER |
| [`docs/tts-benchmark.md`](docs/tts-benchmark.md) | Turkish TTS comparison (Chatterbox vs CosyVoice/OmniVoice/VoxCPM2/VITS; arXiv:2610.06057) |
| [`docs/streaming-pipeline.md`](docs/streaming-pipeline.md) | Streaming pipeline: design, usage, measurement (first audio 18.8 → 7.05–7.60 s) and limits |
| [`docs/decisions.md`](docs/decisions.md) | Decision log |
| [`AGENTS.md`](AGENTS.md) | Developer/agent infrastructure guide |

## License

This project is released under the **MIT** license — see [`LICENSE`](LICENSE) (decision #24).
Third-party components keep their own licenses: whisper.cpp MIT; LLM Llama/Qwen derivative;
Chatterbox MIT; Trendyol-TTS/VoxCPM2 MIT; Piper GPL-3.0 (invoked only as a separate tool).
