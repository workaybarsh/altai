# START — new-session kickoff note

**Project:** Altai — local AI chatbot assistant (fully local **voice** (STT + TTS) AI chat assistant on Windows).
**Working directory:** this folder.

---

## First message to paste into a new session

```
Project: Altai — voice (STT+TTS) local AI chat assistant.

Read these files first: STATUS.md, README.md, AGENTS.md, docs/decisions.md, docs/architecture.md.

Current state (2026-11-19, GPU stack on RTX 5060 Ti 16 GB):
- LLM: llama-server CUDA 13.5, 9B i1-Q5_K_M + MTP, -c 4096 --parallel 1 -ctk q8_0 -ctv q8_0
       --reasoning on --reasoning-budget 128 --reasoning-format deepseek  (~7.0 GB, 85-91 tok/s, TTFT ~0.3 s)
- STT: agent/fw-server.py (faster-whisper large-v3-turbo, int8_float16, CUDA, :8083)  (~1.2 GB, RTF 0.04-0.10)
- TTS: Chatterbox v3 on GPU (scripts/tts-server.ps1 -Backend chatterbox -Lang tr -Tf32)  (~3.3 GB, RTF 1.1-1.4)
- UI: altai-desktop.ps1 — "Load models" then "Click to speak"; services stop on close
- Mic: agent/audio-capture.ps1 (ffmpeg dshow, 16 kHz mono)
- Total ~11.6 GB VRAM. First audio ~5 s; Chatterbox's first sentence is 3-5 s of that.
- Tests: python -m pytest -q (60 tests). Timeline: scripts/measure-turn.ps1
- Start everything: pwsh -File altai-desktop.ps1
```
