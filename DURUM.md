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
- **TTS aracı:** `agent/tts-tools.py` (chatterbox / **voxcpm** / piper / sapi) + **toplu mod**
  (`--batch-file` + `--out-prefix`)
- **TTS-TR değerlendirmesi:** **Trendyol-TTS** ölçüldü (VRAM ~5,6 GB, RTF ~3) → **çevrimdışı motor**
  (karar #16, `docs/tts-tr-sonuc.md`)
- **Chatterbox TR düzeltmeleri (kod):** `install_tr_tokenizer_fix()` + `ş→sh` respell, `--lang tr`
  ile **otomatik**. Kulak testi (2026-10-17): Chatterbox ve Trendyol — ikisi de iyi (karar #18)
- **Pipeline uçtan uca ÇALIŞTI** (gerçek bileşenler): `whisper` → `llama-server` (MTP) → cümle bölme
  → Chatterbox TTS. LLM: ~103 tok/sn, TTFT ~0,30 sn; MTP draft acceptance ~0,63–0,75.
- **Pipeline TOPLU TTS'e bağlandı (2026-10-17):** `pipeline.ps1` cümleleri tek çağrıda üretir
  (`--batch-file` + `--out-prefix`), model **bir kez** yüklenir.
  **Ölçüm (4 cümle): tek-tek 106,6 sn → toplu 48,4 sn (2,2×).** Yükleme ~19,8 sn **bir kez**;
  ayrıntı `logs\pipeline\tts_batch.json`.
- **Kritik bug düzeltmeleri (2026-10-17):**
  - `synth_chatterbox` içinde `uses_mtl` **tanımsızdı** → chatterbox yolu **her zaman `NameError`**
    veriyordu (tekli + toplu). Düzeltildi.
  - LLM cevabındaki **emoji**, `print`'te `UnicodeEncodeError` (cp1254) ile **tüm toplu üretimi**
    düşürüyordu. stdout artık UTF-8'e çevriliyor; ayrıca pipeline emoji-only cümleleri eliyor.
  - `--out` toplu modda zorunlu değil; tek cümle patlarsa toplu üretim **devam ediyor**
    (`failed` sayısı raporlanır).
- **ASR ölçüm + optimizasyon (2026-10-17):** `large-v3-turbo` CPU'da **RTF 4,2 → 1,9**
  (q5_0 quant + `-t 12`). Model f16'ydı → `ggml-large-v3-turbo-q5_0.bin` (547 MB) üretildi
  (transkript **aynı**). `asr-tools.py` artık `load_seconds` / `infer_seconds` ayırıyor;
  thread varsayılanı **mantıksal çekirdek**. **`-ac` REDDEDİLDİ** (tekrar döngüsü/halüsinasyon).
  Ayrıntı: [`docs/faz2-sonuc.md`](docs/faz2-sonuc.md).
- **ASR model karşılaştırması (q5_0, 12 thread, 5,6 sn TR ses):**
  base **0,84 sn** (RTF 0,15 · Türkçe zayıf) · small **2,5 sn** (0,45 · zayıf) ·
  medium **7,5 sn** (1,35 · iyi) · turbo **11,0 sn** (1,98 · en iyi).
- **Kalıcı ASR süreci:** `scripts/whisper-server.ps1` + `asr-tools.py --server-url`
  → model bellekte kalır, yükleme tekrarı biter (turbo sunucuda ~9,9 sn).
- Testler: `python -m pytest -q` → **30 test** geçiyor

## Önemli kararlar (özet)
- **LLM:** Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M **+ MTP zorunlu** (kararlar #12, #13)
- **STT:** whisper.cpp `large-v3-turbo` (karar #11); CPU'da **q5_0 quant + mantıksal thread**;
  canlı hat için **kalıcı `whisper-server`**
- **TTS:** İngilizce **Chatterbox** (MIT). TR: **Chatterbox (tr-fix + respell)** canlı aday (~3,3 GB),
  **Trendyol-TTS** çevrimdışı (~5,6 GB, RTF ~3,4). (kararlar #16/#18)

## Açık işler / sıradaki adımlar
0. ✅ **Pipeline + toplu TTS bağlandı ve ölçüldü (2026-10-17).** Ancak:
   - ⚠️ **`<1 sn` hedefi bu donanımda tutmuyor.** ASR turbo ~10 sn (whisper encoder her istekte
     **30 sn penceresini** encode ediyor → kısa seste sabit maliyet); Chatterbox GPU'da **RTF ~1,29**
     (gerçek zamandan yavaş).
   - **Sıradaki karar (biri/birkaçı):**
     - **TTS'i de kalıcı süreç yap** (whisper-server gibi) → yükleme tekrarı biter, cümle başı ~4–7 sn.
     - **ASR'de `small`/`medium`** (hız↔doğruluk takası) veya whisper'ı GPU'ya al (mimari kuralı değişir).
     - `piper` (CPU, hızlı ama robotik) canlı yedek olarak TTS'te denenebilir.
1. **Türkçe TTS:** Trendyol-TTS ağır (VRAM ~5,6 GB, RTF ~3) → çevrimdışı. Canlı TR adayları
   **CosyVoice2 / XTTS-v2** (hız + VRAM ölçülmeli). Beğenilmezse Piper.
2. **Fish S2 Pro:** yalnız izole WSL denemesi (Türkçe zayıf, silindi; WSL kaldı).
3. **Faz 3:** LLM + MTP + prefix cache (MTP çalışıyor; prefix cache ölçülmedi).
4. **LLM bağlamı/prefix cache** ve sohbet döngüsü (arayüz) henüz yok.

## Ortam notları
- **PowerShell 7 (2026-10-17):** `winget install Microsoft.PowerShell` → **7.6.7**;
  `pwsh` = `%LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe` (PATH'te). Öncesinde yalnız 5.1 vardı.
  `pipeline.ps1`/betikler ASCII tutulduğu için 5.1'de de çalışır.
- **Araçlar:** `tools\whisper\Release\whisper-cli.exe` (+ `whisper-server.exe`, `whisper-quantize.exe`,
  `whisper-bench.exe`), `tools\llama\llama-server.exe` (b11669, CUDA 13.4).
- **Modeller** (`models\`): `ggml-large-v3-turbo.bin` (f16, 1,55 GB),
  **`ggml-large-v3-turbo-q5_0.bin` (547 MB)**, `ggml-{base,small,medium}.bin` + `-q5_0` quant'ları,
  `Huihui-...i1-Q5_K_M.gguf` (6,5 GB, **MTP enjekte edildi**).
- **llama-server (MTP) çalıştırma** (düşünme açık, bütçe 256; port 8080). ⚠️
  `--reasoning-budget-message` boşluk içerdiği için **tırnaklanmalı ve `=` biçimi kullanılmamalı**:
  ```
  tools\llama\llama-server.exe -m models\<gguf> --spec-type draft-mtp -c 4096 -ngl 99 ^
    --reasoning on --reasoning-budget 256 ^
    --reasoning-budget-message "Dusunmeyi bitir ve kisa Turkce cevabi yaz." ^
    --host 127.0.0.1 --port 8080
  ```
- **whisper-server:** `pwsh -File scripts\whisper-server.ps1 -Model models\ggml-large-v3-turbo-q5_0.bin`
  (port **8081**). ⚠️ **`-ng` zorunlu** — GPU'yu denerse `0xC0000409` ile çöküyor (STT CPU'da).
  Kullanım: `asr-tools.py --wav ... --server-url http://127.0.0.1:8081`; durdurmak için `-Stop`.
- ⚠️ **Non-ASCII repo yolu:** yol "Varsayılan" (ı) içeriyor. `Start-Process`'e **mutlak** yol
  argümanı verilirse karakter bozuluyor (whisper-server yanlış yolu açıp çöküyor) → **göreli yol +
  `-WorkingDirectory`** kullan (bkz. `scripts/whisper-server.ps1`).
- **Whisper ikilisi** PATH'te değil → `asr-tools.py --whisper tools\whisper\Release\whisper-cli.exe`.
- **TTS venv:** `%USERPROFILE%\tts-venv` — `torch 2.11.0+cu128` (sm_120), `chatterbox-tts 0.1.7`,
  `voxcpm 2.0.3`, `soundfile`. HF modelleri sağlam.
- **Örnek sesler:** `logs\tts\tr-ornek.wav`, `logs\tts\en-ornek.wav`, `logs\tts\trendyol-tr*.wav`;
  ASR ölçümü için `logs\asr-tmp\chatterbox-tr-final.16k.wav` (5,6 sn TR).
- Proje **native Windows** hedefler; Fish/WSL yalnızca deneme amaçlı
- **Çalışma kuralı:** ağır GPU işi (model yükleme / GPU'da çıkarım) çalıştırmadan **önce kullanıcıya sor**
- **İki donanım profili:** A (8 GB VRAM/16 GB RAM) ve B (16 GB VRAM/32 GB RAM) → [`docs/mimari.md`](docs/mimari.md) §7.1.
  Bu makine **profil B** (Ryzen 5 3600 6C/12T, RTX 5060 Ti 16 GB).
