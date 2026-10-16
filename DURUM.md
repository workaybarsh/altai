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
- **TTS aracı:** `agent/tts-tools.py` (chatterbox / **voxcpm** / piper / sapi)
- **TTS-TR değerlendirmesi:** **Trendyol-TTS** ölçüldü (VRAM ~5,6 GB, RTF ~3, geri-çevirim
  Whisper WER ~0,08) → canlı hat için ağır; **çevrimdışı motor** olarak eklendi (karar #16,
  `docs/tts-tr-sonuc.md`)
- **Bağımsız TR TTS kıyası** (arXiv:2610.06057) işlendi: Chatterbox TR'de hiçbir metriği kazanmıyor,
  kısa cümlede çöküyor; VoxCPM2 klon/kararlılık, CosyVoice doğallık lideri (karar #17,
  `docs/tts-kiyaslama.md`)
- **Chatterbox TR düzeltmesi (kod):** kök neden tokenizer'ın her zaman `NFKD` uygulaması +
  Türkçe-duyarsız `lower()`; `install_tr_tokenizer_fix()` yazıldı, `--chatterbox-tr-fix` eklendi
  (**19 test**). Ses etkisi GPU boşken ölçülecek (karar #18, `docs/tts-kiyaslama.md` §9)
- Testler: `python -m pytest -q` → **17 test** geçiyor

## Önemli kararlar (özet)
- **LLM:** Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M **+ MTP zorunlu** (kararlar #12, #13)
- **STT:** whisper.cpp `large-v3-turbo` (karar #11)
- **TTS:** İngilizce için **Chatterbox** (MIT); Türkçesi zayıf. TR için **Trendyol-TTS** test
  edildi: **anlaşılır** ama **ağır** (~5,6 GB VRAM, RTF ~3) → **çevrimdışı motor** olarak eklendi
  (`voxcpm` backend, kararlar #14/#16). Canlı TR hattı hâlâ açık (kararlar #16 açık maddesi)

## Açık işler / sıradaki adımlar
1. **Türkçe TTS:** Trendyol-TTS değerlendirildi → **anlaşılır** ama canlı hat için **ağır**
   (VRAM ~5,6 GB, RTF ~3). `agent/tts-tools.py`'ye `voxcpm` backend eklendi (çevrimdışı/yüksek
   kalite). Ayrıntı: `docs/tts-tr-sonuc.md`.
   - **Canlı TR için sıradaki adaylar: CosyVoice2, XTTS-v2** (hız + VRAM ölçülmeli)
   - Beğenilmezse geri dönüş: Piper (CPU, hızlı ama robotik)
2. **Fish S2 Pro** → ~~izole WSL denemesi~~ (denendi, Türkçe zayıf, **silindi**; WSL kaldı)
3. **Faz 2 gerçek ölçüm:** `large-v3-turbo` ile gecikme/RTF (hedef donanım, N=10)
4. **Faz 3:** LLM + MTP + prefix cache

## Ortam notları
- **WSL:** Ubuntu 24.04, `E:\wsl\ubuntu-24.04`, RTX 5060 Ti GPU geçişi çalışıyor (Python 3.12)
- **Chatterbox venv:** `%TEMP%\opencode\tts-venv` (5,1 GB) — `torch 2.11.0+cu128`, sm_120,
  `voxcpm 2.0.3`; Trendyol-TTS HF önbellekte (~4,8 GB)
- **Örnek sesler:** `logs\tts\tr-ornek.wav`, `logs\tts\en-ornek.wav`,
  `logs\tts\trendyol-tr.wav`, `logs\tts\trendyol-tr2.wav`
- Proje **native Windows** hedefler; Fish/WSL yalnızca deneme amaçlı
- **İki donanım profili:** A (8 GB VRAM/16 GB RAM) ve B (16 GB VRAM/32 GB RAM) → model/CPU-GPU
  dağılımı ve VRAM/RAM tahminleri: [`docs/mimari.md`](docs/mimari.md) §7.1
