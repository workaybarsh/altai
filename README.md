# Altai — local AI chatbot assistant

**Altai** is a real-time, **fully local** voice assistant for Windows: you speak into the
microphone and the assistant answers **out loud**. No cloud, no API keys — speech recognition,
the language model and speech synthesis all run on your own machine.

```
Microphone → faster-whisper (GPU) → Huihui-Qwen3.5-9B + MTP (GPU) → Chatterbox TTS (GPU) → speaker
```

## What it does

- **Speech in:** faster-whisper `large-v3-turbo` on the GPU (RTF 0.04–0.10, ~0.3–0.5 s per utterance).
- **Answer:** a local 9B model with MTP speculative decoding (85–91 tok/s, first token ~0.3 s),
  thinking on with a 128-token budget.
- **Speech out:** Chatterbox Multilingual v3 on the GPU (RTF 1.1–1.4), Turkish pronunciation patched
  (`ş→sh`, soft `ğ`), markdown stripped before synthesis.
- **Streaming:** TTS starts on the first sentence, so audio begins while the model is still writing.
- **Desktop UI:** one window — "Load models", then "Click to speak". Closing it stops every service.

## Measured (RTX 5060 Ti 16 GB, Ryzen 5 3600)

| Stage | Result |
|---|---|
| ASR (5 s utterance) | 0.3–0.5 s |
| LLM first token | ~0.3 s |
| TTS first sentence | 3–5 s (fixed cost of a Chatterbox call) |
| **First audio** | **~5 s** |
| Total VRAM | **~11.6 GB** (LLM 7.0 · ASR 1.2 · TTS 3.3) |

The remaining latency is Chatterbox's first sentence; everything before it is already sub-second.

## Quick start

Requirements: PowerShell 7, an NVIDIA GPU (CUDA 13.5 build), Python 3.12, the models in `models/`
and the binaries in `tools/` (both git-ignored), plus two virtual environments:

- `%USERPROFILE%\tts-venv` — `torch` (cu128), `chatterbox-tts`, `soundfile`
- `%USERPROFILE%\fw-venv` — `faster-whisper`

First run on a new machine: `pwsh -File scripts\setup.ps1` (venvs, binaries, models, MTP header).

```powershell
# Everything at once (recommended)
pwsh -File altai-desktop.ps1

# Or start the three services by hand
pwsh -File scripts\fw-server.ps1
pwsh -File scripts\tts-server.ps1 -Backend chatterbox -Lang tr -Tf32
.\tools\llama\llama-server.exe -m models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf -c 4096 -ngl 99 `
    --parallel 1 -ctk q8_0 -ctv q8_0 --host 127.0.0.1 --port 8080 `
    --spec-type draft-mtp --reasoning on --reasoning-budget 128 --reasoning-format deepseek
```

Headless check (no window):

```powershell
pwsh -File altai-desktop.ps1 -SelfTest -Wav logs\tts\sample.wav -NoThink
```

## How a turn works

1. **MTP header.** The quantised GGUF ships without the MTP/`nextn` tensors; `agent/mtp_inject.py`
   re-adds the 15 tensors from the base model (lossless). `llama-server` runs with
   `--spec-type draft-mtp` permanently.
2. **Streaming engine.** `agent/llm-stream.py` reads the `llama-server` SSE stream, splits it into
   sentences, sends each sentence to the TTS server and plays the WAVs in the background.
3. **Voice-first prompt.** The system prompt asks for at most two sentences, no markdown, numbers
   spelled out; `--reasoning-format deepseek` keeps thinking text out of the spoken answer.
4. **Cleanup.** The UI stops the LLM, TTS and STT servers on close and frees the VRAM.

## Project layout

| Path | What |
|---|---|
| `altai-desktop.ps1` | WinForms UI (load models / click to speak) |
| `agent/llm-stream.py`, `agent/pipeline-stream.ps1` | Streaming turn (SSE → sentences → TTS → playback) |
| `agent/asr-tools.py`, `agent/fw-server.py` | ASR tooling and the persistent GPU STT server |
| `agent/tts-tools.py` | TTS engines (Chatterbox / VoxCPM / SAPI) and the HTTP server |
| `agent/audio-capture.ps1` | Microphone capture (ffmpeg dshow, 16 kHz mono) |
| `agent/mtp_inject.py`, `agent/mtp-status.py` | MTP header tooling |
| `scripts/` | Server launchers, ASR benchmark, timing harness, MTP verification |
| `docs/` | Architecture, decisions, MTP verification, phase-2 results, TTS research |
| `tests/` | pytest suite (58 tests) |

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — data flow, turn sequence, latency budget
- [`docs/streaming-pipeline.md`](docs/streaming-pipeline.md) — streaming design and measurements
- [`docs/decisions.md`](docs/decisions.md) — decision log, including the GPU-stack decision (#26)
- [`docs/mtp-verification.md`](docs/mtp-verification.md) — MTP injection and acceptance tests
- [`AGENTS.md`](AGENTS.md) — developer/agent guide, pitfalls and changelog
- [`STATUS.md`](STATUS.md) — current setup and continuation notes

## Limits

- First audio ~5 s: Chatterbox costs ~3 s per call and is not a streaming TTS engine.
- While the LLM streams, TTS slows to RTF ~2–3; two-sentence answers keep playback continuous.
- Turkish Chatterbox pronunciation is patched but still fragile on some words.

## License

MIT — see [`LICENSE`](LICENSE). Third-party components keep their own licenses: whisper.cpp (MIT),
faster-whisper/CTranslate2 (MIT), Chatterbox (MIT), llama.cpp (MIT), Qwen-derived model weights.
