# BASLA — yeni sohbet başlangıç notu

**Proje:** aybars_says — Windows'ta tamamen yerel, **sesli** (STT + TTS) yapay zekâ sohbet uygulaması.
**Çalışma dizini:** bu klasör.

---

## Yeni sohbete yapıştıracağın ilk mesaj

```
Proje: aybars_says — sesli (STT+TTS) yerel yapay zekâ sohbet uygulaması.

Önce şu dosyaları oku: DURUM.md, README.md, AGENTS.md, docs/kararlar.md, docs/mimari.md.

Özet durum:
- LLM: Huihui-Qwen3.5-9B i1-Q5_K_M + MTP (GPU'da, llama-server) — ÖLÇÜLDÜ: ~103 tok/sn, TTFT ~0,3 sn
- STT: whisper.cpp large-v3-turbo — CPU'da q5_0 + mantıksal thread: RTF 4,2 → ~1,9; canlı için whisper-server
- TTS: Chatterbox (TR: tr-fix + respell OTOMATİK, --lang tr); Trendyol = çevrimdışı; RTF ~1,29 (GPU)
- **Pipeline uçtan uca ÇALIŞIYOR** (agent/pipeline.ps1): ASR → LLM → cümle → **toplu** TTS (model tek yükleme)
- Düşünme (reasoning) AÇIK: --reasoning on --reasoning-budget 256 (max_tokens düşünmeyi de kapsar)

⚠️ <1 sn hedefi bu donanımda tutmuyor: ASR turbo ~10 sn (encoder 30 sn penceresi), TTS RTF ~1,29.
✅ Yükleme tekrarı ÇÖZÜLDÜ: kalıcı sunucular (whisper-server 8081 + tts-server 8082 + llama-server 8080)
   → tam pipeline tur başına ~23–27 sn, hiç model yüklemesi yok.
⏳ SIRADAKİ İŞ: (a) ASR model/CPU-GPU kararı (small/medium? GPU?), (b) gerçek konuşmayla Türkçe WER,
   (c) akışlı hat (ilk cümlede LLM+TTS başlatma). Ayrıntı: DURUM.md, docs/faz2-sonuc.md, docs/kararlar.md #19/#20
   Kurulumlar: tools\whisper, tools\llama, models\ (turbo-q5_0 + MTP'li 9B)

Hazır araçlar: agent/mtp_inject.py; agent/asr-tools.py (--server-url); agent/tts-tools.py
(chatterbox / voxcpm / piper / sapi + --batch-file + --serve + uzun-kuyruk guard); agent/pipeline.ps1
(-AsrServerUrl / -TtsServerUrl); scripts/whisper-server.ps1; scripts/tts-server.ps1
— testler: python -m pytest -q (39 test)
```
