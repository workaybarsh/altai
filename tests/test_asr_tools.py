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
