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
- STT: whisper.cpp large-v3-turbo — ⚠️ yavaş (RTF ~4,2, CPU, thread ayarsız)
- TTS: Chatterbox (TR: tr-fix + respell OTOMATİK, --lang tr) — canlı aday; Trendyol = çevrimdışı
- **Pipeline uçtan uca ÇALIŞIYOR** (agent/pipeline.ps1): ASR → LLM → cümle → TTS
- Düşünme (reasoning) AÇIK: --reasoning on --reasoning-budget 256 (max_tokens düşünmeyi de kapsar)

⏳ SIRADAKİ İŞ: pipeline'ı tts-tools.py'nin YENİ toplu moduna bağla
   (--batch-file + --out-prefix → model tek yükleme; 57 sn → ~15 sn). Sonra ASR thread ayarı.
   Kurulumlar: tools\whisper (whisper-cli), tools\llama (llama-server), models\ (turbo + MTP'li 9B GGUF)

Hazır araçlar: agent/mtp_inject.py, agent/asr-tools.py, agent/tts-tools.py
(chatterbox / voxcpm / piper / sapi + --batch-file), agent/pipeline.ps1
— testler: python -m pytest -q (20 test)
```
