# Streaming pipeline — emitting first audio early

> Goal: in `pipeline.ps1`'s batch flow, **first audio** only comes out after the LLM response has
> finished *and* all sentences have been synthesised. In the streaming pipeline, by contrast, as LLM
> tokens stream, the **first sentence** goes to TTS the moment it forms and audio **starts playing**
> while the rest of the response is still being written (pipeline principle #7).

## 1. Problem (batch flow)

```
ASR (~10 s) → wait until the LLM finishes (~3-5 s) → split into sentences → batch TTS (all sentences, ~9-12 s) → play
                                                                                                                  ▲
                                                                                       first audio HERE = end of turn
```

So **first audio latency ≈ turn duration** (~20-30 s). The user hears silence for that whole time.

## 2. Streaming pipeline

```
ASR → [LLM SSE stream] ──first sentence──> TTS (single sentence) ──> PLAY immediately (background)
           │                                                         ▲
           └── while the remaining sentences are produced ───────────┘  first audio ≈ ASR + first sentence + TTS(1 sentence)
```

First audio comes out without waiting for the **whole** response; audio plays while the rest of the
LLM output is being written and the following sentences are being synthesised (overlap).

## 3. Components

| File | Role |
|---|---|
| `agent/llm-stream.py` | Engine: llama-server SSE stream → incremental sentence splitting → per-sentence request to the TTS server → background playback (`winsound`). Emits timestamped JSON. No dependencies (stdlib). |
| `agent/pipeline-stream.ps1` | Thin wrapper: ASR (optional; skipped with `-Text`) + streaming turn + summary + `-Play`. |
| `scripts/tts-server.ps1` | **Required**: the streaming pipeline connects to the persistent TTS server (`-TtsServerUrl`); sends one request per sentence. |
| `tests/test_llm_stream.py` | Offline tests: sentence splitting, `reasoning_content` separation, end to end (fake LLM SSE + fake TTS). |

Usage:

```powershell
pwsh -File agent\pipeline-stream.ps1 -Text "Merhaba, nasilsin?" -TtsServerUrl http://127.0.0.1:8082 -Play
pwsh -File agent\pipeline-stream.ps1 -Wav recording.wav -AsrServerUrl http://127.0.0.1:8081 `
     -TtsServerUrl http://127.0.0.1:8082 -Play
```

## 4. Design details

- **`reasoning_content` is ignored.** With thinking on (`enable_thinking`) the model first produces
  thinking tokens; these do **not** enter sentence splitting (otherwise the thinking text would be read
  aloud). `answer` is built only from the `content` chunks.
- **Incremental sentence splitting** (`SentenceBuffer`):
  - hard end: `.!?…` + space/newline;
  - if `force_chars` (default 180) is exceeded, split **forcibly** at the last space (do not hold back a long sentence);
  - if `soft_chars` (default 120) is exceeded, split early at `, ; :` when present (pulls first audio forward);
  - a fragment below `min_chars` is merged with the next one.
- **Symbol-only sentences are not sent** (`is_speakable`): if there is no letter/digit it never goes to
  TTS (Chatterbox used to crash on such input — see `tts-benchmark.md` §11).
- **Playback in the background** (thread + queue): while audio plays, the stream keeps being read and
  the next sentences keep being synthesised (no back pressure).
- **Timestamps** (`--json-out`): `first_token_seconds`, `first_sentence_seconds`,
  `first_audio_seconds`, `llm_seconds`, `total_seconds` + per sentence `llm_at` / `tts_seconds` /
  `ready_at` / `retried`.

## 5. Measurement method

- Persistent servers open (`tts-server` 8082 + `llama-server` 8080, MTP); model load happens once.
- Same text input (`-Text`) → ASR disabled, only **LLM + TTS** compared.
- Comparison: (A) `pipeline.ps1` batch, (B) `pipeline-stream.ps1` streaming.
- "First audio": end of turn in batch mode (waits for batch TTS), `first_audio_seconds` in streaming mode.

<!-- OLCUM-SONUC -->
### 5.1 Measurement result (2026-10-18 · Ryzen 5 3600 · RTX 5060 Ti 16 GB · profile B)

Same prompt, `-Text` (ASR off, only LLM + TTS); three persistent servers open, no model load:

| Run | First token | First sentence | **First audio** | End of turn |
|---|---|---|---|---|
| **A) Batch** (`pipeline.ps1`) | — | — | **18.8 s** (= end of turn) | 18.8 s |
| **B) Streaming** #1 | 0.26 s | 0.53 s | **7.60 s** | 18.69 s |
| **B) Streaming** #2 | 0.28 s | 0.49 s | 18.06 s ⚠️ *(guard retry)* | 28.16 s |
| **B) Streaming** #3 | 0.26 s | 0.68 s | **7.05 s** | 23.07 s |
| **C) Streaming, thinking on** | 0.29 s | 3.98 s | **9.52 s** | 21.48 s |

End to end (with real ASR, `-Wav`; whisper turbo CPU):

| Run | ASR | First token | First audio (in engine) | End of turn |
|---|---|---|---|---|
| **E) Streaming** | 5.24 s audio → **9.91 s** (RTF 1.89) | 0.37 s | 13.40 s ⚠️ *(guard retry)* | 23.82 s |

**How to read it:**
- When the guard **does not fire**, the streaming pipeline pulls first audio forward by **~2.5×**
  (7.0–7.6 s ↔ 18.8 s); the biggest gain is dropping the "wait for the whole response" step, which
  was the real bottleneck.
- With thinking on the first **sentence** arrives late (3.98 s) because the model thinks first; the
  first **chunk** still arrives at 0.29 s, but `reasoning_content` does not enter sentence splitting
  (correct behaviour).
- ⚠️ **Short sentence + guard retry** can push first audio to 13–18 s (B#2, E): the guard sees that
  the audio exceeds the duration limit, regenerates the sentence, and **both generations stay long**
  (`"Harika!"` → 4.48 s). Tail energy analysis (`logs\tail-energy.py`): the tail is **not silence but
  extra speech** (envelope: `… 1794 229 5153 3055 … 2000 7645`) → silence trimming does not fix it.
- **Robustness (a real event during measurement):** two runs hit a `ConnectionResetError`
  (`WinError 10054`, Windows loopback); the engine **retried transparently** and the turn
  completed. After the path/encoding fix the `out` field found 3/3 WAVs correctly (the pitfall fix
  below).


### 5.2 TTS engine choice (2026-11-19): Chatterbox

**Chatterbox is the only live TTS.** Measured on the GPU (RTF 1.1–1.4 in isolation; ~2–3 while the
LLM streams on the same card):

- The sampler is capped by the expected utterance duration (AGENTS pitfall #20), which cut the
  short-sentence worst case from 6–16 s to ~3 s.
- The server warms up at start (`empty_cache` afterwards), so the first real turn does not pay the
  CUDA setup cost.
- First audio (LLM + TTS, no thinking) measured **3.7–7.2 s**; **Chatterbox's first sentence is
  3–5 s of that** and is the remaining latency floor.

End to end on the GPU stack (faster-whisper + 9B + Chatterbox): ASR 0.3–0.5 s, LLM TTFT ~0.3 s,
first sentence ~0.3 s → **first audio ~5 s**, total VRAM ~11.6 GB.

## 6. Known limits / next steps

- One TTS request per sentence → as many requests as sentences; in a long response total TTS time may
  rise slightly compared to batch mode (but **first audio** arrives much earlier).
- Sentence boundaries are **heuristic** (punctuation/length heuristics); responses containing
  markdown/emoji may need cleanup before going to TTS (for now only symbol-only sentences are skipped).
- The TTS side is **solved with Chatterbox**; the remaining latency is its first sentence (3–5 s, §5.2).
  ASR is no longer the bottleneck on the GPU stack (0.3–0.5 s). For a real `<1 s`, TTS would need a
  streaming engine (open decision — `decisions.md` #26).
- ⚠️ **Short sentence + guard retry:** if the guard's audio limit is exceeded it regenerates the
  sentence; on short sentences both generations can stay long → first audio rises to 13–18 s.
  Options: disable retry / floor the limit for short sentences (e.g. <20 letters), pick the shortest
  of 3 generations, or use ready-made (pre-generated) audio for very short interjections. **Work to be
  measured.**
- **Robustness:** a rare `WinError 10054` reset can occur on Windows loopback → sentence TTS is
  attempted **2 times** (synthesis is idempotent); if the LLM stream breaks mid-way, **the turn
  continues with the sentences in hand** and the state is reported in the `stream_error` field. If a
  single sentence's TTS blows up the turn does not fail (`failed_sentences`).
- Audio playback uses `winsound` (Windows); the application layer may use its own audio engine.
