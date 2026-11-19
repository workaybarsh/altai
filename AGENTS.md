# Altai · local AI chatbot assistant · Infrastructure guide for developers and AI agents

This file is the single source of truth for developers and AI agents
working on Altai. The language of communication with the user is **English**.

> This repository is primarily a plan/design document; the first working tool is `agent/mtp_inject.py`.
> The structure and rules below define the target to be built on top of it.

## 1. The product in one paragraph

A real-time, AI-powered **voice chat assistant** that runs entirely locally on Windows. In a single
WinForms window the user speaks into the microphone; the app transcribes the speech (**whisper.cpp**),
feeds it to the local language model (**Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M**, **MTP always on**)
and reads the answer out loud (TTS). The target is for the first audio to come out **within 1 second**
after the user stops speaking.

## 2. Architecture principles (immutable)

1. **Only the language model runs on the GPU.** STT and TTS run **on the CPU**.
2. **The language model is resident.** It is not unloaded between turns; there is no model swapping.
3. **Model:** Huihui-Qwen3.5-9B-abliterated **i1-Q5_K_M** GGUF (imatrix) + MTP (`mtp_inject.py`).
4. **MTP is always on.** `--spec-type draft-mtp`; it is never disabled. Lossless output.
5. **STT: whisper.cpp** (Qwen3-ASR is not used).
6. **Single-owner pipeline.** Only `llama-server` + CPU workers.
7. **Pipeline.** LLM first sentence → TTS; while the user listens, the LLM keeps generating.

## 3. Models

### 3.1 Language model

| Field | Value |
|---|---|
| Model | Huihui-Qwen3.5-9B-abliterated **i1-Q5_K_M** (GGUF, imatrix) |
| File | `Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf` (~6.6 GB) |
| HF repository | `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF` |
| Base model | `huihui-ai/Huihui-Qwen3.5-9B-abliterated` (Qwen3.5-9B derivative, abliterated) |
| MTP | `blk.<N>.nextn.*` via `mtp_inject.py` (source: `huihui-ai/Huihui-Qwen3.5-9B-abliterated`) |
| Launch | `llama-server` + `--spec-type draft-mtp` (always) |
| Context | **4k** in chat (sliding window), upper bound **8k**; **32768 is not needed** (voice chat bot) |

> **Verified (2026-10-16):** the target quant GGUF (`i1-Q5_K_M`) **does not contain** an MTP/`nextn`
> layer; the source repository `huihui-ai/Huihui-Qwen3.5-9B-abliterated` **has 15 MTP tensors** and
> they match the `mtp_inject.py` mapping exactly. Injection is **mandatory**. Risks and acceptance tests:
> [`docs/mtp-verification.md`](docs/mtp-verification.md).

### 3.2 STT: whisper.cpp

| Field | Value |
|---|---|
| Engine | **whisper.cpp** (MIT, C/C++) |
| Model | **large-v3-turbo** (default); speed fallbacks `medium` / `small` |
| License | MIT (engine) · model weights MIT |
| Language | Multilingual; **Turkish (tr)** supported |
| Capability | Offline batch inference; streaming/chunked use is possible |
| Size | turbo ~1.6 GB (Q5) · medium ~1.5 GB · small ~0.5 GB |
| Where | **CPU** (the GPU belongs to the LLM) |
| Fallback | `medium` / `small` (faster on the CPU) |

> **Measured (2026-10-17, Ryzen 5 3600 6C/12T, CPU):** with `large-v3-turbo` **f16** the RTF is ~4.2
> (`-t 4`, the whisper default). With **q5_0 quant** + `-t 12` it is **RTF ~1.9** (encode 10.0 s / 5.6 s audio).
> Model comparison (q5_0, 12 threads): base **0.84 s** (weak Turkish) · small **2.5 s** (weak) ·
> medium **7.5 s** (good) · turbo **11.0 s** (best). ⚠️ whisper encodes its **30 s window** on every
> request → a fixed cost on short audio. ⚠️ `-ac` is **not used** (repetition loops).
> For the live pipeline, **`whisper-server`** (resident model) is recommended. Details: [`docs/phase2-results.md`](docs/phase2-results.md).

> **Speed note:** on the CPU, whisper.cpp `large-v3-turbo` transcribes a typical chat sentence in ~0.2–0.4 s
> (depending on the thread setting). For a long sentence `<1 s` is borderline; this is compensated by
> VAD segmentation + chunk parallelism. If needed, fall back to `medium`/`small`.

### 3.3 TTS: swappable layer

