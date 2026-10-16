# Durum ve Devam Notu

> Yeni bir sohbet/oturum başlarken hızlı bağlam için. Ayrıntı: [`README.md`](README.md),
> [`AGENTS.md`](AGENTS.md), [`docs/`](docs/).

## Proje
Windows'ta **tamamen yerel**, sesli (STT + TTS) yapay zekâ sohbet uygulaması.
Repo: `github.com/workaybarsh/aybars_says`

## Tamamlananlar
- Mimari + kararlar: `docs/mimari.md`, `docs/kararlar.md`
- **MTP araçları:** `agent/mtp_inject.py`, `agent/mtp-durum.py`, `scripts/mtp-dogrula.ps1` + testler
- **ASR aracı:** `agent/asr-tools.py`, `scripts/asr-olcum.ps1` — whisper.cpp ile gerçek uçtan uca
  duman testi (base.en, CPU, RTF ~0,19)
- **TTS aracı:** `agent/tts-tools.py` (chatterbox / piper / sapi)
- Testler: `python -m pytest -q` → **16 test** geçiyor

## Önemli kararlar (özet)
- **LLM:** Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M **+ MTP zorunlu** (kararlar #12, #13)
- **STT:** whisper.cpp `large-v3-turbo` (karar #11)
- **TTS:** İngilizce için **Chatterbox** çok iyi (MIT). ⚠️ **Türkçesi kötü çıktı** → Türkçe için
  **alternatif aranıyor** (karar #14 revize edilecek)

## Açık işler / sıradaki adımlar
1. **Türkçe TTS alternatifi:** aday **XTTS-v2** (Türkçe + klonlama, Windows/pip). Kur, Türkçe örnek üret,
   Chatterbox TR ile karşılaştır. Sıradaki adaylar: **Chatterbox v3** (GitHub main), **Piper** (MIT, hızlı yedek)
2. **Fish S2 Pro** → yalnızca **izole WSL denemesi** (merak); projeye entegre **değil** (karar #15)
3. **Faz 2 gerçek ölçüm:** `large-v3-turbo` ile gecikme/RTF (hedef donanım, N=10)
4. **Faz 3:** LLM + MTP + prefix cache

## Ortam notları
- **WSL:** Ubuntu 24.04, `E:\wsl\ubuntu-24.04`, RTX 5060 Ti GPU geçişi çalışıyor (Python 3.12)
- **Chatterbox venv:** `%TEMP%\opencode\tts-venv` (5,1 GB) — `torch 2.11.0+cu128`, sm_120
- **Örnek sesler:** `logs\tts\tr-ornek.wav`, `logs\tts\en-ornek.wav`
- Proje **native Windows** hedefler; Fish/WSL yalnızca deneme amaçlı
