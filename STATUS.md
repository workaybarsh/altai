# Status and Continuation Notes

> For quick context when starting a new chat/session. Details: [`README.md`](README.md),
> [`AGENTS.md`](AGENTS.md), [`docs/`](docs/).

## Project
**Altai** — local AI chatbot assistant. A **fully local**, voice (STT + TTS) AI chat assistant on Windows.
Repo: `github.com/workaybarsh/altai`

## Completed
- Architecture + decisions: `docs/architecture.md`, `docs/decisions.md`
- **MTP tools:** `agent/mtp_inject.py`, `agent/mtp-status.py`, `scripts/mtp-verify.ps1` + tests
- **ASR tool:** `agent/asr-tools.py`, `scripts/asr-benchmark.ps1` — real end-to-end
  smoke test with whisper.cpp (base.en, CPU, RTF ~0.19)
- **TTS tool:** `agent/tts-tools.py` (chatterbox / **voxcpm** / piper / sapi) + **batch mode**
  (`--batch-file` + `--out-prefix`)
- **TTS-TR evaluation:** **Trendyol-TTS** measured (VRAM ~5.6 GB, RTF ~3) → **offline engine**
  (decision #16, `docs/tts-tr-results.md`)
- **Chatterbox TR fixes (code):** `install_tr_tokenizer_fix()` + `ş→sh` respell, **automatic**
  with `--lang tr`. Listening test (2026-10-17): Chatterbox and Trendyol — both good (decision #18)
- **Pipeline ran end to end** (real components): `whisper` → `llama-server` (MTP) → sentence splitting
  → Chatterbox TTS. LLM: ~103 tok/s, TTFT ~0.30 s; MTP draft acceptance ~0.63–0.75.
- **Pipeline connected to batch TTS (2026-10-17):** `pipeline.ps1` generates the sentences in one call
  (`--batch-file` + `--out-prefix`), the model loads **once**.
  **Measurement (4 sentences): one-by-one 106.6 s → batch 48.4 s (2.2×).** Loading ~19.8 s **once**;
  details `logs\pipeline\tts_batch.json`.
- **Critical bug fixes (2026-10-17):**
  - `uses_mtl` was **undefined** inside `synth_chatterbox` → the chatterbox path **always** raised `NameError`
    (single + batch). Fixed.
  - **Emoji** in the LLM response caused `UnicodeEncodeError` (cp1254) in `print` and **took down the whole
    batch generation**. stdout is now reconfigured to UTF-8; the pipeline also filters out emoji-only sentences.
  - `--out` is no longer mandatory in batch mode; if a single sentence blows up, batch generation **continues**
    (`failed` count is reported).
- **ASR measurement + optimisation (2026-10-17):** `large-v3-turbo` on CPU **RTF 4.2 → 1.9**
  (q5_0 quant + `-t 12`). The model was f16 → `ggml-large-v3-turbo-q5_0.bin` (547 MB) was produced
  (transcript **identical**). `asr-tools.py` now separates `load_seconds` / `infer_seconds`;
  thread default is **logical cores**. **`-ac` was REJECTED** (repeat loop/hallucination).
  Details: [`docs/phase2-results.md`](docs/phase2-results.md).
- **ASR model comparison (q5_0, 12 threads, 5.6 s TR audio):**
  base **0.84 s** (RTF 0.15 · Turkish weak) · small **2.5 s** (0.45 · weak) ·
  medium **7.5 s** (1.35 · good) · turbo **11.0 s** (1.98 · best).
- **Persistent ASR process:** `scripts/whisper-server.ps1` + `asr-tools.py --server-url`
  → the model stays in memory, repeated loading is over (turbo ~9.9 s on the server).
- **Persistent TTS process (2026-10-17):** `tts-tools.py --serve` (HTTP) + `scripts/tts-server.ps1`
  → Chatterbox stays in memory. Measurement (same 4 sentences): sentence-by-sentence **106.6 s** → batch 48.4 s →
  **persistent server 16.6–18.5 s** (~6×). Full pipeline with three servers up **~23–27 s per turn**
  (ASR ~10 + LLM ~4 + TTS ~9–12), **no model loading at all**.
  Details: [`docs/tts-benchmark.md`](docs/tts-benchmark.md) §10.
- **Long-tail (hallucination) guard (2026-10-17):** `synth_chatterbox(guard=True)` — if the generated audio
  exceeds the duration limit (`max(3×expected, expected+2 s)`, expected ≈ letters/14) the sentence is
  generated **once** more and the **shorter** one is kept (`--no-guard` disables it). Also, empty/emoji-only
  sentences **never reach** the model (`ensure_speakable`; previously they crashed with `IndexError`/CUDA assert).
  **GPU measurement (24 generations): 7 triggers (29%), longest caught tail 6.04 s, 0 errors**;
  it never triggered on a long sentence. ⚠️ The guard reduces but does not guarantee. Details and the
  "two mechanisms" distinction: [`docs/tts-benchmark.md`](docs/tts-benchmark.md) §11, decision #21.
  *(Post-review fix: when the retry won, the `out` field pointed at a deleted `.retry.wav` path →
  `pipeline.ps1` lost that sentence in `Test-Path`; `out` is now the real file, and a defence was added
  to the pipeline.)*
- **Streaming pipeline (2026-10-18, principle #7 in code):** `agent/llm-stream.py` (`llama-server` **SSE** →
  incremental sentence splitting → TTS as soon as a sentence forms → audio played **in the background**) + `agent/pipeline-stream.ps1`.
  **Measurement (LLM+TTS, same prompt): first audio 18.8 s batch → 7.05–7.60 s streaming (~2.5×)** (first token
  0.26 s, first sentence ~0.5 s; with reasoning on, first audio 9.52 s). End to end (ASR turbo CPU 9.91 s +
  streaming) first audio **13.4 s**. ⚠️ On a short sentence the guard retry can push first audio to 13–18 s;
  end-energy analysis showed the tail is **extra speech** (not silence → trimming does not solve it).
  Details: [`docs/streaming-pipeline.md`](docs/streaming-pipeline.md), decision #22.
- **Robustness (2026-10-18):** a sentence's TTS is retried **2 times** on a transient `WinError 10054` reset
  (synthesis is idempotent); if the LLM stream breaks mid-way it **continues with the sentences at hand**
  (`stream_error`); if one sentence's TTS blows up the turn does not fail (`failed_sentences`). Two real resets
  were transparently compensated during measurement.
- **Critical fix (2026-10-18):** PS 5.1 `Get-Content -Raw` read a BOM-less UTF-8 file as **ANSI**
  → 3 WAVs produced on the streaming pipeline appeared "lost" (`Test-Path` wrongly `False`; pitfall #15). All
  JSON reads were switched to `-Encoding UTF8`; the ASR path was switched to `--out` + reading from the file
  (the stdout pipe can corrupt the encoding).
- **TTS bottleneck SOLVED — Piper (2026-10-18):** `tts-tools.py --serve --backend piper` +
  `scripts/install-piper.ps1` (installs into an ASCII directory: `%LOCALAPPDATA%\altai\piper`). Piper
  `tr_TR-dfki-medium`: **RTF 0.19**, round-trip transcription **WER 0.000** (5/5 sentences exact), **on CPU** (no GPU).
  On the streaming pipeline **first audio (LLM+TTS): 0.77–0.90 s** (Chatterbox 4.2–7.6 s; 30 s with guard retry).
  End to end (ASR + piper): **~11.7 s** (Chatterbox 13.4 s) → **ASR is still dominant (85%)**.
  Details: [`docs/streaming-pipeline.md`](docs/streaming-pipeline.md) §5.2, [`docs/tts-benchmark.md`](docs/tts-benchmark.md) §5.
  ⚠️ Piper (espeak-ng/onnxruntime) **cannot read non-ASCII paths** → the binary and the voice file must be in an
  ASCII directory; the same limit applies to `whisper-cli.exe` (`0xC0000409` on a non-ASCII **absolute** path).
- **Chatterbox `ğ` fix (2026-10-18):** the user's listening complaint (`çalıştığı` → "çalıştı ki")
  **was confirmed by round-trip transcription** ("Tam yerel çalıştığı için…" → "Tam yarar çalıştı ki işin…"). Root cause:
  the grapheme dictionary (`grapheme_mtl_merged_expanded_v1.json`) **has `ğ`**, there is no NFKD decomposition → the problem is
  **in the acoustic model**, not in the tokenizer. `tr_softg()` was added (`ğ`: between two vowels → `y`, after a vowel
  before a consonant/finally → the previous vowel: `dağ`→`daa`), applied **before** `ş→sh`.
  **A/B (Chatterbox, seed 42, same texts, round-trip transcription):** `çalıştığı` **fixed** ✅ (old patch
  "çalış dışı", unpatched "çalıtıcı"); word accuracy on the 9-word list **44% → 67%**; guard
  retry on sentence 1 **23.2 s → 5.0 s**. Disable: `--chatterbox-no-softg` (on the server, per request `{"softg": false}`).
  ⚠️ TR defects independent of `ğ`: `yerel`→"gereğe", `için`→"işin", `Aybars`→"haybars/aybaş"
  (not solved by the patch). Details: [`docs/tts-benchmark.md`](docs/tts-benchmark.md) §9.4;
  **listening test ✅ (2026-10-18): the user said "yeni olan güzel" → the patch was accepted (decision #23)**;
  listening set (desktop) `aybars-tts-test\`; measurement files `logs/softg-bench/`.
- Tests: `python -m pytest -q` → **59 tests** passing

## Key decisions (summary)
- **LLM:** Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M **+ MTP mandatory** (decisions #12, #13)
- **STT:** whisper.cpp `large-v3-turbo` (decision #11); on CPU **q5_0 quant + logical threads**;
  **persistent `whisper-server`** for the live pipeline
- **TTS:** English **Chatterbox** (MIT). TR: **Piper** (`tr_TR-dfki-medium`, **CPU**, RTF 0.19,
  WER 0.000, first audio ~0.8 s) — **fastest candidate for live** (the default decision awaits approval);
  **Chatterbox (tr-fix+respell+`ğ` patch)** for naturalness (~3.3 GB GPU, RTF ~1.2) but its TR pronunciation is
  **fragile** (`yerel`/`için`/`Aybars` still broken → §9.4); **Trendyol-TTS** offline
  (~5.6 GB, RTF ~3). (decisions #16/#18; Piper measurement `docs/streaming-pipeline.md` §5.2)

## Open items / next steps
0. ✅ **Pipeline + streaming pipeline + persistent servers connected and measured (2026-10-17/18).**
   - ✅ **TTS side solved:** streaming pipeline (decision #22) + **Piper** (CPU, RTF 0.19, WER 0.000) →
     **first audio (LLM+TTS) 0.77–0.90 s** — within the target (<1 s).
   - ⚠️ **The only remaining bottleneck is ASR** (~10 s; ~85% of the end-to-end time). whisper turbo encodes the
     **30 s window** on every request → a fixed cost on short audio; `-ac` was rejected (repeat loop).
   - **Next decision:** `small`/`medium` for ASR (speed↔accuracy trade-off) **or** move whisper to the GPU
     **or** hide it with VAD/streaming ASR (turbo RTF>1 on CPU → hard).
   - ⏸️ **Moving all components to the GPU (VRAM split) → to be evaluated in the 8 GB VRAM PROFILE**
     (user note 2026-10-18: "onu 8 GB VRAM'li PC'de düşünürüz"). On this machine (profile B, 16 GB)
     STT/TTS **stay on the CPU** (principle #1). Obstacles identified if they are moved to the GPU: this whisper
     build has **no `ggml-cuda.dll`** (a CUDA build is needed; **RTX 5060 Ti = sm_120** → CUDA ≥12.8
     required, the official `whisper-cublas-12.4` prebuild is not enough); Piper is **CPU-only** (onnxruntime-gpu
     needed); Chatterbox GPU **~3.3 GB** and **RTF ~1.2** (slow → it would ruin first audio again).
     Rough budget: LLM 6.6 + whisper 0.6–1.6 + Chatterbox 3.3 ≈ **10.5–11.5 GB** → fits in 16 GB,
     **does not fit in 8 GB** (in profile A the question is whether ASR or TTS gets priority).
   - ⬜ **Awaiting decision:** should Piper be the **default TTS** of the live pipeline? (measurement ready, awaiting approval;
     because Piper runs on the CPU it leaves the GPU entirely to the LLM — architecture principle #1).
   - ✅ **The `ğ` patch was ACCEPTED BY LISTENING TEST (2026-10-18, decision #23):** the user said "yeni olan güzel"
     → it is on by default with `--lang tr`. ⬜ **Remaining work:** `yerel`/`için`/`Aybars` type errors
     (§9.4) → **word-exception dictionary** (with ASR supervision) **or** a TR TTS replacement. The user rejected Piper
     on **naturalness** (WER 0.000 but robotic) → Chatterbox TR fragility is still an open topic.
   - ⬜ **Open item (only if Chatterbox stays):** limiting the guard retry on short sentences (e.g. no
     retry under 20 letters / a floor limit) or a pre-recorded voice for short exclamations.
1. **Turkish TTS:** Trendyol-TTS is heavy (VRAM ~5.6 GB, RTF ~3) → offline. Live TR candidates
   **CosyVoice2 / XTTS-v2** (speed + VRAM must be measured). If not liked, Piper.
2. **Fish S2 Pro:** isolated WSL trial only (Turkish weak, deleted; WSL kept).
3. **Phase 3:** LLM + MTP + prefix cache (MTP works; prefix cache not measured).
4. **LLM context/prefix cache** and the chat loop (interface) do not exist yet.

## Environment notes
- ⚠️ **BIG CLEANUP (2026-10-18) — disk data deleted, SOURCE CODE REMAINS.** By user decision
  ("sonra tekrar üzerinde çalışırsak yükleriz") the following were deleted (**15.6 GB** reclaimed; C: 154.5 → 170.2 GB):
  `models\` (9B i1-Q5_K_M GGUF **6.5 GB** + `ggml-large-v3-turbo-q5_0.bin` 0.5 GB) · `tts-venv` (**5.4 GB**) ·
  `%LOCALAPPDATA%\altai` (piper 0.1 GB) · HF `models--ResembleAI--chatterbox` (**3.0 GB**) · `logs\`
  (measurement artifacts + dev scripts: `asr-diff.py`, `softg-bench.py`, `softg-asr.py`, `dinle-kit.py`,
  `check-grapheme.py`, `bench-piper.py`…). **Remaining:** `tools\` (whisper + llama binaries, 780 MB).
  **Re-setup:** (1) `tts-venv` → `pip install` (list below: torch 2.11+cu128, chatterbox-tts,
  soundfile); (2) `scripts\install-piper.ps1`; (3) HF chatterbox downloads **automatically** on first run;
  (4) `models\` → HF `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF` + **MTP
  injection with `mtp_inject.py` (mandatory)**, whisper turbo q5_0 with `whisper-quantize`. The "Models"/"TTS venv"/
  "Sample audio" lines below describe **the state on that day** (no longer on disk).
- **PowerShell 7 (2026-10-17):** `winget install Microsoft.PowerShell` → **7.6.7**;
  `pwsh` = `%LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe` (on PATH). Before that only 5.1 existed.
  `pipeline.ps1`/the scripts are kept ASCII, so they also run on 5.1.
- **Tools:** `tools\whisper\Release\whisper-cli.exe` (+ `whisper-server.exe`, `whisper-quantize.exe`,
  `whisper-bench.exe`), `tools\llama\llama-server.exe` (b11669, CUDA 13.4).
- **Models** (`models\`): ⚠️ **deleted on 2026-10-18** (see BIG CLEANUP). On that day: **`ggml-large-v3-turbo-q5_0.bin` (547 MB, default ASR)** and
  `Huihui-...i1-Q5_K_M.gguf` (6.7 GB, **MTP injected**).
  *(2026-10-17 disk cleanup: turbo **f16**, base/small/medium (+q5_0) and the **Trendyol-TTS** in HF
  plus the whisper-v3-turbo caches were deleted — **~15 GB** reclaimed. They can be regenerated from HF/with
  `whisper-quantize` if needed; the `voxcpm` offline backend does not work until then.)*
- **Persistent servers (recommended for the live pipeline):**
  `llama-server` (port 8080) + `scripts\whisper-server.ps1` (8081, **`-ng`**) +
  `scripts\tts-server.ps1` (8082, tts-venv). Pipeline:
  `pipeline.ps1 -AsrServerUrl http://127.0.0.1:8081 -TtsServerUrl http://127.0.0.1:8082`.
  **Streaming pipeline:** `pipeline-stream.ps1` (same servers; `-Play` plays the generated audio immediately).
  ⚠️ if `tts-server` loses its CUDA context on bad input, `/health` returns `fatal` → restart it.
- **Piper (CPU TTS, 2026-10-18):** `scripts\install-piper.ps1` → `%LOCALAPPDATA%\altai\piper`
  (`piper.exe` + `voice.onnx`); then `scripts\tts-server.ps1 -Backend piper -Port 8082`.
  ⚠️ **ASCII directory required** (espeak-ng cannot read non-ASCII paths; onnxruntime crashes with `0xC0000409`).
  Details + measurement: [`docs/streaming-pipeline.md`](docs/streaming-pipeline.md) §5.2.
- **Running `llama-server` (MTP)** (reasoning on, budget 256; port 8080). ⚠️
  because `--reasoning-budget-message` contains spaces it **must be quoted and the `=` form must not be used**:
  ```
  tools\llama\llama-server.exe -m models\<gguf> --spec-type draft-mtp -c 4096 -ngl 99 ^
    --reasoning on --reasoning-budget 256 ^
    --reasoning-budget-message "Dusunmeyi bitir ve kisa Turkce cevabi yaz." ^
    --host 127.0.0.1 --port 8080
  ```
- **whisper-server:** `pwsh -File scripts\whisper-server.ps1 -Model models\ggml-large-v3-turbo-q5_0.bin`
  (port **8081**). ⚠️ **`-ng` is mandatory** — if it tries the GPU it crashes with `0xC0000409` (STT stays on CPU).
  Usage: `asr-tools.py --wav ... --server-url http://127.0.0.1:8081`; `-Stop` to stop it.
- ⚠️ **Non-ASCII repo path:** the path contains "Varsayılan" (ı). If an **absolute** path
  argument is passed to `Start-Process`, the character is corrupted (whisper-server opens the wrong path and crashes) → use a **relative path +
  `-WorkingDirectory`** (see `scripts/whisper-server.ps1`).
- **Whisper binary** is not on PATH → `asr-tools.py --whisper tools\whisper\Release\whisper-cli.exe`.
- **TTS venv:** `%USERPROFILE%\tts-venv` ⚠️ **deleted on 2026-10-18** (BIG CLEANUP). On that day:
  `torch 2.11.0+cu128` (sm_120), `chatterbox-tts 0.1.7`,
  `voxcpm 2.0.3`, `soundfile`. HF models are intact.
- **Sample audio (⚠️ `logs\` deleted on 2026-10-18):** `logs\tts\tr-ornek.wav`, `logs\tts\en-ornek.wav`,
  `logs\tts\trendyol-tr*.wav`; for the ASR measurement `logs\asr-tmp\chatterbox-tr-final.16k.wav` (5.6 s TR).
- The project targets **native Windows**; Fish/WSL is only for trials
- **Working rule:** **ask the user** before running heavy GPU work (model loading / GPU inference)
- **Two hardware profiles:** A (8 GB VRAM/16 GB RAM) and B (16 GB VRAM/32 GB RAM) → [`docs/architecture.md`](docs/architecture.md) §7.1.
  This machine is **profile B** (Ryzen 5 3600 6C/12T, RTX 5060 Ti 16 GB).
