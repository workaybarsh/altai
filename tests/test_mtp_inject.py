"""Verifies the core logic of MTP header injection offline.

No real GGUF download is needed: a small, synthetic `qwen35` GGUF is built and
synthetic MTP tensors are injected. This way the logic of the T1/T2/T7 acceptance
tests runs fast and without a network.

For the acceptance tests see docs/mtp-verification.md.
"""
import struct

import pytest

import mtp_inject as m

# The 15 MTP tensors verified in the source repo (see docs/mtp-verification.md)
EXPECTED_MTP = {
    "mtp.fc.weight",
    "mtp.layers.0.input_layernorm.weight",
    "mtp.layers.0.post_attention_layernorm.weight",
    "mtp.layers.0.self_attn.q_proj.weight",
    "mtp.layers.0.self_attn.k_proj.weight",
    "mtp.layers.0.self_attn.v_proj.weight",
    "mtp.layers.0.self_attn.o_proj.weight",
    "mtp.layers.0.self_attn.q_norm.weight",
    "mtp.layers.0.self_attn.k_norm.weight",
    "mtp.layers.0.mlp.gate_proj.weight",
    "mtp.layers.0.mlp.down_proj.weight",
    "mtp.layers.0.mlp.up_proj.weight",
    "mtp.pre_fc_norm_embedding.weight",
    "mtp.pre_fc_norm_hidden.weight",
    "mtp.norm.weight",
}

STRING, U32, F32 = 8, 4, 0
ALIGN = 32


def _s(v):
    b = v.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def _align_up(x, a=ALIGN):
    return (x + a - 1) // a * a


def build_synthetic_gguf(path, block_count=1, arch="qwen35"):
    """Writes a minimal but valid GGUF (a single dummy tensor)."""
    meta = [
        _s("general.architecture") + struct.pack("<I", STRING) + _s(arch),
        _s(f"{arch}.block_count") + struct.pack("<I", U32) + struct.pack("<I", block_count),
    ]
    tensors = [("token_embd.weight", [4], F32, 0)]
    with open(path, "wb") as f:
        f.write(b"GGUF")
        f.write(struct.pack("<I", 3))                 # version
        f.write(struct.pack("<Q", len(tensors)))      # tensor count
        f.write(struct.pack("<Q", len(meta)))         # kv count
        for kv in meta:
            f.write(kv)
        for name, dims, ttype, off in tensors:
            f.write(_s(name))
            f.write(struct.pack("<I", len(dims)))
            for d in dims:
                f.write(struct.pack("<Q", d))
            f.write(struct.pack("<I", ttype))
            f.write(struct.pack("<Q", off))
        f.write(b"\x00" * ((-f.tell()) % ALIGN))
        f.write(struct.pack("<4f", 1.0, 2.0, 3.0, 4.0))  # token_embd data


def fake_mtp_tensors():
    """Tiny synthetic tensors with the same keys as `mtp_inject.MAP`."""
    out = {}
    for hf in m.MAP:
        if "norm" in hf:                      # 1-D norms -> F32
            out[hf] = {"dtype": "F32", "shape": [4],
                       "raw": struct.pack("<4f", 0.5, 0.5, 0.5, 0.5)}
        else:                                 # large matrices -> F16
            out[hf] = {"dtype": "F16", "shape": [8, 4], "raw": b"\x00" * (8 * 4 * 2)}
    return out


def meta_dict(path):
    _v, meta, _t, _d = m.read_header(path)
    return {k: v for k, _t, v in meta}


def test_map_has_exactly_the_15_verified_tensors():
    assert set(m.MAP.keys()) == EXPECTED_MTP


def test_has_mtp_false_for_missing_file():
    assert m.has_mtp("does-not-exist.gguf") is False


def test_has_mtp_false_before_injection(tmp_path):
    p = tmp_path / "model.gguf"
    build_synthetic_gguf(str(p), block_count=1)
    assert m.has_mtp(str(p)) is False


def test_injection_adds_mtp_t1_t2(tmp_path):
    p = tmp_path / "model.gguf"
    build_synthetic_gguf(str(p), block_count=1)
    _v, _meta, base_tensors, _d = m.read_header(str(p))

    m.inject_into_gguf(str(p), fake_mtp_tensors(), emit=lambda *_: None)

    # T1: MTP is now present
    assert m.has_mtp(str(p)) is True
    d = meta_dict(str(p))
    # T2: header data
    assert d["general.architecture"] == "qwen35"
    assert d["qwen35.nextn_predict_layers"] == 1
    assert d["qwen35.block_count"] == 2  # 1 + 1

    _v2, _meta2, tensors2, _d2 = m.read_header(str(p))
    names = [t[0] for t in tensors2]
    assert len(tensors2) == len(base_tensors) + len(m.MAP)
    assert "blk.1.attn_norm.weight" in names          # MTP block sits at the old block_count index
    assert sum(1 for n in names if ".nextn." in n) == 4  # eh_proj, enorm, hnorm, shared_head_norm


def test_injection_is_idempotent_t7(tmp_path):
    p = tmp_path / "model.gguf"
    build_synthetic_gguf(str(p), block_count=1)
    m.inject_into_gguf(str(p), fake_mtp_tensors(), emit=lambda *_: None)
    _v, _m, tensors_after_first, _d = m.read_header(str(p))

    # Second call: must see the header and skip, adding no tensors
    m.inject_into_gguf(str(p), fake_mtp_tensors(), emit=lambda *_: None)
    _v2, _m2, tensors_after_second, _d2 = m.read_header(str(p))
    assert len(tensors_after_second) == len(tensors_after_first)


def test_injection_rejects_non_qwen35(tmp_path):
    p = tmp_path / "other.gguf"
    build_synthetic_gguf(str(p), block_count=1, arch="llama")
    with pytest.raises(RuntimeError):
        m.inject_into_gguf(str(p), fake_mtp_tensors(), emit=lambda *_: None)
