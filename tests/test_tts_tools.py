"""tts-tools.py'nin saf (cevrimdisi) davranislarini dogrular."""
import importlib.util
import json
import os

import pytest

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


def test_tr_softg_turkish_rules():
    # iki unlu arasi -> 'y'
    assert tts.tr_softg("değil") == "deyil"
    assert tts.tr_softg("ağaç") == "ayaç"
    assert tts.tr_softg("kağıt") == "kayıt"
    # unluden sonra onsoz/son -> onceki unlu uzatilir (Turkce'de ğ hep unluden sonra gelir)
    assert tts.tr_softg("dağ") == "daa"
    assert tts.tr_softg("yağmur") == "yaamur"
    assert tts.tr_softg("öğretmen") == "ööretmen"
    assert tts.tr_softg("mağdur") == "maadur"
    assert tts.tr_softg("iğne") == "iine"
    # onsozden sonra (nadir/odunc) -> 'g'
    assert tts.tr_softg("xğx") == "xgx"


def test_tr_softg_leaves_other_text_alone():
    assert tts.tr_softg("merhaba dünya") == "merhaba dünya"
    assert tts.tr_respell("Harika Aybars!") == "Harika Aybars!"


def test_tr_respell_fixes_the_broken_sentence():
    # Kulakla sikayet edilen ornek: 'çalıştığı' -> 'çalıştı ki' cikiyordu.
    src = "Tam yerel çalıştığı için cevaplarım hem hızlı hem de gizli."
    assert tts.tr_respell(src) == "Tam yerel çalıshtıyı için cevaplarım hem hızlı hem de gizli."


def test_tr_respell_softg_can_be_disabled():
    """A/B ve geri donus: softg=False -> eski davranis ('ş'->'sh' kalir, 'ğ' dokunulmaz)."""
    out = tts.tr_respell("değil dağ çalıştığı", softg=False)
    assert out == "değil dağ çalı" + "sh" + "tığı"   # 'ş' -> s+h, 'ğ' dokunulmaz
    assert tts.tr_respell("değil dağ", softg=True) == "deyil daa"


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


# ---------------------------------------------------------------- uzun-kuyruk guard

def _stub_chatterbox(monkeypatch, durations):
    """Chatterbox'i taklit eder: `durations` sirasiyla doner, _save_wav gercek dosya yazar."""
    import sys
    import types

    fake_torch = types.ModuleType("torch")
    fake_torch.manual_seed = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    saved = {}

    def fake_save(wav, path, sr):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"RIFF")
        saved[path] = round(wav.shape[-1] / sr, 3)
        return "stub"

    monkeypatch.setattr(tts, "_save_wav", fake_save)

    class FakeTok:
        def preprocess_text(self, t, language_id=None, lowercase=True, nfkd_normalize=True):
            return t

    calls = {"n": 0}

    class FakeWav:
        def __init__(self, secs):
            self.shape = (1, int(24000 * secs))

    class FakeModel:
        sr = 24000
        tokenizer = FakeTok()

        def generate(self, text, **kw):
            i = min(calls["n"], len(durations) - 1)
            calls["n"] += 1
            return FakeWav(durations[i])

    return FakeModel(), calls, saved


def test_expected_audio_and_guard_limit():
    assert tts.expected_audio_seconds("") == 0.0
    assert tts.expected_audio_seconds("Merhaba!") == pytest.approx(0.5)   # 7 harf / 14
    # "Merhaba!" icin sinir = max(3*0,5 ; 0,5+2,0) = 2,5 sn
    assert tts.audio_guard_limit("Merhaba!") == pytest.approx(2.5)
    # uzun cumlede sinir buyur (yanlis pozitif olmasin)
    assert tts.audio_guard_limit("Bugün size nasıl yardımcı olabilirim?") > 4.0


