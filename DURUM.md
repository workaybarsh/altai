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
  (**19 test**). **Kulak testi (2026-10-17): Chatterbox (tr-fix+respell) ve Trendyol — ikisi de iyi.**
  Chatterbox hafif/hızlı → canlı aday; Trendyol native TR ama ağır → çevrimdışı (karar #18,
  `docs/tts-kiyaslama.md` §9)
- Testler: `python -m pytest -q` → **19 test** geçiyor

## Önemli kararlar (özet)
- **LLM:** Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M **+ MTP zorunlu** (kararlar #12, #13)
- **STT:** whisper.cpp `large-v3-turbo` (karar #11)
- **TTS:** İngilizce **Chatterbox** (MIT). TR: **Chatterbox (tr-fix + respell)** ve **Trendyol-TTS**
  kulak testinde **ikisi de iyi** → Chatterbox **canlı aday** (hafif/hızlı, ~2 GB), Trendyol
  **çevrimdışı** (~5,6 GB, RTF ~3,4). (kararlar #16/#18)

## Açık işler / sıradaki adımlar
0. ✅ **Pipeline uçtan uca ÇALIŞTI (2026-10-17)** — gerçek bileşenlerle:
   `whisper-cli` → `llama-server` (MTP) → cümle bölme → Chatterbox TTS.
   Çıktı: `logs\pipeline\tts_1.wav`, `tts_2.wav`.
   - **LLM/MTP doğrulandı:** draft acceptance ~0,63–0,75, **~103 tok/sn**, TTFT ~0,30 sn
     (preset: `--spec-type draft-mtp -c 4096 -ngl 99`)
   - **Düşünme AÇIK** (kullanıcı tercihi): `--reasoning on --reasoning-budget 256
     --reasoning-budget-message "Dusunmeyi bitir ve kisa Turkce cevabi yaz."` → ~0,26 sn.
     ⚠️ `max_tokens` düşünmeyi de kapsar; bütçesiz bırakılırsa cevap hiç gelmez (`finish_reason=length`).
   - ⚠️ **ASR yavaş:** 5,5 sn ses → 23,6 sn (**RTF ~4,2**, CPU, thread ayarsız).
   - ⚠️ **TTS her cümlede modeli yeniden yüklüyor** (~13 sn + torch import ~8 sn) → toplam 57 sn.
     `tts-tools.py`'ye **toplu mod** eklendi (`--batch-file` + `--out-prefix`, model tek yükleme);
     **pipeline.ps1 henüz bu moda bağlanmadı**.
   - **Sıradaki iş:** pipeline'ı `--batch-file`'a geçir (57 sn → ~15 sn), sonra ASR thread ayarı.
1. **Türkçe TTS:** Trendyol-TTS değerlendirildi → **anlaşılır** ama canlı hat için **ağır**
   (VRAM ~5,6 GB, RTF ~3). `agent/tts-tools.py`'ye `voxcpm` backend eklendi (çevrimdışı/yüksek
   kalite). Ayrıntı: `docs/tts-tr-sonuc.md`.
   - **Canlı TR için sıradaki adaylar: CosyVoice2, XTTS-v2** (hız + VRAM ölçülmeli)
   - Beğenilmezse geri dönüş: Piper (CPU, hızlı ama robotik)
2. **Fish S2 Pro** → ~~izole WSL denemesi~~ (denendi, Türkçe zayıf, **silindi**; WSL kaldı)
3. **Faz 2 gerçek ölçüm:** `large-v3-turbo` ile gecikme/RTF (hedef donanım, N=10)
4. **Faz 3:** LLM + MTP + prefix cache

## Ortam notları
- **Araçlar (2026-10-17 kuruldu):** `tools\whisper\Release\whisper-cli.exe` (b5454),
  `tools\llama\llama-server.exe` (b11669, CUDA 13.4 + cudart). **Modeller:** `models\`
  (`ggml-large-v3-turbo.bin` 1,55 GB; `Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf` 6,5 GB
  — **MTP enjekte edildi**, `nextn_predict_layers=1`, block 33). `tools/` ve `models/` gitignore'da.
- **llama-server çalıştırma:** `tools\llama\llama-server.exe -m models\<gguf> --spec-type draft-mtp
  -c 4096 -ngl 99 --reasoning on --reasoning-budget 256 ...` (port 8080)
- **Whisper ikilisi** `tools\whisper\Release\` altında (PATH'te değil) → `asr-tools.py --whisper ...` ver
- **WSL:** Ubuntu 24.04, `E:\wsl\ubuntu-24.04`, RTX 5060 Ti GPU geçişi çalışıyor (Python 3.12)
- **TTS venv:** ⚠️ 2026-10-17: `%TEMP%\opencode\tts-venv` silindi (restart) → **yeniden kuruldu:
  `%USERPROFILE%\tts-venv`** — `torch 2.11.0+cu128` (sm_120, CUDA True), `chatterbox-tts 0.1.7`,
  `voxcpm 2.0.3`, `soundfile`; doğrulandı. HF modelleri **sağlam**: Chatterbox ~3 GB,
  Trendyol-TTS ~4,9 GB, whisper-large-v3-turbo ~1,5 GB
- **Örnek sesler:** `logs\tts\tr-ornek.wav`, `logs\tts\en-ornek.wav`,
  `logs\tts\trendyol-tr.wav`, `logs\tts\trendyol-tr2.wav`
- Proje **native Windows** hedefler; Fish/WSL yalnızca deneme amaçlı
- **Çalışma kuralı:** ağır GPU işi (model yükleme / GPU'da çıkarım) çalıştırmadan **önce kullanıcıya sor**
- **İki donanım profili:** A (8 GB VRAM/16 GB RAM) ve B (16 GB VRAM/32 GB RAM) → model/CPU-GPU
  dağılımı ve VRAM/RAM tahminleri: [`docs/mimari.md`](docs/mimari.md) §7.1
