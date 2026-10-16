# BASLA — yeni sohbet başlangıç notu

**Proje:** aybars_says — Windows'ta tamamen yerel, **sesli** (STT + TTS) yapay zekâ sohbet uygulaması.
**Çalışma dizini:** bu klasör.

---

## Yeni sohbete yapıştıracağın ilk mesaj

```
Proje: aybars_says — sesli (STT+TTS) yerel yapay zekâ sohbet uygulaması.

Önce şu dosyaları oku: DURUM.md, README.md, AGENTS.md, docs/kararlar.md, docs/mimari.md.

Özet durum:
- LLM: Huihui-Qwen3.5-9B i1-Q5_K_M + MTP zorunlu (GPU)
- STT: whisper.cpp large-v3-turbo (CPU)
- TTS: Chatterbox (EN çok iyi; TR diakritik sorunu TESPİT EDİLDİ ve KOD ile düzeltildi → --chatterbox-tr-fix)
- Trendyol-TTS (VoxCPM2 + TR LoRA): TR anlaşılır (WER ~0,08) ama ağır (~5,6 GB VRAM, RTF ~3)
  → çevrimdışı motor (backend: voxcpm). Fish S2-Pro: silindi (izole WSL denemesiydi).
- Bağımsız TR TTS kıyası (arXiv:2610.06057) işlendi (karar #17)
- Donanım profilleri: A (8 GB/16 GB) · B (16 GB/32 GB); LLM bağlamı 4k — docs/mimari.md §7.1

⏳ SIRADAKİ İŞ (GPU boşalınca, öncelik): **SES ÇIKIŞI testi** — Chatterbox TR düzeltmesinin A/B
   ölçümü (doğru TR × yama açık/kapalı, ASCII) → Whisper geri-çevirim + WER + kulak.
   Plan: docs/tts-kiyaslama.md §9.1. Ön koşul: Chatterbox ağırlıkları ~2 GB (ilk çalıştırmada iner).

Canlı TR TTS hâlâ açık — adaylar: CosyVoice3 (finetune gerekir), XTTS-v2 (TR'de iyi iddiası),
Piper (CPU, hızlı ama robotik).

Hazır araçlar: agent/mtp_inject.py, agent/asr-tools.py, agent/tts-tools.py
(chatterbox / voxcpm / piper / sapi), scripts/mtp-dogrula.ps1, scripts/asr-olcum.ps1
— testler: python -m pytest -q (19 test)
```