def test_synth_chatterbox_retries_when_audio_too_long(monkeypatch, tmp_path):
    """9,6 sn'lik 'Merhaba!' (tts_batch.json vakasi) -> yeniden uret, kisa olani tut."""
    model, calls, saved = _stub_chatterbox(monkeypatch, [9.6, 0.9])
    out = tmp_path / "m.wav"
    res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model)

    assert calls["n"] == 2                      # bir kez daha uretildi
    assert res["retried"] is True
    assert res["long_tail_guard"] is True
    assert res["audio_seconds"] == pytest.approx(0.9, abs=0.01)   # kisa olan tutuldu
    assert res["first_audio_seconds"] == pytest.approx(9.6, abs=0.01)
    assert os.path.exists(out)                  # kisa cikti asil yola tasindi
    assert not os.path.exists(str(out) + ".retry.wav")
    assert res["out"] == str(out)               # ⚠️ regresyon: yol .retry.wav'a kaymamali
    assert res["guard_extra_seconds"] == res["tts_seconds"]   # telafi = retry uretimi


def test_synth_chatterbox_keeps_first_when_retry_longer(monkeypatch, tmp_path):
    model, calls, saved = _stub_chatterbox(monkeypatch, [9.6, 12.0])
    out = tmp_path / "m2.wav"
    res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model)

    assert calls["n"] == 2
    assert res["retried"] is True
    assert res["first_audio_seconds"] == pytest.approx(9.6, abs=0.01)   # ilk deneme
    assert res["audio_seconds"] == pytest.approx(9.6, abs=0.01)   # ilki daha kisa
    assert res["retry_audio_seconds"] == pytest.approx(12.0, abs=0.01)
    assert not os.path.exists(str(out) + ".retry.wav")            # gecici dosya silindi
    assert res["out"] == str(out) and os.path.exists(res["out"])  # ilk cikti yerinde
    assert res["guard_extra_seconds"] >= 0                        # telafi maliyeti kaydi


def test_synth_chatterbox_retry_result_points_to_real_file(monkeypatch, tmp_path):
    """Her durumda `out` diskte VAR olan dosyayi gostermeli (pipeline Test-Path kullaniyor)."""
    durations = {"a": ([9.6, 0.9], True), "b": ([9.6, 12.0], True), "c": ([1.0], False)}
    for name, (durs, should_retry) in durations.items():
        model, calls, saved = _stub_chatterbox(monkeypatch, durs)
        out = tmp_path / f"{name}.wav"
        res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model)
        assert bool(res.get("retried", False)) is should_retry
        assert res["out"] == str(out)
        assert os.path.exists(res["out"])           # bayat .retry.wav yolu DEGIL


def test_synth_chatterbox_no_retry_when_normal(monkeypatch, tmp_path):
    model, calls, saved = _stub_chatterbox(monkeypatch, [1.2])
    out = tmp_path / "n.wav"
    res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model)

    assert calls["n"] == 1
    assert "retried" not in res
    assert res["audio_seconds"] == pytest.approx(1.2, abs=0.01)


def test_synth_chatterbox_guard_can_be_disabled(monkeypatch, tmp_path):
    model, calls, saved = _stub_chatterbox(monkeypatch, [9.6])
    out = tmp_path / "g.wav"
    res = tts.synth_chatterbox("Merhaba!", str(out), lang="tr", model=model, guard=False)

    assert calls["n"] == 1
    assert "retried" not in res
    assert res["audio_seconds"] == pytest.approx(9.6, abs=0.01)


def test_server_texts_normalizes_single_and_list():
    assert tts.server_texts({"texts": "tek"}) == ["tek"]
    assert tts.server_texts({"text": "tek"}) == ["tek"]
    assert tts.server_texts({"texts": ["a", " b ", ""]}) == ["a", "b"]
    assert tts.server_texts({}) == []
    # metin olmayan oge reddedilir (bozuk girdi CUDA baglamini zehirleyebiliyor)
    import pytest as _pytest
    with _pytest.raises(ValueError):
        tts.server_texts({"texts": [{"value": "x"}]})