| Engine | Naturalness | Turkish | Live speed | License | Role |
|---|---|---|---|---|---|
| **Chatterbox Multilingual v3** | Highest | ⚠️ weak (`ş`/`ğ` patched; §3.3) | GPU | MIT | Primary for EN |
| **Trendyol-TTS** (`voxcpm`, VoxCPM2 + TR LoRA, ~2B) | High | ✅ intelligible | ❌ RTF ~3, ~5.6 GB VRAM | MIT | **TR offline/high quality** |
| **Piper** | Medium | ✅ **WER 0.000** | ✅ **RTF 0.19 · CPU** | GPL-3.0 | **Fast/live candidate** |
| Windows SAPI | Low | ✅ | ✅ | — | Last resort |

> **Measured (2026-10-18):** Piper `tr_TR-dfki-medium` — **RTF 0.19** over 5 sentences;
> round-trip transcription (whisper turbo) **WER 0.000** (5/5 verbatim, diacritics correct). In the
> streaming pipeline, **first audio 0.77–0.90 s** (Chatterbox 4.2–7.6 s). It runs **on the CPU** → the
> GPU is entirely for the LLM (principle #1) and there is no guard retry. Setup `scripts/install-piper.ps1`
> (⚠️ **ASCII directory required**, pitfall #16). Details: [`docs/streaming-pipeline.md`](docs/streaming-pipeline.md) §5.2.

> **Fixed and ACCEPTED (2026-10-18):** the Chatterbox TR pronunciation errors are patched with `ş→sh` +
> **`ğ` respell** (`tr_softg()`: between two vowels → `y`, after a vowel before a consonant/finally → the
> preceding vowel: `dağ`→`daa`). **The step is now correct** (`çalıştığı` → ❌"çalıştı ki" ⏩ ✅"çalıştığı");
> **ear test ✅** (user: *"yeni olan güzel"* → decision #23). A/B (seed 42, round-trip transcription): word
> accuracy over 9 words **44% → 67%**, guard retry on sentence 1 **23.2 → 5.0 s**. Disable with
> `--chatterbox-no-softg` (on the server, per request `{"softg": false}`). ⚠️ Errors unrelated to `ğ` persist
> (`yerel`, `için`, `Aybars`) → **Chatterbox TR is fragile**; a word-exception dictionary is needed.
> Details: [`docs/tts-benchmark.md`](docs/tts-benchmark.md) §9.4.

> **Measured (2026-10-16):** Trendyol-TTS Turkish is **intelligible** (round-trip Whisper WER ~0.08) but
> it needs ~5.6 GB VRAM + RTF ~3 → it does not fit on a target 8 GB card together with the resident LLM
> and it eats the `<1 s` target. That is why it is **not the default for the live pipeline**; it was added
> as an offline engine via `tts-tools.py --backend voxcpm` (decision #16). Details: [`docs/tts-tr-results.md`](docs/tts-tr-results.md).

## 4. Component map

✅ = existing · ⬜ = target

| Status | Path | Content |
|---|---|---|
| ⬜ | `altai-desktop.ps1` | **Desktop app**: WinForms UI - "Load models" (llama-server + fw-server + Chatterbox), "Click to speak", VRAM readout, full cleanup on close (`-SelfTest` for headless runs) |
| ⬜ | `agent/llm-run.ps1` | Start/stop `llama-server`, MTP, VRAM gate |
| ✅ | `agent/mtp_inject.py` | Adds the MTP/`nextn` head to a quant GGUF (from the base `huihui-ai` repository) |
| ✅ | `agent/mtp-status.py` | Writes a GGUF's MTP status as JSON |
| ✅ | `scripts/mtp-verify.ps1` | Checks the MTP status; adds the head with `-Inject` |
| ✅ | `agent/asr-tools.py` | 16 kHz mono conversion + **whisper.cpp** inference (single-shot **or** resident `whisper-server` via `--server-url`) + latency/RTF measurement |
| ✅ | `scripts/asr-benchmark.ps1` | Phase 2 ASR measurement harness (wrapper) |
| ✅ | `scripts/whisper-server.ps1` | Start/stop the resident `whisper-server` (`-ng`, port 8081); the model stays in memory |
| ✅ | `scripts/tts-server.ps1` | Resident TTS server (`tts-tools.py --serve`, port 8082); Chatterbox stays in memory · `-Backend piper` for **CPU Piper** (no loading) |
| ✅ | `scripts/install-piper.ps1` | Installs Piper + the `tr_TR-dfki-medium` voice into an **ASCII directory** (`%LOCALAPPDATA%\altai\piper`; required because the repo path is non-ASCII) |
| ✅ | `agent/tts-tools.py` | Swappable TTS: Chatterbox / **voxcpm** (Trendyol-TTS, TR) / **Piper** / SAPI + **batch mode** (`--batch-file`) + **persistent server** (`--serve`; chatterbox **or** piper) + **long-tail guard** (Chatterbox; duration limit + 1 retry; `--no-guard`) |
| ✅ | `agent/pipeline.ps1` | Pipeline (**batch/reference path**): ASR → LLM (HTTP) → sentence splitting → **batch**/**server** TTS; `-Ffmpeg` for ASR conversion, `-Piper`/`-PiperModel` for CPU TTS; the TTS server path now works for every backend |
| ✅ | `agent/llm-stream.py` | **Streaming turn engine:** `llama-server` **SSE** → incremental sentence splitting → TTS per sentence → background playback; timestamped JSON (`reasoning_content` ignored, symbol-only skipped, 2 attempts on a transient network error) |
| ✅ | `agent/pipeline-stream.ps1` | **Streaming** pipeline (ASR + `llm-stream.py`): emits the first audio early (principle #7); `-Ffmpeg` for ASR conversion |
| ⬜ | `agent/audio-capture.ps1` | Microphone capture: **ffmpeg dshow** -> 16 kHz mono 16-bit WAV (MCI fallback); device picker saved in `%LOCALAPPDATA%\altai\mic.txt` |
| `agent/fw-server.py` + `scripts/fw-server.ps1` | Persistent **faster-whisper (GPU)** STT server (port 8083, int8_float16, `/health` + `/transcribe`); warm-up on load |
| `scripts/measure-turn.ps1` | Timing harness: speech end -> first audio -> playback end -> next turn (wall-clock events from `llm-stream.py`) |
| ✅ | `tests/` | pytest (MTP injection + ASR tools) |
| ✅ | `scripts/`, `docs/` | setup/diagnostics, documentation |

## 5. Latency budget (target < 1000 ms)

| Stage | Target | Method |
|---|---|---|
| Endpoint | 0–200 ms | Push-to-talk = 0; VAD + ~200 ms threshold |
| STT | ≤ 400 ms | whisper.cpp `large-v3-turbo` (`medium`/`small` if needed). Measured: turbo ~10 s, medium ~7.5 s, small ~2.5 s, base ~0.84 s (CPU; ⚠️ the target is not met on this hardware) |
| LLM first token | ≤ 250 ms | Resident model + KV prefix cache |
| TTS first audio | ≤ 150 ms | **Piper (CPU, measured ~0.3–0.5 s)**; Chatterbox/Piper, on the first sentence. **Trendyol-TTS (`voxcpm`) is not suitable for live use** (RTF ~3, ~5.6 GB VRAM) — offline/high quality |

> **Measured (2026-10-18, streaming pipeline):** with Chatterbox, LLM+TTS first audio **7.05–7.60 s**
> (18.8 s in batch mode; 9.52 s with reasoning on). **With Piper (CPU) first audio is 0.77–0.90 s** —
> within the target (<1 s); Piper RTF 0.19, round-trip transcription WER 0.000. End to end (ASR turbo CPU
> ~9.9 s + streaming Piper) **~11.7 s**. **The only remaining bottleneck is STT (~10 s = ~85% of the
> end-to-end time)**; because whisper encodes its 30 s window on every request, short audio carries a fixed
> cost. Details: [`docs/streaming-pipeline.md`](docs/streaming-pipeline.md) §5.1/§5.2.

## 6. Critical pitfalls

1. **The app only runs with the embedded PowerShell 7.** `Start-ThreadJob` does not exist in 5.1.
2. **`$PSScriptRoot` is empty inside `Start-ThreadJob -FilePath`.** The root is carried via `$JobData.root`.
3. **Windows PowerShell 5.1 reads a `.ps1` without BOM as ANSI.** Keep 5.1 scripts ASCII or save them with a UTF-8 BOM.
4. **KV cache matching.** The UI's message array must be byte-for-byte identical to the server's.
5. **Use `Start-DetachedProcess`.** `Start-Process -Redirect…` inherits the caller's stdout.
6. **The VRAM margin is kept small.** 9B i1-Q5_K_M (~6.6 GB) + MTP + KV sits at the limit of an 8 GB card.
7. **The MTP flag is added only if the GGUF carries an MTP layer** (`Test-GgufHasMtp`). A quant GGUF
   does not contain MTP; it is added back with `mtp_inject.py` on download (see [`docs/mtp-verification.md`](docs/mtp-verification.md)).
8. **ASR/TTS share the CPU.** They do not run at the same time (listening vs speaking), but measurement is mandatory on a noisy machine.
9. **whisper.cpp thread count.** `-t` is set by measurement. ⚠️ The general "physical cores" rule does
   **not** apply here: on a Ryzen 5 3600, `-t 12` (logical) > `-t 6` (physical) was measured. The
   `asr-tools.py` default is logical cores.
10. **ASK the user before running heavy GPU work.** Jobs such as loading a model / GPU inference can make
    the user wait or collide with other GPU work; never start them without permission.
11. **The Windows console encoding (cp1254) breaks `print`.** Characters outside UTF-8 such as emoji in
    an LLM reply raise `UnicodeEncodeError`; in tools like TTS **stdout must be switched to UTF-8**
    (`sys.stdout.reconfigure`), otherwise the job fails completely. Also, in `.ps1` scripts **swallow the
    native tool's stdout** (`1> $null`) and read the JSON from a file — otherwise the output gets mixed
    into the function's return value.
12. **The repo path contains non-ASCII** ("Varsayılan" → `ı`). If an **absolute** path argument is passed
    to `Start-Process` the character is mangled (whisper-server opens the wrong path and crashes) →
    **relative path + `-WorkingDirectory`**.
13. **`whisper-server` requires `-ng`.** If it tries the GPU it crashes with `0xC0000409` (fast-fail);
    since STT runs on the CPU, `-ng` is both correct and necessary. In `llama-server`, values containing
    spaces such as `--reasoning-budget-message` must be quoted and the `=` form must not be used.
14. **Do not redirect Python output with PowerShell `1>`.** Windows PowerShell writes the output as
    **UTF-16** and takes Python's UTF-8 bytes for OEM (cp850), mangling Turkish characters (`ı` → `─▒`).
    Let **Python write the JSON to a file** (`--json-out` / `Path.write_text(encoding="utf-8")`) or use
    `pwsh` + `-Encoding utf8`; otherwise the `ı` in the path is mangled and `Test-Path` / `os.path.exists`
    returns a **false `False`** (misleading the measurement — this is exactly what happened on 2026-10-17).
15. **`Get-Content -Raw` (PS 5.1) reads a UTF-8 file without BOM as ANSI.** The `ı` in paths inside the
    JSON written by Python's `--json-out` is mangled → `Test-Path -LiteralPath` returns a **false `False`**
    (3 WAVs produced by the streaming pipeline looked "lost", 2026-10-18). Fix: **`Get-Content -Raw -Encoding UTF8`**.
    Also, instead of taking a native tool's JSON **piped from stdout**, have it written **to a file** with
    `--out`/`--json-out` (the ASR path works this way now) — the same class of bug as pitfall #14.
16. **Some binaries cannot read a non-ASCII path at all (they crash on an absolute path).** On a non-ASCII
    repo path: **Piper**'s espeak-ng layer gives `Illegal byte sequence`, onnxruntime `0xC0000409 (fast-fail)`;
    **`whisper-cli.exe`** crashes with `0xC0000409` on a non-ASCII **absolute** `-m`/`-f` path (on the same
    machine it works fine with a **relative** path — use `cwd` + a relative path). Fix: install Piper and
    the voice file into an **ASCII directory** (`scripts/install-piper.ps1` → `%LOCALAPPDATA%\altai\piper`);
    call whisper-cli with a **relative path**. (A generalisation of pitfall #12.)
17. **On Windows loopback ~30% of HTTP requests can fail with `WinError 10054` (RST)** (measured
    2026-10-21: the same happens with `urllib`/`http.client`/raw socket and in a minimal stdlib `http.server`
    repro → **environmental**, not server code). That is why HTTP calls are written with **retry**
    (`llm-stream.py` TTS call 2 attempts; `_post_json` 10 attempts in the tests) and a retried request must
    be **idempotent**: if the same request goes out again, the server produces the same audio a second time
    (harmless, a little CPU). That is also why the tests look at the result per request rather than at the
    sequence number.

18. **The CUDA build must match the GPU architecture.** On Blackwell (RTX 50xx, `sm_120`) the CUDA 12.4
    llama.cpp build only runs through PTX JIT: measured **9.8 tok/s** generation and **1.4 tok/s** prompt
    eval, while the CUDA 13.5 build of the same version gives **~91 tok/s** generation and **~135 tok/s**
    prompt eval on the same model/flags (MTP acceptance ~0.56). On 50-series cards install
    `llama-*-bin-win-cuda-13.5-x64.zip` + `cudart-*-cuda-13.5-x64.zip` and keep the CUDA runtime DLLs next
    to `llama-server.exe`. (Measured 2026-11-19, RTX 5060 Ti 16 GB, driver 621.24.)

19. **Never start a second server for the same model.** Two Chatterbox processes or two
    `fw-server.py` instances silently double VRAM. Check the **process list**, not only the port: while a
    model loads the HTTP port is not bound yet, and `tts-server.ps1 -Stop` used to leave orphans. Note
    that a venv `python.exe` is a **launcher**: `python.exe` (4 MB) plus the real interpreter as its child
    are **one** server, not two.

20. **Chatterbox hardcodes `max_new_tokens=1000`.** A short sentence ("Merhaba!") can therefore spend
    6-16 s before EOS. Budget the sampler from the expected duration (~30 tokens/s) in
    `synth_chatterbox`; measured effect: worst case ~16 s -> ~3 s. Do not lower it blindly: too small a
    budget cuts the utterance.

21. **Thinking text leaks into the answer unless the server uses `--reasoning-format deepseek`.**
    With `--reasoning on` and the default format, Qwen3.5 sometimes emits its self-check ("Wait, let's
    count again...") as **content**, which then goes to TTS. Use `--reasoning on --reasoning-budget 128
    --reasoning-format deepseek`; `llm-stream.py` ignores `reasoning_content` and only speaks `content`.

22. **VRAM tuning (16 GB profile).** Measured: LLM ~7.0 GB with `-c 4096 --parallel 1 -ctk q8_0
    -ctv q8_0` (0.75 GB less than the default KV setup, same ~85-91 tok/s), STT (int8_float16)
    ~1.2 GB, Chatterbox **~3.3 GB** (fp32 floor; `half()` fails with "mat1 and mat2 must have the same
    dtype"). Total ~11.6 GB. Free the warm-up arena with `torch.cuda.empty_cache()` and set
    `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`; without them the process sat ~15.6 GB.

## 7. Change checklist

- [ ] Is MTP still on? (Hard rule)
- [ ] Is the LLM still i1-Q5_K_M (Huihui-Qwen3.5-9B-abliterated)?
- [ ] Is STT still whisper.cpp (not reverted to Qwen3-ASR)?
- [ ] Is the language model still resident (not unloaded)?
- [ ] Has anything other than the LLM been moved to the GPU?
- [ ] Are the TR and ENG versions consistent?
- [ ] Are `README.md`, `docs/architecture.md`, `docs/mtp-verification.md`, `docs/phase2-measurement-plan.md`, `docs/phase2-results.md`, `docs/streaming-pipeline.md`, `docs/decisions.md` up to date?

## 8. Changelog

| Date | Change | Files |
|---|---|---|
| 2026-11-19 | **GPU-resident stack and desktop UI.** LLM 9B + MTP (~7.0 GB with `--parallel 1 -ctk q8_0 -ctv q8_0`), faster-whisper turbo on CUDA (~1.2 GB, RTF 0.04-0.10), Chatterbox on GPU (~3.3 GB, TF32, sampler cap, warm-up) -> **~11.6 GB total** on the 16 GB card. New: `altai-desktop.ps1` (Load models -> click to speak, VRAM readout, cleanup on close), `agent/audio-capture.ps1` (ffmpeg dshow 16 kHz mono; the MCI default was 11 kHz/8-bit), `agent/fw-server.py` + `scripts/fw-server.ps1` (persistent GPU STT), `scripts/measure-turn.ps1` (timeline). Voice-first system prompts (TR/EN, max 2 sentences) and `--reasoning-format deepseek` so thinking text cannot leak into TTS. Measured: first audio **~4.9-7.2 s** (Chatterbox's first sentence is 3-5 s), ASR 0.5 s, LLM TTFT 0.25-0.4 s. **60 tests.** | altai-desktop.ps1, agent/, scripts/, AGENTS.md |
| 2026-11-19 | **Full hardware test on RTX 5060 Ti (16 GB, driver 621.24) and first real end-to-end runs.** LLM (CUDA 13.5 build, MTP on): **91.4 tok/s** generation, **135 tok/s** prompt eval, **TTFT 0.41 s**, MTP draft acceptance 0.56. Streaming pipeline: **FIRST AUDIO 1.045 s** with `-NoThink` (1.08 s text-only), **3.68 s** with reasoning on; ASR turbo on CPU **9.9–10.0 s** (RTF 1.45–1.46); Piper **RTF 0.21–0.27**; batch turn produced 5 WAVs in ~15 s. **Fixes found by the test:** `install-piper.ps1` flattens the release zip's `piper/` folder; `pipeline.ps1` gained `-Ffmpeg` and `-Piper`/`-PiperModel`, and its TTS server path now works for every backend; `pipeline-stream.ps1` gained `-Ffmpeg`. **New pitfall #18:** the CUDA 12.4 llama.cpp build on Blackwell runs at 9.8 tok/s while the CUDA 13.5 build does ~91 tok/s. **59 tests green.** | AGENTS.md, agent/pipeline.ps1, agent/pipeline-stream.ps1, scripts/install-piper.ps1 |
| 2026-11-18 | **Repository fully translated into English; first tagged release (`v0.1.0`).** All documentation, code comments, docstrings, console/log messages and user-facing error text translated. Turkish document and tool names renamed: `DURUM.md`→`STATUS.md`, `BASLA.md`→`START.md`, `docs/mimari.md`→`docs/architecture.md`, `kararlar.md`→`decisions.md`, `mtp-dogrulama.md`→`mtp-verification.md`, `faz2-olcum-plani.md`→`phase2-measurement-plan.md`, `faz2-sonuc.md`→`phase2-results.md`, `tts-kiyaslama.md`→`tts-benchmark.md`, `tts-tr-sonuc.md`→`tts-tr-results.md`, `akishli-hat.md`→`streaming-pipeline.md`; `agent/mtp-durum.py`→`agent/mtp-status.py`, `scripts/mtp-dogrula.ps1`→`scripts/mtp-verify.ps1`, `scripts/asr-olcum.ps1`→`scripts/asr-benchmark.ps1`, `scripts/piper-kur.ps1`→`scripts/install-piper.ps1`. Turkish TTS test sentences and pronunciation examples kept verbatim. Token-level verification: only comments/strings changed, no code logic; **59 tests green**. | all |
| 2026-10-21 | **Flaky server tests made resilient to retries.** Measurement: on Windows loopback **~30%** of consecutive HTTP requests fail with `WinError 10054` (RST); the same happens in a repro with a minimal stdlib server + raw socket → **environmental** (not server code). In the tests: a separate `prefix` per request + verification with a **last** call per request (when a retry synthesised the same batch a second time, the order-based assert slipped — `test_tts_server_passes_respell_switches_per_request`, `test_tts_server_piper_dispatch`) and 10 attempts in `_post_json`. Mutation check: the tests still catch it when the `tr_raw` wiring is broken and when the piper argument order is swapped. **59 tests, 10/10 green.** | tests/test_tts_tools.py, AGENTS.md |
| 2026-10-21 | **Repository and product name became Altai** (`github.com/workaybarsh/altai`); the "local AI chatbot assistant" positioning was applied to the README/AGENTS headings, Piper directory `%LOCALAPPDATA%\altai\piper` (decision #25). | README.md, AGENTS.md, STATUS.md, START.md, docs/architecture.md, docs/decisions.md, agent/, scripts/ |
| 2026-10-19 | **MIT license added** (`LICENSE`; copyright holder `workaybarsh`); decision #24 recorded, the README license section and usage line updated. | LICENSE, README.md, docs/decisions.md, AGENTS.md |
| 2026-10-19 | Repository name **aybars_speaks** (became **Altai** on 2026-10-21); texts updated. | all |
| 2026-10-18 | **Chatterbox `ğ` pronunciation bug found and fixed (user's ear → measurement).** Complaint: `çalıştığı` → "çalıştı ki". Round-trip transcription confirmed it ("Tam yarar çalıştı ki işin…"). **Root cause:** `ğ` **is** in the grapheme dictionary, there is no NFKD decomposition → the bug is not in the tokenizer but in the **acoustic model**. New `tr_softg()`: `ğ` between two vowels → `y`, after a vowel before a consonant/finally → long vowel (`dağ`→`daa`); applied before `ş→sh`. **A/B (seed 42, same texts):** `çalıştığı` **fixed** (old patch "çalış dışı", without the patch "çalıtıcı"), word accuracy over 9 words **44% → 67%**, guard retry **23.2 → 5.0 s**. Disable: `--chatterbox-no-softg` / per request `{"softg": false}` (server A/B wiring). **Ear test ✅ (2026-10-18): the user said "yeni olan güzel" → the patch was accepted as the default (decision #23).** ⚠️ `yerel`/`için`/`Aybars` errors persist → Chatterbox TR is fragile. **59 tests** (+3). Measurement: `logs/softg-bench.py`, `logs/softg-asr.py`. | agent/tts-tools.py, scripts/tts-server.ps1, tests/test_tts_tools.py, docs/tts-benchmark.md (§9.4), docs/decisions.md (#23), STATUS.md, AGENTS.md |
| 2026-10-18 | **TTS bottleneck solved: Piper (CPU) wired into the streaming pipeline.** `tts-tools.py --serve --backend piper` + `scripts/tts-server.ps1 -Backend piper` + `scripts/install-piper.ps1` (install into an ASCII directory). **Measurement (same session, same prompt):** first audio **Chatterbox 4.2–7.6 s → Piper 0.77–0.90 s** (within the <1 s target); Piper `tr_TR-dfki-medium` **RTF 0.19**, round-trip transcription **WER 0.000** (5/5). End to end (ASR turbo ~9.9 s + Piper) **~11.7 s** → the only remaining bottleneck is **ASR (85%)**. Piper runs on the CPU (principle #1: the GPU entirely for the LLM) and produces no guard retry. **New pitfall #16:** Piper/onnxruntime and `whisper-cli` crash on a non-ASCII path (`Illegal byte sequence` / `0xC0000409`) → Piper in an ASCII directory, whisper-cli via a relative path. **54 tests** (+2: piper server path). | agent/tts-tools.py, scripts/tts-server.ps1, scripts/install-piper.ps1, tests/test_tts_tools.py, docs/streaming-pipeline.md, docs/tts-benchmark.md, STATUS.md, AGENTS.md, README.md |
| 2026-10-18 | **Streaming pipeline added (principle #7 in code).** `agent/llm-stream.py`: `llama-server` **SSE** → incremental sentence splitting → TTS per sentence → **background** playback (playback thread; `reasoning_content` ignored, symbol-only skipped) + `agent/pipeline-stream.ps1` (ASR wrapper). **Measurement (LLM+TTS): first audio 18.8 s → 7.05–7.60 s (~2.5×)**; 9.52 s with reasoning on; end to end (ASR turbo CPU 9.91 s) 13.4 s. **Findings:** on a short sentence the guard retry pushes first audio to 13–18 s — end-energy analysis showed the tail is **extra speech** (end trimming does not fix it). During measurement two real `ConnectionResetError`s were **transparently compensated**. **Critical fix:** PS 5.1 `Get-Content -Raw` was reading BOM-less UTF-8 as ANSI → streaming WAVs "lost" (pitfall #15); the ASR path moved to `--out` + UTF-8; the TTS server call is **2 attempts** (an honest error instead of falling back to local and OOMing). **52 tests.** | agent/llm-stream.py, agent/pipeline-stream.ps1, agent/pipeline.ps1, tests/test_llm_stream.py, docs/streaming-pipeline.md, docs/decisions.md, STATUS.md, AGENTS.md |
| 2026-10-17 | **Guard review: `out` path bug found and fixed.** When the retry won, `synth_chatterbox` returned the path of an already deleted `.retry.wav`; because `pipeline.ps1` used that field with `Test-Path`, **the corrected sentence could silently fail to play** (6 records in a 24-generation measurement). `out` is now the real file (the old path is `retry_out`), the pipeline has a defence that falls back to the file name, and `guard_extra_seconds` was added for measurement. Regression net: **3 tests fail** without the fix, **39 tests** with it. | agent/tts-tools.py, agent/pipeline.ps1, tests/test_tts_tools.py, docs/tts-benchmark.md, STATUS.md |
| 2026-10-17 | **TTS long-tail (hallucination) guard added.** Review finding: the "don't send empties" filters were preventing the **crash** (`IndexError: max()` / CUDA `device-side assert`); what trimmed the overflowing audio was Chatterbox's own `alignment_stream_analyzer` (`forcing EOS, long_tail=True`) — **two separate mechanisms** (decision #21). Guard: if `audio_guard_limit = max(3×expected, expected+2 s)` (expected ≈ letters/14) is exceeded, generate the sentence **once** more and keep the **shorter** one (`--no-guard` disables it). **GPU measurement (24 generations, 4 seeds): 7 triggers (29%), longest caught tail 6.04 s, 0 errors**; it never triggered on a long sentence; the persistent server path was verified. Empty/emoji-only input **never reaches** the model thanks to `ensure_speakable` (the batch does not fail). **38 tests**. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-benchmark.md, docs/decisions.md, STATUS.md, AGENTS.md |
| 2026-10-17 | **Persistent TTS server added** (`tts-tools.py --serve` + `scripts/tts-server.ps1`, port 8082). Measurement (4 sentences): sentence by sentence **106.6 s** → batch 48.4 s → **persistent server 16.6–18.5 s**. Full pipeline with three servers **~23–27 s per turn**. Because bad input can corrupt the CUDA context, the server rejects non-text elements with 400 and `/health` reports `fatal`. **32 tests**. Disk cleanup ~15 GB. | agent/tts-tools.py, agent/pipeline.ps1, scripts/tts-server.ps1, tests/, docs/tts-benchmark.md, STATUS.md, AGENTS.md |
| 2026-10-17 | **Pipeline wired to batch TTS + ASR optimised.** `pipeline.ps1` now generates all sentences in a single call (`--batch-file`+`--out-prefix`); the measurement went from **106.6 → 48.4 s** on 4 sentences. ASR: **f16→q5_0 quant** + logical threads → **RTF 4.2→1.9**; `-ac` rejected (repetition loop). Model comparison (base/small/medium/turbo). Support for a **persistent `whisper-server` process** (`--server-url`). Critical bug: `uses_mtl` NameError + emoji `UnicodeEncodeError` (it was killing batch generation) fixed. **30 tests**. PS7 installed (7.6.7). | agent/pipeline.ps1, agent/tts-tools.py, agent/asr-tools.py, scripts/whisper-server.ps1, scripts/asr-benchmark.ps1, tests/, docs/phase2-results.md, docs/decisions.md, STATUS.md, START.md, AGENTS.md |
| 2026-10-17 | **Pipeline ran end to end** (whisper→llama-server MTP→Chatterbox). LLM measured: ~103 tok/s, TTFT ~0.3 s, MTP acceptance ~0.7. Reasoning on + budget 256 verified. **Batch mode** added to `tts-tools.py`. | agent/pipeline.ps1, agent/tts-tools.py, STATUS.md, .gitignore, AGENTS.md |
| 2026-10-17 | **Chatterbox "ş" respell fix:** `ş→sh` confirmed in an ear test → automatic for TR (`--lang tr`). **20 tests**. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-benchmark.md, docs/decisions.md, STATUS.md, AGENTS.md |
| 2026-10-17 | **Two hardware profiles (A: 8 GB VRAM/16 GB RAM · B: 16 GB VRAM/32 GB RAM)** added to the resource budget — model/CPU-GPU split, VRAM/RAM estimates and variants for B. | docs/architecture.md, STATUS.md, AGENTS.md |
| 2026-10-17 | **Root cause of the Chatterbox TR diacritic problem found and the patch written:** the tokenizer's `NFKD` + Turkish-insensitive `lower()` bug → `install_tr_tokenizer_fix()` / `--chatterbox-tr-fix` (offline, **19 tests**). Audio verification while the GPU was free. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-benchmark.md, docs/tts-tr-results.md, docs/decisions.md, STATUS.md, AGENTS.md |
| 2026-10-16 | **Independent Turkish TTS comparison recorded** (arXiv:2610.06057, Sestek): Chatterbox vs CosyVoice/OmniVoice/VoxCPM2/VITS. Chatterbox wins no metric and collapses on short sentences; VoxCPM2 leads on cloning/stability, CosyVoice on naturalness. Decision #17. | docs/tts-benchmark.md, docs/decisions.md, STATUS.md, README.md, AGENTS.md |
| 2026-10-16 | **Turkish TTS evaluated + `voxcpm` backend added.** Trendyol-TTS (VoxCPM2 + TR LoRA) measured: ~5.6 GB VRAM, RTF ~3, round-trip Whisper WER ~0.08 → **intelligible but heavy for the live pipeline**; added to `tts-tools.py` as an offline engine. Tests grew to 17. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-tr-results.md, docs/decisions.md, STATUS.md, README.md, AGENTS.md, docs/architecture.md |
| 2026-10-16 | **Phase 2 ASR pipeline skeleton added** (`asr-tools.py`, `asr-benchmark.ps1`) and **verified end to end with real whisper.cpp** (base.en, CPU, RTF ~0.19). Tests grew to 13. | agent/asr-tools.py, scripts/asr-benchmark.ps1, tests/, docs/phase2-measurement-plan.md, AGENTS.md |
| 2026-10-16 | **First working tool added:** `agent/mtp_inject.py` (proven) + `scripts/mtp-verify.ps1` status/injection script. The repository was marked as "voice". | agent/mtp_inject.py, scripts/mtp-verify.ps1, README.md, AGENTS.md |
| 2026-10-16 | **MTP verified and made mandatory.** The target quant GGUF has no MTP; the source has 15 tensors; `mtp_inject.py` is required. A verification + acceptance tests document was added. | README.md, AGENTS.md, docs/architecture.md, docs/decisions.md, docs/mtp-verification.md |
| 2026-10-16 | LLM fixed as **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (mradermacher imatrix quant). | README.md, AGENTS.md, docs/architecture.md, docs/decisions.md |
| 2026-10-16 | STT reverted from **Qwen3-ASR to whisper.cpp** (`large-v3-turbo`). | README.md, AGENTS.md, docs/architecture.md, docs/phase2-measurement-plan.md, docs/decisions.md |
| 2026-10-11 | **Status** section added to the README: draft (`v0.1-plan`), no code, R&D fallback paths noted. | README.md, AGENTS.md |
| 2026-10-11 | "Evaluated and rejected alternatives" section added. | docs/decisions.md, docs/architecture.md |
| 2026-10-11 | STT moved from whisper to **Qwen3-ASR-1.7B** (at the time); speed fallback 0.6B. | all |
| 2026-10-11 | Turn sequence + responsibility table added to the architecture; Phase 2 measurement plan. | docs/architecture.md, docs/phase2-measurement-plan.md |
| 2026-10-11 | Model aligned with MamidLabs LITE. | all |
| 2026-10-11 | Repository opened; plan written. | all |
