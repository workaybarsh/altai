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
- **Kalıcı TTS süreci (2026-10-17):** `tts-tools.py --serve` (HTTP) + `scripts/tts-server.ps1`
  → Chatterbox bellekte kalır. Ölçüm (aynı 4 cümle): cümle-cümle **106,6 sn** → toplu 48,4 sn →
  **kalıcı sunucu 16,6–18,5 sn** (~6×). Tam pipeline, üç sunucu açıkken **tur başına ~23–27 sn**
  (ASR ~10 + LLM ~4 + TTS ~9–12), **hiç model yüklemesi yok**.
  Ayrıntı: [`docs/tts-kiyaslama.md`](docs/tts-kiyaslama.md) §10.
- **Uzun-kuyruk (halüsinasyon) guard'ı (2026-10-17):** `synth_chatterbox(guard=True)` — üretilen ses
  süre sınırını (`max(3×beklenen, beklenen+2 sn)`, beklenen ≈ harf/14) aşarsa cümle **1 kez** daha
  üretilir, **kısa olan** tutulur (`--no-guard` kapatır). Ayrıca boş/emoji-only cümleler modele
  **hiç gitmez** (`ensure_speakable`; eskiden `IndexError`/CUDA assert ile çöküyordu).
  **GPU ölçümü (24 üretim): 7 tetiklenme (%29), en uzun yakalanan kuyruk 6,04 sn, 0 hata**;
  uzun cümlede hiç tetiklenmedi. ⚠️ Guard azaltır, garanti etmez. Ayrıntı ve "iki mekanizma"
  ayrımı: [`docs/tts-kiyaslama.md`](docs/tts-kiyaslama.md) §11, karar #21.
  *(İnceleme sonrası düzeltme: retry kazandığında `out` alanı silinmiş `.retry.wav` yolunu
  gösteriyordu → `pipeline.ps1` o cümleyi `Test-Path`'te kaybediyordu; `out` artık gerçek dosya,
  pipeline'a savunma eklendi.)*
- **Akışlı hat (2026-10-18, ilke #7 kodda):** `agent/llm-stream.py` (`llama-server` **SSE** → kademeli
  cümle bölme → cümle oluşur oluşmaz TTS → ses **arka planda** çalınır) + `agent/pipeline-stream.ps1`.
  **Ölçüm (LLM+TTS, aynı istem): ilk ses toplu 18,8 sn → akışlı 7,05–7,60 sn (~2,5×)** (ilk token
  0,26 sn, ilk cümle ~0,5 sn; düşünme açıkken ilk ses 9,52 sn). Uçtan uca (ASR turbo CPU 9,91 sn +
  akışlı) ilk ses **13,4 sn**. ⚠️ Kısa cümlede guard retry ilk sesi 13–18 sn'ye çıkarabiliyor;
  uç enerjisi analizi kuyruğun **fazladan konuşma** olduğunu gösterdi (sessizlik değil → kırpma çözmez).
  Ayrıntı: [`docs/akishli-hat.md`](docs/akishli-hat.md), karar #22.
- **Dayanıklılık (2026-10-18):** cümle TTS'i geçici `WinError 10054` reset'inde **2 kez** denenir
  (sentez idempotent); LLM akışı ortada koparsa **eldeki cümlelerle devam** (`stream_error`);
  tek cümlenin TTS'i patlarsa tur düşmez (`failed_sentences`). Ölçüm sırasında iki gerçek reset
  şeffaf şekilde telafi edildi.
- **Kritik düzeltme (2026-10-18):** PS 5.1 `Get-Content -Raw` BOM'suz UTF-8 dosyayı **ANSI** okuyordu
  → akışlı hatta üretilen 3 WAV "kayıp" görünüyordu (`Test-Path` yanlış `False`; tuzak #15). Tüm
  JSON okumaları `-Encoding UTF8`'e alındı; ASR yolu `--out` + dosyadan okumaya çevrildi (stdout
  boru hattı kodlamayı bozabiliyor).
- **TTS darboğazı ÇÖZÜLDÜ — Piper (2026-10-18):** `tts-tools.py --serve --backend piper` +
  `scripts/piper-kur.ps1` (ASCII dizine kurar: `%LOCALAPPDATA%\aybars\piper`). Piper
  `tr_TR-dfki-medium`: **RTF 0,19**, geri-çevirim **WER 0,000** (5/5 cümle birebir), **CPU'da** (GPU yok).
  Akışlı hatta **ilk ses (LLM+TTS): 0,77–0,90 sn** (Chatterbox 4,2–7,6 sn; guard retry ile 30 sn).
  Uçtan uca (ASR + piper): **~11,7 sn** (Chatterbox 13,4 sn) → **ASR hâlâ baskın (%85)**.
  Ayrıntı: [`docs/akishli-hat.md`](docs/akishli-hat.md) §5.2, [`docs/tts-kiyaslama.md`](docs/tts-kiyaslama.md) §5.
  ⚠️ Piper (espeak-ng/onnxruntime) **non-ASCII yolu okuyamıyor** → ikili ve ses dosyası ASCII dizinde
  olmalı; aynı sınır `whisper-cli.exe`'de de var (non-ASCII **mutlak** yolda `0xC0000409`).
- **Chatterbox `ğ` düzeltmesi (2026-10-18):** kullanıcının kulak şikâyeti (`çalıştığı` → "çalıştı ki")
  **geri-çevirimle doğrulandı** ("Tam yerel çalıştığı için…" → "Tam yarar çalıştı ki işin…"). Kök neden:
  grapheme sözlükte (`grapheme_mtl_merged_expanded_v1.json`) **`ğ` var**, NFKD ayrığı yok → sorun
  **akustik modelde**, tokenizer'da değil. `tr_softg()` eklendi (`ğ`: iki ünlü arası → `y`, ünlüden
  sonra ünsüz/sonda → önceki ünlü: `dağ`→`daa`), `ş→sh`'den **önce** uygulanır.
  **A/B (Chatterbox, seed 42, aynı metinler, geri-çevirim):** `çalıştığı` **düzeldi** ✅ (eski yama
  "çalış dışı", yamasız "çalıtıcı"); 9 kelimelik listede kelime-doğru **%44 → %67**; 1. cümlede guard
  retry **23,2 sn → 5,0 sn**. Kapatma: `--chatterbox-no-softg` (sunucuda istek başına `{"softg": false}`).
  ⚠️ `ğ`'den bağımsız kalan TR kusurları: `yerel`→"gereğe", `için`→"işin", `Aybars`→"haybars/aybaş"
  (yamayla çözülmez). Ayrıntı: [`docs/tts-kiyaslama.md`](docs/tts-kiyaslama.md) §9.4;
  **kulak testi ✅ (2026-10-18): kullanıcı "yeni olan güzel" dedi → yama kabul edildi (karar #23)**;
  dinleme seti (masaüstü) `aybars-tts-test\`; ölçüm dosyaları `logs/softg-bench/`.
- Testler: `python -m pytest -q` → **59 test** geçiyor

## Önemli kararlar (özet)
- **LLM:** Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M **+ MTP zorunlu** (kararlar #12, #13)
- **STT:** whisper.cpp `large-v3-turbo` (karar #11); CPU'da **q5_0 quant + mantıksal thread**;
  canlı hat için **kalıcı `whisper-server`**
- **TTS:** İngilizce **Chatterbox** (MIT). TR: **Piper** (`tr_TR-dfki-medium`, **CPU**, RTF 0,19,
  WER 0,000, ilk ses ~0,8 sn) — **canlı için en hızlı aday** (varsayılan kararı onay bekliyor);
  **Chatterbox (tr-fix+respell+`ğ` yaması)** doğallık için (~3,3 GB GPU, RTF ~1,2) ama TR telaffuzu
  **kırılgan** (`yerel`/`için`/`Aybars` hâlâ bozuk → §9.4); **Trendyol-TTS** çevrimdışı
  (~5,6 GB, RTF ~3). (kararlar #16/#18; Piper ölçümü `docs/akishli-hat.md` §5.2)

## Açık işler / sıradaki adımlar
0. ✅ **Pipeline + akışlı hat + kalıcı sunucular bağlandı ve ölçüldü (2026-10-17/18).**
   - ✅ **TTS tarafı çözüldü:** akışlı hat (karar #22) + **Piper** (CPU, RTF 0,19, WER 0,000) →
     **ilk ses (LLM+TTS) 0,77–0,90 sn** — hedefin (<1 sn) içinde.
   - ⚠️ **Kalan tek darboğaz ASR** (~10 sn; uçtan uca sürenin ~%85'i). whisper turbo her istekte
     **30 sn penceresini** encode ediyor → kısa seste sabit maliyet; `-ac` reddedildi (tekrar döngüsü).
   - **Sıradaki karar:** ASR'de `small`/`medium` (hız↔doğruluk takası) **veya** whisper'ı GPU'ya al
     **veya** VAD/akışlı ASR ile gizle (turbo CPU'da RTF>1 → zor).
   - ⏸️ **Tüm bileşenleri GPU'ya alma (VRAM dağılımı) → 8 GB VRAM'li PROFiLDE değerlendirilecek**
     (kullanıcı notu 2026-10-18: "onu 8 GB VRAM'li PC'de düşünürüz"). Bu makinede (profil B, 16 GB)
     STT/TTS **CPU'da** kalır (ilke #1). GPU'ya taşınacaksa tespit edilen engeller: bu whisper
     derlemesinde **`ggml-cuda.dll` yok** (CUDA build gerekir; **RTX 5060 Ti = sm_120** → CUDA ≥12.8
     şart, resmi `whisper-cublas-12.4` ön-derlemesi yetmez); Piper **CPU-only** (onnxruntime-gpu
     gerekir); Chatterbox GPU **~3,3 GB** ve **RTF ~1,2** (yavaş → ilk sesi geri bozar).
     Kaba bütçe: LLM 6,6 + whisper 0,6–1,6 + Chatterbox 3,3 ≈ **10,5–11,5 GB** → 16 GB'a sığar,
     **8 GB'a sığmaz** (profil A'da öncelik ASR mi TTS mi sorusu).
   - ⬜ **Karar bekliyor:** Piper canlı hattın **varsayılan TTS'i** olsun mu? (ölçüm hazır, onay bekliyor;
     Piper CPU'da çalıştığı için GPU'yu tümüyle LLM'e bırakır — mimari ilke #1).
   - ✅ **`ğ` yaması KULAK TESTİYLE KABUL EDİLDİ (2026-10-18, karar #23):** kullanıcı "yeni olan güzel"
     dedi → `--lang tr`'de varsayılan açık. ⬜ **Kalan iş:** `yerel`/`için`/`Aybars` tipi hatalar
     (§9.4) → **kelime-istisna sözlüğü** (ASR denetimiyle) **veya** TR TTS değişimi. Kullanıcı Piper'ı
     **doğallık** yönünden reddetti (WER 0,000 ama robotik) → Chatterbox TR kırılganlığı hâlâ açık konu.
   - ⬜ **Açık iş (yalnız Chatterbox kalırsa):** kısa cümlede guard retry'ı sınırlamak (ör. <20 harfte
     retry yok / sınır tabanı) veya kısa ünlemler için hazır ses.
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
- **Modeller** (`models\`): **`ggml-large-v3-turbo-q5_0.bin` (547 MB, varsayılan ASR)** ve
  `Huihui-...i1-Q5_K_M.gguf` (6,7 GB, **MTP enjekte edildi**).
  *(2026-10-17 disk temizliği: turbo **f16**, base/small/medium (+q5_0) ve HF'deki **Trendyol-TTS**
  ile whisper-v3-turbo cache'leri silindi — **~15 GB** kazanıldı. Gerekirse HF/`whisper-quantize` ile
  yeniden üretilir; `voxcpm` çevrimdışı backend'i o zamana kadar çalışmaz.)*
- **Kalıcı sunucular (canlı hat için önerilen):**
  `llama-server` (port 8080) + `scripts\whisper-server.ps1` (8081, **`-ng`**) +
  `scripts\tts-server.ps1` (8082, tts-venv). Pipeline:
  `pipeline.ps1 -AsrServerUrl http://127.0.0.1:8081 -TtsServerUrl http://127.0.0.1:8082`.
  **Akışlı hat:** `pipeline-stream.ps1` (aynı sunucular; `-Play` ile üretilen sesi hemen çalar).
  ⚠️ `tts-server` bozuk girdide CUDA bağlamını kaybederse `/health` `fatal` döner → yeniden başlat.
- **Piper (CPU TTS, 2026-10-18):** `scripts\piper-kur.ps1` → `%LOCALAPPDATA%\aybars\piper`
  (`piper.exe` + `voice.onnx`); sonra `scripts\tts-server.ps1 -Backend piper -Port 8082`.
  ⚠️ **ASCII dizin şart** (espeak-ng non-ASCII yolu okuyamaz; onnxruntime `0xC0000409` çöker).
  Ayrıntı + ölçüm: [`docs/akishli-hat.md`](docs/akishli-hat.md) §5.2.
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
