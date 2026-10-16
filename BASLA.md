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
- TTS: proje için seçilecek. İngilizce için Chatterbox iyi ama TÜRKÇESİ KÖTÜ;
  Fish S2-Pro da Türkçede yetersiz kaldı (izole WSL denemesiydi, silindi).
- Şu an test edilen aday: Trendyol-TTS (openbmb/VoxCPM2 + Türkçe LoRA, MIT, ~2B).
  Örnek çıktı: logs\tts\trendyol-tr.wav  (varsa kalitesini değerlendir)

Sıradaki iş: Trendyol-TTS sonucunu değerlendir. Beğenilirse agent/tts-tools.py'ye
'voxcpm' backend'i ekle ve kararı docs/kararlar.md'ye (#14) işle. Beğenilmezse
alternatifler: CosyVoice2, XTTS-v2.

Hazır test betiği: scripts/tts-trendyol-test.py  →  python scripts/tts-trendyol-test.py
(kurulum: pip install voxcpm soundfile)

Ayrıca hazır araçlar: agent/mtp_inject.py, agent/asr-tools.py, agent/tts-tools.py,
scripts/mtp-dogrula.ps1, scripts/asr-olcum.ps1 — testler: python -m pytest -q
```
