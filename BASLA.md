# BASLA — yeni sohbet başlangıç notu

**Proje:** aybars_says — Windows'ta tamamen yerel, **sesli** (STT + TTS) yapay zekâ sohbet uygulaması.
**Çalışma dizini:** bu klasör.

---

## Yeni sohbete yapıştıracağın ilk mesaj

```
Proje: aybars_says — sesli (STT+TTS) yerel yapay zekâ sohbet uygulaması.

Önce şu dosyaları oku: DURUM.md, README.md, AGENTS.md, docs/kararlar.md, docs/mimari.md.

Özet durum:
- LLM: Huihui-Qwen3.5-9B i1-Q5_K_M + MTP zorunlu
- STT: whisper.cpp large-v3-turbo
- TTS: İngilizce için Chatterbox iyi ama TÜRKÇESİ KÖTÜ; Fish S2-Pro da yetersizdi (silindi).
- Trendyol-TTS (openbmb/VoxCPM2 + Türkçe LoRA, MIT, ~2B) DEĞERLENDİRİLDİ: TR anlaşılır
  (geri-çevirim WER ~0,08) ama ağır (~5,6 GB VRAM, RTF ~3) → çevrimdışı motor olarak eklendi.
  Örnek: logs\tts\trendyol-tr.wav

Sıradaki iş: Trendyol-TTS sonucunu değerlendir. **Değerlendirildi (2026-10-16):** Türkçe anlaşılır
(geri-çevirim WER ~0,08) ama ağır (~5,6 GB VRAM, RTF ~3) → canlı hat için uygun değil; `voxcpm`
backend'i çevrimdışı motor olarak `agent/tts-tools.py`'ye eklendi ve karar `docs/kararlar.md` (#16)
işlendi. Ayrıntı: `docs/tts-tr-sonuc.md`.

**Canlı TR TTS** hâlâ açık — sıradaki adaylar: **CosyVoice2, XTTS-v2** (hız + VRAM ölçülmeli);
beğenilmezse geri dönüş **Piper** (CPU, hızlı ama robotik).

Hazır test betiği: scripts/tts-trendyol-test.py  →  python scripts/tts-trendyol-test.py
(kurulum: pip install voxcpm soundfile)

Ayrıca hazır araçlar: agent/mtp_inject.py, agent/asr-tools.py, agent/tts-tools.py,
scripts/mtp-dogrula.ps1, scripts/asr-olcum.ps1 — testler: python -m pytest -q
```