def test_ensure_speakable_rejects_symbol_only():
    """Sembol-only/emoji girdi uretime HIC gitmez (Chatterbox orada patliyordu)."""
    assert tts.ensure_speakable("Merhaba") == "Merhaba"
    assert tts.ensure_speakable("3 elma") == "3 elma"
    for bad in ("", "   ", "???", "!!! ...", "\U0001f60a"):
        with pytest.raises(ValueError):
            tts.ensure_speakable(bad)


def test_tts_server_health_and_tts(monkeypatch, tmp_path):
    """Kalici sunucu: /health ve /tts calisir (model fonksiyonlari taklit; GPU gerekmez)."""
    import threading
    import time
    import types
    import urllib.request

    monkeypatch.setattr(tts, "load_chatterbox", lambda **kw: object())

    def fake_synth(text, out_wav, *a, **k):
        os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
        with open(out_wav, "wb") as f:
            f.write(b"RIFF")
        return {"out": out_wav, "audio_seconds": 1.0, "tts_seconds": 0.5, "text": text}

    monkeypatch.setattr(tts, "synth_chatterbox", fake_synth)

    def post(url, data):
        # Windows loopback'ta nadir gorulen gecici reset'lere karsi yeniden dene
        last = None
        for _ in range(3):
            try:
                req = urllib.request.Request(url, data=data, method="POST",
                                             headers={"Content-Type": "application/json"}) if data else url
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (ConnectionError, OSError) as exc:
                last = exc
                time.sleep(0.2)
        raise last

    args = types.SimpleNamespace(backend="chatterbox", lang="tr", device="cpu", t3_model="v3",
                                 exaggeration=0.5, cfg=0.5, seed=None, chatterbox_tr_raw=False,
                                 voice_prompt=None, host="127.0.0.1", port=0)
    srv = tts.create_server(args)
    srv.ensure_model()
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        health = post(f"http://127.0.0.1:{port}/health", None)
        assert health["ok"] is True
        assert health["loaded"] is True

        body = json.dumps({"texts": ["bir", "iki"], "out_dir": str(tmp_path), "prefix": "s_"}).encode()
        out = post(f"http://127.0.0.1:{port}/tts", body)

        # Sembol-only oge: oge bazli hata (HTTP 200, ok=True cunku digeri uretildi);
        # boylece bozuk girdi CUDA baglamini zehirlemeden partiyi dusurmez.
        body2 = json.dumps({"texts": ["tamam", "???"], "out_dir": str(tmp_path),
                            "prefix": "x_"}).encode()
        out2 = post(f"http://127.0.0.1:{port}/tts", body2)
    finally:
        srv.shutdown()
        srv.server_close()

    assert out["ok"] is True
    assert out["count"] == 2 and out["failed"] == 0
    assert os.path.exists(tmp_path / "s_1.wav")
    assert os.path.exists(tmp_path / "s_2.wav")

    assert out2["ok"] is True and out2["failed"] == 1
    bad = [r for r in out2["results"] if not r["ok"]]
    assert len(bad) == 1 and bad[0]["index"] == 2
    assert "harf icermiyor" in bad[0]["error"]
    assert not os.path.exists(tmp_path / "x_2.wav")   # uretilmedi


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


def _post_json(url, data):
    import time
    import urllib.request
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, data=data, method="POST",
                                         headers={"Content-Type": "application/json"}) if data else url
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (ConnectionError, OSError) as exc:
            last = exc
            time.sleep(0.2)
    raise last


