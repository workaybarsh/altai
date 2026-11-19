# Status and Continuation Notes

> For quick context when starting a new chat/session. Details: [`README.md`](README.md),
> [`AGENTS.md`](AGENTS.md), [`docs/`](docs/).

## Project
**Altai** — local AI chatbot assistant. A **fully local**, voice (STT + TTS) AI chat assistant on Windows.
Repo: `github.com/workaybarsh/altai`

## Current setup (2026-11-19) — GPU stack
- **LLM:** `llama-server` (CUDA 13.5 build), 9B i1-Q5_K_M + MTP,
  `-c 4096 --parallel 1 -ctk q8_0 -ctv q8_0 --reasoning on --reasoning-budget 128 --reasoning-format deepseek`
  → ~7.0 GB VRAM, 85–91 tok/s, TTFT ~0.3 s
- **STT:** `agent/fw-server.py` (faster-whisper large-v3-turbo, int8_float16, CUDA, port 8083)
  → ~1.2 GB, RTF 0.04–0.10, warm-up on load
- **TTS:** Chatterbox v3 on the GPU (`scripts/tts-server.ps1 -Backend chatterbox -Tf32`, port 8082)
  → ~3.3 GB, RTF 1.1–1.4 isolated / ~2–3 under concurrent LLM load
- **UI:** `altai-desktop.ps1` — "Load models" then "Click to speak"; every service stops on close
- **Mic:** `agent/audio-capture.ps1` (ffmpeg dshow, 16 kHz mono 16-bit; MCI fallback)
- **Total:** ~11.6 GB models, ~13.8 GB with all services and the desktop running (16 GB card)
- **Measured:** first audio ~5 s (Chatterbox's first sentence is 3–5 s of it); ASR 0.5 s; LLM TTFT ~0.3 s

## Start everything
```powershell
pwsh -File altai-desktop.ps1          # GUI: Load models -> Click to speak
```
Headless check (no UI):
```powershell
pwsh -File altai-desktop.ps1 -SelfTest -Wav logs\tts\rec.wav -NoThink
```

## Tests and measurements
- `python -m pytest -q` → **58 tests**
- Timeline: `pwsh -File scripts\measure-turn.ps1 -Wav <wav> -Turns 2 -NoThink -MaxTokens 80`
- MTP check: `python agent\mtp-status.py models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf`

## What works
- End-to-end voice turn: mic → fw-server (GPU) → llama-server (MTP) → Chatterbox → speaker.
- Streaming: TTS starts on the first sentence; markdown is stripped before synthesis.
- Thinking is on by default (budget 128, `deepseek` format) and never reaches TTS.
- Graceful cleanup: closing the UI stops llama-server, the TTS server and the STT server.

## Known limits
- **First audio ~5 s** — dominated by Chatterbox's first sentence (fixed cost ~3 s per call, RTF > 1).
  A streaming TTS engine would be needed for `< 1 s`; Chatterbox cannot reach it.
- **Concurrent GPU load** raises TTS RTF to ~2–3: long answers play back with gaps. Keeping answers to
  two sentences (the system prompt) keeps playback continuous.
- **ASR cold start** is expensive (~28 s); the fw-server warm-up hides it at load time.
- **Chatterbox TR pronunciation** is patched (`ş→sh`, `ğ` soft-g) but still fragile on some words.
- **No window-less service mode**: the UI starts everything; each script can also run standalone.

## Repository map
| Path | What |
|---|---|
| `altai-desktop.ps1` | Desktop UI (load models / click to speak / cleanup) |
| `agent/llm-stream.py` | Streaming turn engine (SSE → sentences → TTS → playback) |
| `agent/pipeline-stream.ps1` | Streaming pipeline wrapper (ASR + llm-stream) |
| `agent/pipeline.ps1` | Batch/reference pipeline (ASR → LLM → batch TTS) |
| `agent/asr-tools.py` | ASR tool (whisper.cpp, whisper-server, fw-server) |
| `agent/fw-server.py` | Persistent faster-whisper (GPU) server |
| `agent/tts-tools.py` | TTS: Chatterbox / voxcpm / SAPI + HTTP server |
| `agent/audio-capture.ps1` | Microphone capture (ffmpeg dshow) |
| `agent/mtp_inject.py`, `agent/mtp-status.py` | MTP header tooling |
| `scripts/` | Server launchers, ASR benchmark, timeline, MTP verification |
| `docs/` | Architecture, decisions, MTP, phase-2, streaming, TTS research |
| `tests/` | pytest suite |

## Notes for the next session
- The venv for Chatterbox is `%USERPROFILE%\tts-venv`; the ASR venv is `%USERPROFILE%\fw-venv`.
- Models live in `models/` (git-ignored): 9B GGUF + whisper turbo q5_0; binaries in `tools/`.
- Do not start a second instance of any server: duplicate models double VRAM (AGENTS pitfall #19).
- Commit style: short prefixes (`feat:`, `fix:`, `docs:`, `perf:`), English, repo language is English.
