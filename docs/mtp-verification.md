# MTP (Multi-Token Prediction) — Verification and Injection Plan

> This document defines the verification and re-injection steps required for the hard rule
> "**MTP always on**" to **actually work**.

## 1. Why this document

Quantised GGUF files **do not contain the MTP (nextn) header**: the HF → GGUF converter
leaves the MTP layers out. Therefore, if the `--spec-type draft-mtp` flag is passed to the model,
llama.cpp **does not start**. To use MTP, the header must be **injected back** into the GGUF.

## 2. Verified findings (2026-10-16)

| Check | Result | Evidence |
|---|---|---|
| Target GGUF: `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF` → `i1-Q5_K_M.gguf` | **NO MTP** | `nextn` = 0 matches in the header; `nextn_predict_layers` absent |
| Source repo: `huihui-ai/Huihui-Qwen3.5-9B-abliterated` | **15 MTP tensors present** | `mtp.*` tensors are present in shard 2/3/4 |
| Source tensors ↔ `mtp_inject.py` MAP | **Exact match** | The 15 names below |

So: **the target model does not contain MTP, the source supplies MTP → injection is necessary and possible.**

### 2.1 Source MTP tensors (15)

```
mtp.fc.weight
mtp.layers.0.input_layernorm.weight
mtp.layers.0.post_attention_layernorm.weight
mtp.layers.0.self_attn.q_proj.weight
mtp.layers.0.self_attn.k_proj.weight
mtp.layers.0.self_attn.v_proj.weight
mtp.layers.0.self_attn.o_proj.weight
mtp.layers.0.self_attn.q_norm.weight
mtp.layers.0.self_attn.k_norm.weight
mtp.layers.0.mlp.gate_proj.weight
mtp.layers.0.mlp.down_proj.weight
mtp.layers.0.mlp.up_proj.weight
mtp.pre_fc_norm_embedding.weight
mtp.pre_fc_norm_hidden.weight
mtp.norm.weight
```

## 3. Solution: `mtp_inject.py` (a tool proven in MamidLabs)

The same problem is already solved in MamidLabs. The same worker is reused.

**What it does:**
1. Reads the safetensors header of the source HF repository via an HTTP range download.
2. Pulls only the **15 MTP tensors** (not the whole model).
3. Appends them to the end of the existing GGUF under the name `blk.<N>.nextn.*`.
4. Adds `qwen35.nextn_predict_layers = 1` to the metadata and raises `qwen35.block_count` by +1.
5. Applies **+1** to the 1-D (F32) norm tensors (llama.cpp GGUF normalisation rule).
6. **Does not touch** the main model weights → lossless.

**Properties:** architecture check (must be `qwen35`), idempotent (skips if already present via `has_mtp`),
atomic write (tmp + `os.replace`), 4 retries against network flakiness.

## 4. Implementation steps (concrete)

```powershell
# 1) Download the target GGUF (with size verification)
#    models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf

# 2) Inject the MTP header (source = base abliterated repo)
python mtp_inject.py `
  "models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf" `
  "huihui-ai/Huihui-Qwen3.5-9B-abliterated"

# 3) Verify: has_mtp == True
# 4) Start the server with MTP (using the flags below)
```

From the programming interface:

```python
from mtp_inject import ensure_mtp, has_mtp
ensure_mtp(target_gguf, {'repo': 'huihui-ai/Huihui-Qwen3.5-9B-abliterated'})
assert has_mtp(target_gguf)
```

## 5. Evidence / acceptance tests (work is not done until these pass)

- [ ] **T1 — Injection:** `has_mtp(gguf) == True` (`False` before).
- [ ] **T2 — Metadata:** `general.architecture == qwen35`; `nextn_predict_layers == 1`;
      `block_count` = old value + 1.
- [ ] **T3 — Server start:** `llama-server ... --spec-type draft-mtp` starts without errors
      (supplied without MTP it does not start — that is also the negative control).
- [ ] **T4 — MTP active:** the MTP/draft-spec path is visible as active in the server log.
- [ ] **T5 — Speed gain:** throughput is measured for the same prompt with MTP **on vs off**; on ≥ off
      (expected on the order of ~2x, less at 8 GB).
- [ ] **T6 — Losslessness:** no meaningful output difference for the same prompt with MTP on/off (lossless).
- [ ] **T7 — Restart:** after the application is closed and reopened the injection is **not repeated** (idempotent).

## 6. llama-server flags (target)

```
llama-server
  -m models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf
  --spec-type draft-mtp          # if MTP is present; otherwise a THIRD one is not added either
  -c 32768
  -ngl 99
  ...
```

- The flag is added **only if the GGUF really carries MTP** (`Test-GgufHasMtp` / `gguf_has_mtp`).
- The llama.cpp build is pinned (same as MamidLabs: **b10998**). The flag name depends on the build version
  (llama.cpp has renamed the `--spec-type` argument in the past); therefore the **version is kept fixed**.

## 7. VRAM note

The MTP header means **an additional transformer block** (~hundreds of MB) + draft context. On the target 8 GB card,
`i1-Q5_K_M` (~6.6 GB) + MTP + KV is already at the limit; **VRAM must be re-measured after injection**.
If it does not fit:

1. `i1-Q4_K_M` (~5.6 GB) — drop the quant,
2. set the KV cache to `q4_0`,
3. lower the `-c` context.

## 8. Risks and fallbacks

| Risk | Fallback |
|---|---|
| The GGUF is corrupted after injection | Re-download the original file; repeat the injection |
| `qwen35` architecture unrecognised / `block_count` missing | Fall back to the source `huihui-ai` GGUF |
| nextn behaves unexpectedly with the imatrix quant | Use the original `huihui-ai` **static** Q5_K_M |
| MTP does not fit in 8 GB | `settings.mtp = false` + `i1-Q4_K_M` |
| The llama.cpp flag name changes | Pin the build to **b10998** |

## 9. Conclusion

- **In this project MTP is not optional, it is mandatory.** The target quant GGUF has no MTP → `mtp_inject.py` is required.
- The source tensors are **verified**; the mechanism is **proven** in MamidLabs.
- Transition criterion: **the T1–T7 tests must pass.**