def test_tts_server_piper_dispatch(monkeypatch, tmp_path):
    """piper sunucu modu: model bellege alinmaz; her istek synth_piper'a gider (GPU gerekmez)."""
    import threading
    import types

    exe = tmp_path / "piper.exe"
    exe.write_bytes(b"x")
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"y")

    calls = []

    def fake_piper(text, out_wav, model_path=None, piper_exe=None):
        calls.append((text, model_path, piper_exe))
        os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
        with open(out_wav, "wb") as f:
            f.write(b"RIFF")
        return {"out": out_wav, "audio_seconds": 1.0, "tts_seconds": 0.1, "rtf": 0.1}

    monkeypatch.setattr(tts, "synth_piper", fake_piper)

    args = types.SimpleNamespace(backend="piper", lang="tr", device="cpu", t3_model="v3",
                                 exaggeration=0.5, cfg=0.5, seed=None, chatterbox_tr_raw=False,
                                 voice_prompt=None, host="127.0.0.1", port=0,
                                 piper=str(exe), piper_model=str(model))
    srv = tts.create_server(args)
    srv.ensure_model()          # piper icin yukleme yok, yalniz dogrulama
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        health = _post_json(f"http://127.0.0.1:{port}/health", None)
        body = json.dumps({"texts": ["merhaba", "dunya"], "out_dir": str(tmp_path),
                           "prefix": "p_"}).encode()
        out = _post_json(f"http://127.0.0.1:{port}/tts", body)
    finally:
        srv.shutdown()
        srv.server_close()

    assert health["ok"] is True and health["backend"] == "piper"
    assert health["loaded"] is True and health["load_seconds"] == 0.0
    assert out["ok"] is True and out["count"] == 2 and out["failed"] == 0
    assert [c[0] for c in calls] == ["merhaba", "dunya"]
    assert calls[0][1] == str(model) and calls[0][2] == str(exe)
    assert os.path.exists(tmp_path / "p_1.wav")


def test_tts_server_piper_missing_model_raises(tmp_path):
    """piper sunucu modu: eksik ikili/ses dosyasi durust hata verir (sessiz dusmez)."""
    import types

    args = types.SimpleNamespace(backend="piper", lang="tr", device="cpu", t3_model="v3",
                                 exaggeration=0.5, cfg=0.5, seed=None, chatterbox_tr_raw=False,
                                 voice_prompt=None, host="127.0.0.1", port=0,
                                 piper=str(tmp_path / "yok.exe"),
                                 piper_model=str(tmp_path / "yok.onnx"))
    srv = tts.create_server(args)
    with pytest.raises(RuntimeError):
        srv.ensure_model()


def test_tts_server_passes_respell_switches_per_request(monkeypatch, tmp_path):
    """Istek basina A/B kablolamasi: 'softg'/'tr_raw' synth_chatterbox'a dogru gecer.

    {'softg': false} -> yalniz 'ğ' respell kapali (respell=True, softg=False)
    {'tr_raw': true} -> tum TR duzeltmeleri kapali (respell=False)
    """
    import threading
    import types

    monkeypatch.setattr(tts, "load_chatterbox", lambda **kw: object())
    seen = []

    def fake_synth(text, out_wav, *a, **k):
        seen.append({"text": text, "tr_fix": a[7], "respell": a[8], "softg": k.get("softg")})
        os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
        with open(out_wav, "wb") as f:
            f.write(b"RIFF")
        return {"out": out_wav, "audio_seconds": 1.0, "tts_seconds": 0.1, "text": text}

    monkeypatch.setattr(tts, "synth_chatterbox", fake_synth)

    args = types.SimpleNamespace(backend="chatterbox", lang="tr", device="cpu", t3_model="v3",
                                 exaggeration=0.5, cfg=0.5, seed=None, chatterbox_tr_raw=False,
                                 chatterbox_no_softg=False, no_guard=True,
                                 voice_prompt=None, host="127.0.0.1", port=0)
    srv = tts.create_server(args)
    srv.ensure_model()
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for extra in ({"softg": False}, {"tr_raw": True}, {}):
            body = dict({"texts": ["değil"], "out_dir": str(tmp_path), "prefix": "r_"}, **extra)
            _post_json(f"http://127.0.0.1:{port}/tts", json.dumps(body).encode())
    finally:
        srv.shutdown()
        srv.server_close()

    assert seen[0]["softg"] is False and seen[0]["respell"] is True    # yalniz 'ğ' kapali
    assert seen[1]["respell"] is False and seen[1]["tr_fix"] is False  # tr_raw: hepsi kapali
    assert seen[2]["softg"] is True and seen[2]["respell"] is True     # varsayilan: hepsi acik
