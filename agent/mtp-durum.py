#!/usr/bin/env python3
"""mtp-durum.py -- Bir GGUF'un MTP/nextn basligi durumunu JSON olarak yazar.

`agent/mtp_inject.py`'nin basligini okur; enjeksiyon yapmaz. Kabuk betikleri
(PowerShell) bu ciktiyi ayristirir. Boylece kod `python -c "..."` ile gecirilmez ve
PowerShell'in tirnak/tirnak kacisi tuzagina dusulmez.

Kullanim:
  python agent/mtp-durum.py <gguf>
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtp_inject as m  # noqa: E402


def durum(path: str) -> dict:
    version, meta, tensors, _data_start = m.read_header(path)
    d = {k: v for k, _t, v in meta}
    return {
        "file": path,
        "size_mb": round(os.path.getsize(path) / 1048576, 1),
        "gguf_version": version,
        "arch": d.get("general.architecture"),
        "block_count": d.get("qwen35.block_count"),
        "nextn_predict_layers": d.get("qwen35.nextn_predict_layers"),
        "tensor_count": len(tensors),
        "nextn_tensor_count": sum(1 for t in tensors if ".nextn." in t[0]),
        "has_mtp": m.has_mtp(path),
    }


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print(json.dumps({"ok": False, "error": "kullanim: mtp-durum.py <gguf>"}))
        return 2
    path = argv[0]
    if not os.path.exists(path):
        print(json.dumps({"ok": False, "error": f"bulunamadi: {path}"}))
        return 2
    out = durum(path)
    out["ok"] = True
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
