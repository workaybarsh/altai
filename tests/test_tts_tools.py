"""tts-tools.py'nin saf (cevrimdisi) davranislarini dogrular."""
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("tts_tools", os.path.join(ROOT, "agent", "tts-tools.py"))
tts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tts)


def test_empty_text_returns_error(tmp_path, capsys):
    out = tmp_path / "x.wav"
    code = tts.main(["--backend", "sapi", "--text", "   ", "--out", str(out)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False


def test_missing_piper_reports_error(tmp_path, capsys):
    code = tts.main(["--backend", "piper", "--text", "merhaba", "--out", str(tmp_path / "a.wav"),
                     "--piper", "kesinlikle-olmayan-piper-x"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["ok"] is False
    assert "piper" in payload["error"].lower()


def test_sapi_synthesizes_on_windows(tmp_path, capsys):
    if os.name != "nt":
        import pytest
        pytest.skip("SAPI yalnizca Windows")
    out = tmp_path / "sapi.wav"
    code = tts.main(["--backend", "sapi", "--text", "Merhaba dunya", "--out", str(out)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["ok"] is True
    assert os.path.exists(out)
    assert payload["audio_seconds"] > 0


def test_voxcpm_missing_dependency_reports_error(tmp_path, capsys):
    """voxcpm kurulu degilse durustce ok=false doner (agir model indirmeyi tetiklemez)."""
    import pytest
    try:
        import voxcpm  # noqa: F401
    except Exception:
        pass
    else:
        pytest.skip("voxcpm kurulu; agir model yuklemeyi tetiklememek icin atlanir")
    out = tmp_path / "v.wav"
    code = tts.main(["--backend", "voxcpm", "--text", "merhaba", "--out", str(out)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["ok"] is False
    assert payload["backend"] == "voxcpm"


def test_tr_lower_is_turkish_aware():
    assert tts.tr_lower("İSTANBUL IĞDIR") == "istanbul ığdır"


def test_tr_respell_maps_s_to_sh():
    assert tts.tr_respell("Çalışan şair, şaşkın şarkı") == "Çalıshan shair, shashkın sharkı"


def test_install_tr_tokenizer_fix_keeps_precomposed():
    import unicodedata

    class FakeTok:
        def preprocess_text(self, raw_text, language_id=None, lowercase=True, nfkd_normalize=True):
            t = raw_text.lower() if lowercase else raw_text
            return unicodedata.normalize("NFKD", t) if nfkd_normalize else t

    tok = tts.install_tr_tokenizer_fix(FakeTok())
    tr = tok.preprocess_text("ŞÜĞÖÇ IĞDIR", language_id="tr")
    assert "ş" in tr and "ü" in tr and "ı" in tr          # diakritikler korunur
    assert "\u0308" not in tr and "\u0327" not in tr      # NFKD ile ayrismaz
    en = tok.preprocess_text("Ş", language_id="en")       # tr disi: orijinal NFKD
    assert "\u0327" in en


def test_synth_chatterbox_mtl_sets_language_id(monkeypatch, tmp_path):
    """Regresyon: `uses_mtl` tanimli olmali; aksi halde chatterbox yolu NameError verirdi."""
    import sys
    import types

    fake_torch = types.ModuleType("torch")
    fake_torch.manual_seed = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    saved = {}
    monkeypatch.setattr(tts, "_save_wav",
                        lambda wav, path, sr: saved.update(path=path, sr=sr) or "stub")

    class FakeTok:
        def preprocess_text(self, t, language_id=None, lowercase=True, nfkd_normalize=True):
            return t

    class FakeWav:
        shape = (1, 24000)

    class FakeModel:
        sr = 24000
        tokenizer = FakeTok()

        def generate(self, text, **kw):
            return FakeWav()

    out = tmp_path / "a.wav"
    res = tts.synth_chatterbox("Çalışan şair", str(out), lang="tr", model=FakeModel())
    assert res["language_id"] == "tr"          # MTL yolu secildi
    assert res["t3_model"] == "v3"
    assert saved["path"] == str(out)


def test_json_handles_emoji_without_crashing(tmp_path):
    """LLM ciktisindaki emoji konsol kodlamasinda print'i patlatmamali (toplu modu dusururdu)."""
    out = tmp_path / "j.json"
    tts._json({"ok": True, "text": "merhaba 😊 dünya"}, str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["text"] == "merhaba 😊 dünya"


def test_batch_mode_rejects_non_chatterbox(tmp_path, capsys):
    bf = tmp_path / "b.txt"
    bf.write_text("bir\niki\n", encoding="utf-8")
    code = tts.main(["--backend", "piper", "--batch-file", str(bf),
                     "--out-prefix", str(tmp_path / "o_"), "--piper", "yok"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["ok"] is False
    assert "chatterbox" in payload["error"].lower()


def test_batch_missing_file_reports_error(tmp_path, capsys):
    code = tts.main(["--backend", "chatterbox", "--batch-file", str(tmp_path / "yok.txt"),
                     "--out-prefix", str(tmp_path / "o_")])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert "bulunamadi" in payload["error"]


def test_batch_needs_out_prefix_or_out(tmp_path, capsys):
    bf = tmp_path / "b.txt"
    bf.write_text("bir\n", encoding="utf-8")
    code = tts.main(["--backend", "chatterbox", "--batch-file", str(bf)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert "out-prefix" in payload["error"]
