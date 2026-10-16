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
