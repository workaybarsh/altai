# START — new-session kickoff note

**Project:** Altai — local AI chatbot assistant (fully local **voice** (STT + TTS) AI chat assistant on Windows).
**Working directory:** this folder.

---

## First message to paste into a new session

```
Project: Altai — voice (STT+TTS) local AI chat assistant.

Read these files first: STATUS.md, README.md, AGENTS.md, docs/decisions.md, docs/architecture.md.

Status summary:
- LLM: Huihui-Qwen3.5-9B i1-Q5_K_M + MTP (GPU, llama-server) — MEASURED: ~103 tok/s, TTFT ~0.3 s
- STT: whisper.cpp large-v3-turbo — q5_0 on CPU + logical threads: RTF 4.2 → ~1.9; whisper-server for live use
- TTS: Chatterbox (TR: tr-fix + respell AUTOMATIC, --lang tr); Trendyol = offline; RTF ~1.29 (GPU)
- **Pipeline works end to end** (agent/pipeline.ps1): ASR → LLM → sentence → **batch** TTS (single model load)
- Reasoning ON: --reasoning on --reasoning-budget 256 (max_tokens covers reasoning too)

⚠️ The <1 s target does not hold on this hardware: ASR turbo ~10 s (30 s encoder window), TTS RTF ~1.29.
✅ Repeated model loading SOLVED: persistent servers (whisper-server 8081 + tts-server 8082 + llama-server 8080)
   → full pipeline ~23–27 s per turn, no model loading at all.
⏳ NEXT WORK: (a) ASR model/CPU-GPU decision (small/medium? GPU?), (b) Turkish WER with real speech,
   (c) streaming pipeline (start LLM+TTS on the first sentence). Details: STATUS.md, docs/phase2-results.md, docs/decisions.md #19/#20
   Installations: tools\whisper, tools\llama, models\ (turbo-q5_0 + 9B with MTP)

Available tools: agent/mtp_inject.py; agent/asr-tools.py (--server-url); agent/tts-tools.py
(chatterbox / voxcpm / piper / sapi + --batch-file + --serve + long-tail guard); agent/pipeline.ps1
(-AsrServerUrl / -TtsServerUrl); scripts/whisper-server.ps1; scripts/tts-server.ps1
— tests: python -m pytest -q (59 tests)
```
