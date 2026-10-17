"""asr-tools.py'nin saf (cevrimdisi) yardimcilarini dogrular.

Dosya adinda tire oldugu icin importlib ile yuklenir.
"""
import importlib.util
import json
import os
import struct
import wave

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("asr_tools", os.path.join(ROOT, "agent", "asr-tools.py"))
asr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(asr)


def make_wav(path, seconds=1.0, rate=16000, channels=1):
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % n, *([0] * n)))
    return str(path)


def test_audio_seconds_reads_length(tmp_path):
    p = make_wav(tmp_path / "a.wav", seconds=2.0, rate=16000)
    assert asr.audio_seconds(p) == pytest.approx(2.0, abs=1e-6)


def test_compute_rtf():
    assert asr.compute_rtf(0.5, 2.0) == pytest.approx(0.25)
    assert asr.compute_rtf(1.0, 0) == float("inf")


def test_percentile_edges():
    vals = [0.10, 0.20, 0.30, 0.40, 0.50]
    assert asr.percentile(vals, 0.5) == pytest.approx(0.30)
    assert asr.percentile(vals, 0.95) == pytest.approx(0.48)
    assert asr.percentile([], 0.5) is None
    assert asr.percentile([7], 0.9) == 7


def test_build_whisper_command():
    cmd = asr.build_whisper_command("whisper-cli", "m.bin", "a.wav", "tr", 6, ["--foo"])
    assert cmd[:2] == ["whisper-cli", "-m"]
    assert "-nt" in cmd                      # zaman damgasi yok
    assert cmd[cmd.index("-l") + 1] == "tr"
    assert cmd[cmd.index("-t") + 1] == "6"
    assert cmd[-1] == "--foo"
    # dil verilmezse 'auto'
    cmd2 = asr.build_whisper_command("w", "m", "f", None)
    assert cmd2[cmd2.index("-l") + 1] == "auto"


def test_find_whisper_bogus_returns_none():
    assert asr.find_whisper("kesinlikle-olmayan-bir-arac-adx") is None


def test_prepare_wav_skips_conversion_when_already_16k_mono(tmp_path):
    p = make_wav(tmp_path / "b.wav", seconds=0.5, rate=16000, channels=1)
    out, err = asr.prepare_wav(p, str(tmp_path / "tmp"), ffmpeg="ffmpeg-yok")
    assert err is None
    assert out == p                          # donusum gerekmedi, ayni yol


def test_main_reports_missing_whisper(tmp_path, capsys):
    code = asr.main(["--wav", make_wav(tmp_path / "c.wav"), "--model", str(tmp_path / "m.bin"),
                     "--whisper", "kesinlikle-olmayan-bir-arac-adx"])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["ok"] is False
    assert "whisper" in out["error"].lower()


def test_default_threads_at_least_one():
    n = asr.default_threads()
    assert isinstance(n, int) and n >= 1


def test_parse_whisper_timings_splits_load_and_infer():
    stderr = (
        "whisper_print_timings:     load time =  1221.79 ms\n"
        "whisper_print_timings:   encode time = 15993.31 ms /     1 runs ( 15993.31 ms per run)\n"
        "whisper_print_timings:   decode time =     0.00 ms /     1 runs (     0.00 ms per run)\n"
        "whisper_print_timings:    total time = 17886.53 ms\n"
    )
    t = asr.parse_whisper_timings(stderr)
    assert t["load_seconds"] == pytest.approx(1.2218, abs=1e-3)
    assert t["encode_seconds"] == pytest.approx(15.9933, abs=1e-3)
    assert t["whisper_total_seconds"] == pytest.approx(17.8865, abs=1e-3)
    assert asr.parse_whisper_timings("") == {}


def test_build_whisper_command_threads_optional():
    # thread verilmezse -t eklenmez (whisper varsayilani); verilirse eklenir
    assert "-t" not in asr.build_whisper_command("w", "m", "f", "tr", None)
    assert "-t" in asr.build_whisper_command("w", "m", "f", "tr", 6)


def test_server_mode_posts_multipart_and_needs_no_model(tmp_path, monkeypatch, capsys):
    """whisper-server modu: --server-url verilince --model gerekmez; /inference'e multipart POST edilir.

    Gercek soket yerine urlopen taklit edilir (Windows loopback reset'lerinden bagimsiz, deterministik).
    """
    import urllib.request

    captured = {}

    class FakeResp:
        def __init__(self, body):
            self._b = body

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["ctype"] = req.headers.get("Content-type") or req.headers.get("Content-Type")
        captured["body"] = req.data
        return FakeResp(json.dumps({"text": "merhaba dunya"}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    wav = make_wav(tmp_path / "srv.wav", seconds=1.0)
    code = asr.main(["--wav", wav, "--server-url", "http://127.0.0.1:8081"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["ok"] is True
    assert out["results"][0]["text"] == "merhaba dunya"
    assert out["results"][0]["audio_seconds"] == pytest.approx(1.0, abs=1e-6)
    assert captured["url"].endswith("/inference")
    assert "multipart/form-data" in captured["ctype"]
    assert b"RIFF" in captured["body"]


def test_server_mode_dead_endpoint_reports_error(tmp_path, capsys):
    wav = make_wav(tmp_path / "dead.wav", seconds=0.5)
    code = asr.main(["--wav", wav, "--server-url", "http://127.0.0.1:1"])
    out = json.loads(capsys.readouterr().out)
    assert code == 5
    assert out["ok"] is False
    assert out["errors"]
