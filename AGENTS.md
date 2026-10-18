# aybars_speaks · sesli yerel yapay zekâ sohbet botu · Geliştirici ve yapay zekâ ajanları için altyapı rehberi

Bu dosya, aybars_speaks üzerinde çalışan geliştiriciler ve yapay
zekâ ajanları için tek doğru kaynaktır. Kullanıcıyla iletişim dili **Türkçe**dir.

> Bu depo **ağırlıklı olarak planlama** aşamasındadır; ilk çalışan araç `agent/mtp_inject.py`.
> Aşağıdaki yapı ve kurallar, üzerine inşa edilecek hedefi tanımlar.

## 1. Ürün tek paragrafta

Windows'ta tamamen yerel çalışan, gerçek zamanlı, yapay zekâ destekli **sesli sohbet botu**. Tek bir
WinForms penceresinde kullanıcı mikrofonla konuşur; uygulama konuşmayı yazıya çevirir (**whisper.cpp**),
yerel dil modeline verir (**Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M**, **MTP daima açık**) ve yanıtı
sesli okur (TTS). Hedef, kullanıcı konuşmayı bitirdikten sonra **1 saniye içinde** ilk sesin çıkmasıdır.

## 2. Mimari ilkeler (değişmez)

1. **GPU'da yalnızca dil modeli çalışır.** STT ve TTS **CPU'da** çalışır.
2. **Dil modeli yerleşiktir.** Turlar arasında boşaltılmaz; model takası yok.
3. **Model:** Huihui-Qwen3.5-9B-abliterated **i1-Q5_K_M** GGUF (imatrix) + MTP (`mtp_inject.py`).
4. **MTP daima açık.** `--spec-type draft-mtp`; kapatılmaz. Kayıpsız çıktı.
5. **STT: whisper.cpp** (Qwen3-ASR kullanılmaz).
6. **Tek sahipli hat.** Yalnızca `llama-server` + CPU işçileri.
7. **Boru hattı.** LLM ilk cümle → TTS; kullanıcı dinlerken LLM yazmaya devam eder.

## 3. Modeller

### 3.1 Dil modeli

| Alan | Değer |
|---|---|
| Model | Huihui-Qwen3.5-9B-abliterated **i1-Q5_K_M** (GGUF, imatrix) |
| Dosya | `Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf` (~6,6 GB) |
| HF deposu | `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF` |
| Taban model | `huihui-ai/Huihui-Qwen3.5-9B-abliterated` (Qwen3.5-9B türevi, abliterated) |
| MTP | `mtp_inject.py` ile `blk.<N>.nextn.*` (kaynak: `huihui-ai/Huihui-Qwen3.5-9B-abliterated`) |
| Çalıştırma | `llama-server` + `--spec-type draft-mtp` (daima) |
| Bağlam | sohbette **4k** (kayan pencere), üst sınır **8k**; **32768 gerekmez** (sesli sohbet botu) |

> **Doğrulandı (2026-10-16):** hedef quant GGUF (`i1-Q5_K_M`) MTP/`nextn` katmanı **içermez**;
> kaynak `huihui-ai/Huihui-Qwen3.5-9B-abliterated` deposunda **15 MTP tensoru mevcut** ve
> `mtp_inject.py` eşlemesiyle birebir uyuşur. Enjeksiyon **zorunludur**. Riskler ve kabul testleri:
> [`docs/mtp-dogrulama.md`](docs/mtp-dogrulama.md).

### 3.2 STT: whisper.cpp

| Alan | Değer |
|---|---|
| Motor | **whisper.cpp** (MIT, C/C++) |
| Model | **large-v3-turbo** (varsayılan); hız yedekleri `medium` / `small` |
| Lisans | MIT (motor) · model ağırlıkları MIT |
| Dil | Çok dilli; **Türkçe (tr)** destekli |
| Yetenek | Çevrimdışı toplu çıkarım; akışlı/parçalı kullanım mümkün |
| Boyut | turbo ~1,6 GB (Q5) · medium ~1,5 GB · small ~0,5 GB |
| Nerede | **CPU** (GPU LLM'e ait) |
| Yedek | `medium` / `small` (CPU'da daha hızlı) |

> **Ölçüldü (2026-10-17, Ryzen 5 3600 6C/12T, CPU):** `large-v3-turbo` **f16** ile RTF ~4,2
> (`-t 4`, whisper varsayılanı). **q5_0 quant** + `-t 12` ile **RTF ~1,9** (encode 10,0 sn / 5,6 sn ses).
> Model karşılaştırması (q5_0, 12 thread): base **0,84 sn** (Türkçe zayıf) · small **2,5 sn** (zayıf) ·
> medium **7,5 sn** (iyi) · turbo **11,0 sn** (en iyi). ⚠️ whisper her istekte **30 sn penceresini**
> encode eder → kısa seste sabit maliyet. ⚠️ `-ac` **kullanılmaz** (tekrar döngüleri).
> Canlı hat için **`whisper-server`** (kalıcı model) önerilir. Ayrıntı: [`docs/faz2-sonuc.md`](docs/faz2-sonuc.md).

> **Hız notu:** whisper.cpp `large-v3-turbo` CPU'da tipik sohbet cümlesini ~0,2–0,4 sn'de çevirir
> (thread ayarına bağlı). Uzun cümlede `<1 sn` sınırda; VAD bölütleme + parça paralelliği ile telafi
> edilir. Gerekirse `medium`/`small`'a inilir.

### 3.3 TTS: takas edilebilir katman

| Motor | Doğallık | Türkçe | Canlı hız | Lisans | Rol |
|---|---|---|---|---|---|
| **Chatterbox Multilingual v3** | En yüksek | ⚠️ zayıf (ş/ğ yamalı; §3.3) | GPU | MIT | EN birincil |
| **Trendyol-TTS** (`voxcpm`, VoxCPM2 + TR LoRA, ~2B) | Yüksek | ✅ anlaşılır | ❌ RTF ~3, ~5,6 GB VRAM | MIT | **TR çevrimdışı/yüksek kalite** |
| **Piper** | Orta | ✅ **WER 0,000** | ✅ **RTF 0,19 · CPU** | GPL-3.0 | **Hızlı/canlı aday** |
| Windows SAPI | Düşük | ✅ | ✅ | — | Son çare |

> **Ölçüldü (2026-10-18):** Piper `tr_TR-dfki-medium` — 5 cümle **RTF 0,19**;
> geri-çevirim (whisper turbo) **WER 0,000** (5/5 birebir, diakritik doğru). Akışlı hatta
> **ilk ses 0,77–0,90 sn** (Chatterbox 4,2–7,6 sn). **CPU'da** çalışır → GPU tümüyle LLM'de
> (ilke #1) ve guard retry yok. Kurulum `scripts/piper-kur.ps1` (⚠️ **ASCII dizin şart**, tuzak #16).
> Ayrıntı: [`docs/akishli-hat.md`](docs/akishli-hat.md) §5.2.

> **Düzeltildi ve KABUL EDİLDİ (2026-10-18):** Chatterbox TR telaffuz hataları `ş→sh` + **`ğ` respell**
> (`tr_softg()`: iki ünlü arası → `y`, ünlüden sonra ünsüz/sonda → önceki ünlü: `dağ`→`daa`) ile
> yamalanıyor. **Adım artık doğru** (`çalıştığı` → ❌"çalıştı ki" ⏩ ✅"çalıştığı"); **kulak testi ✅**
> (kullanıcı: *"yeni olan güzel"* → karar #23). A/B (seed 42, geri-çevirim): 9 kelimede kelime-doğru
> **%44 → %67**, 1. cümlede guard retry **23,2 → 5,0 sn**. Kapatma `--chatterbox-no-softg`
> (sunucuda istek başına `{"softg": false}`). ⚠️ `ğ`'den bağımsız hatalar sürüyor (`yerel`, `için`,
> `Aybars`) → **Chatterbox TR kırılgan**; kelime-istisna sözlüğü gerekir. Ayrıntı:
> [`docs/tts-kiyaslama.md`](docs/tts-kiyaslama.md) §9.4.

> **Ölçüldü (2026-10-16):** Trendyol-TTS Türkçe **anlaşılır** (geri-çevirim Whisper WER ~0,08) ama
> ~5,6 GB VRAM + RTF ~3 → hedef 8 GB kartta yerleşik LLM ile sığmaz ve `<1 sn` hedefini yer.
> Bu yüzden **canlı hattın varsayılanı değil**; `tts-tools.py --backend voxcpm` ile çevrimdışı
> motor olarak eklendi (karar #16). Ayrıntı: [`docs/tts-tr-sonuc.md`](docs/tts-tr-sonuc.md).

## 4. Bileşen haritası

✅ = mevcut · ⬜ = hedef

| Durum | Yol | İçerik |
|---|---|---|
| ⬜ | `aybars_speaks-desktop.ps1` | Ana uygulama: WinForms arayüzü, sohbet durumu, olay döngüsü |
| ⬜ | `agent/llm-run.ps1` | `llama-server` başlat/durdur, MTP, VRAM kapısı |
| ✅ | `agent/mtp_inject.py` | Quant GGUF'a MTP/`nextn` başlığı ekler (taban `huihui-ai` deposundan) |
| ✅ | `agent/mtp-durum.py` | Bir GGUF'un MTP durumunu JSON olarak yazar |
| ✅ | `scripts/mtp-dogrula.ps1` | MTP durumunu denetler; `-Inject` ile başlığı ekler |
| ✅ | `agent/asr-tools.py` | 16 kHz mono dönüştürme + **whisper.cpp** çıkarımı (tek-atım **veya** `--server-url` ile kalıcı `whisper-server`) + gecikme/RTF ölçümü |
| ✅ | `scripts/asr-olcum.ps1` | Faz 2 ASR ölçüm koşum takımı (sarmalayıcı) |
| ✅ | `scripts/whisper-server.ps1` | Kalıcı `whisper-server` başlat/durdur (`-ng`, port 8081); model bellekte kalır |
| ✅ | `scripts/tts-server.ps1` | Kalıcı TTS sunucusu (`tts-tools.py --serve`, port 8082); Chatterbox bellekte kalır · `-Backend piper` ile **CPU Piper** (yükleme yok) |
| ✅ | `scripts/piper-kur.ps1` | Piper + `tr_TR-dfki-medium` sesini **ASCII dizine** kurar (`%LOCALAPPDATA%\aybars\piper`; repo yolu non-ASCII olduğu için şart) |
| ✅ | `agent/tts-tools.py` | Takas edilebilir TTS: Chatterbox / **voxcpm** (Trendyol-TTS, TR) / **Piper** / SAPI + **toplu mod** (`--batch-file`) + **kalıcı sunucu** (`--serve`; chatterbox **veya piper**) + **uzun-kuyruk guard** (Chatterbox; süre sınırı + 1 retry; `--no-guard`) |
| ✅ | `agent/pipeline.ps1` | Boru hattı (**toplu/referans yol**): ASR → LLM (HTTP) → cümle bölme → **toplu** TTS (model tek yükleme) |
| ✅ | `agent/llm-stream.py` | **Akışlı tur motoru:** `llama-server` **SSE** → kademeli cümle bölme → cümle başına TTS → arka planda çalma; zaman damgalı JSON (`reasoning_content` yok sayılır, sembol-only atlanır, geçici ağ hatasında 2 deneme) |
| ✅ | `agent/pipeline-stream.ps1` | **Akışlı** boru hattı (ASR + `llm-stream.py`): ilk sesi erken çıkarır (ilke #7) |
| ⬜ | `agent/audio-capture.ps1` | winmm `mciSendString` ile bağımlılıksız kayıt |
| ✅ | `tests/` | pytest (MTP enjeksiyonu + ASR araçları) |
| ✅ | `scripts/`, `docs/` | kurulum/tanı, belgeler |

## 5. Gecikme bütçesi (hedef < 1000 ms)

| Aşama | Hedef | Yöntem |
|---|---|---|
| Endpoint | 0–200 ms | Bas-konuş = 0; VAD + ~200 ms eşik |
| STT | ≤ 400 ms | whisper.cpp `large-v3-turbo` (gerekirse `medium`/`small`). Ölçüm: turbo ~10 sn, medium ~7,5 sn, small ~2,5 sn, base ~0,84 sn (CPU; ⚠️ hedef bu donanımda tutmuyor) |
| LLM ilk token | ≤ 250 ms | Yerleşik model + KV prefix cache |
| TTS ilk ses | ≤ 150 ms | **Piper (CPU, ölçülen ~0,3–0,5 sn)**; Chatterbox/Piper, ilk cümlede. **Trendyol-TTS (`voxcpm`) canlı için uygun değil** (RTF ~3, ~5,6 GB VRAM) — çevrimdışı/yüksek kalite |

> **Ölçüldü (2026-10-18, akışlı hat):** Chatterbox ile LLM+TTS ilk ses **7,05–7,60 sn** (toplu akışta
> 18,8 sn; düşünme açıkken 9,52 sn). **Piper (CPU) ile ilk ses 0,77–0,90 sn** — hedefin (<1 sn) içinde;
> Piper RTF 0,19, geri-çevirim WER 0,000. Uçtan uca (ASR turbo CPU ~9,9 sn + akışlı Piper) **~11,7 sn**.
> **Kalan tek darboğaz STT (~10 sn = uçtan uca sürenin ~%85'i)**; whisper her istekte 30 sn penceresini
> encode ettiği için kısa seste sabit maliyet. Ayrıntı: [`docs/akishli-hat.md`](docs/akishli-hat.md) §5.1/§5.2.

## 6. Kritik tuzaklar

1. **Uygulama yalnızca gömülü PowerShell 7 ile çalışır.** `Start-ThreadJob` 5.1'de yoktur.
2. **`Start-ThreadJob -FilePath` içinde `$PSScriptRoot` boştur.** Kök `$JobData.root` ile taşınır.
3. **Windows PowerShell 5.1 BOM'suz `.ps1`'i ANSI okur.** 5.1 betikleri ASCII tut ya da UTF-8 BOM'lu kaydet.
4. **KV önbellek eşleşmesi.** Arayüzün mesaj dizisi sunucununkiyle bayt bayt aynı olmalı.
5. **`Start-DetachedProcess` kullan.** `Start-Process -Redirect…` çağıranın stdout'unu devralır.
6. **VRAM payı küçük tutulur.** 9B i1-Q5_K_M (~6,6 GB) + MTP + KV, 8 GB kartın sınırında.
7. **MTP bayrağı yalnızca GGUF MTP katmanı taşıyorsa eklenir** (`Test-GgufHasMtp`). Quant GGUF
   MTP'yi içermez; indirmede `mtp_inject.py` ile geri eklenir (bkz. [`docs/mtp-dogrulama.md`](docs/mtp-dogrulama.md)).
8. **ASR/TTS CPU'yu paylaşır.** Aynı anda çalışmazlar (dinleme vs konuşma), ama gürültülü makinede ölçüm şart.
9. **whisper.cpp thread sayısı.** `-t` ölçümle ayarlanır. ⚠️ "fiziksel çekirdek" genel kuralı burada
   geçerli **değil**: Ryzen 5 3600'da `-t 12` (mantıksal) > `-t 6` (fiziksel) ölçüldü. `asr-tools.py`
   varsayılanı mantıksal çekirdek.
10. **Ağır GPU işi çalıştırmadan önce kullanıcıya SOR.** Model yükleme / GPU'da çıkarım gibi işler
    kullanıcıyı bekletebilir veya başka GPU işiyle çakışır; izinsiz başlatma.
11. **Windows konsol kodlaması (cp1254) `print`'i patlatır.** LLM cevabındaki emoji gibi UTF-8 dışı
    karakterler `UnicodeEncodeError` verir; TTS gibi araçlarda **stdout UTF-8'e çevrilmeli**
    (`sys.stdout.reconfigure`), yoksa iş tamamen düşer. Ayrıca `.ps1` betiklerinde native araç
    **stdout'unu yut** (`1> $null`), JSON'u dosyadan oku — aksi halde çıktı fonksiyon dönüşüne karışır.
12. **Repo yolu non-ASCII içeriyor** ("Varsayılan" → `ı`). `Start-Process`'e **mutlak** yol argüman
    verilirse karakter bozulur (whisper-server yanlış yolu açıp çöker) → **göreli yol + `-WorkingDirectory`**.
13. **`whisper-server` `-ng` ister.** GPU'yu denerse `0xC0000409` (fast-fail) ile çöker; STT CPU'da
    olduğu için `-ng` hem doğru hem gerekli. `llama-server`'da `--reasoning-budget-message` gibi
    boşluk içeren değerler tırnaklanmalı ve `=` biçimi kullanılmamalı.
14. **Python çıktısını PowerShell `1>` ile yönlendirme.** Windows PowerShell çıktıyı **UTF-16** yazar ve
    Python'un UTF-8 baytlarını OEM (cp850) sanıp Türkçe karakterleri bozar (`ı` → `─▒`). JSON'u
    **dosyaya Python yazsın** (`--json-out` / `Path.write_text(encoding="utf-8")`) ya da `pwsh` +
    `-Encoding utf8` kullanın; aksi halde yoldaki `ı` bozulur ve `Test-Path` / `os.path.exists`
    **yanlış `False`** verir (ölçümü yanıltır — 2026-10-17'de tam bunu yaşadık).
15. **`Get-Content -Raw` (PS 5.1) BOM'suz UTF-8 dosyayı ANSI okur.** Python'un `--json-out` ile
    yazdığı JSON'daki yollarda `ı` bozulur → `Test-Path -LiteralPath` **yanlış `False`** döner
    (akışlı hatta üretilen 3 WAV "kayıp" göründü, 2026-10-18). Çözüm: **`Get-Content -Raw -Encoding UTF8`**.
    Ayrıca native aracın JSON'unu **stdout'tan boruyla** almak yerine `--out`/`--json-out` ile
    **dosyaya** yazdır (ASR yolu artık böyle) — tuzak #14 ile aynı sınıf hata.
16. **Bazı ikililer non-ASCII yolu hiç okuyamaz (mutlak yolla çöker).** Non-ASCII repo yolunda:
    **Piper**'ın espeak-ng katmanı `Illegal byte sequence`, onnxruntime `0xC0000409 (fast-fail)`;
    **`whisper-cli.exe`** non-ASCII **mutlak** `-m`/`-f` yoluyla `0xC0000409` ile çöküyor (aynı makinede
    **göreli** yolla sorunsuz — `cwd` + göreli yol kullan). Çözüm: Piper'ı ve ses dosyasını
    **ASCII dizine** kur (`scripts/piper-kur.ps1` → `%LOCALAPPDATA%\aybars\piper`); whisper-cli'yi
    **göreli yolla** çağır. (Tuzak #12'nin genellemesi.)

## 7. Değişiklik kontrol listesi

- [ ] MTP hâlâ açık mı? (Kesin kural)
- [ ] LLM hâlâ i1-Q5_K_M (Huihui-Qwen3.5-9B-abliterated) mi?
- [ ] STT hâlâ whisper.cpp mi (Qwen3-ASR'a dönülmedi)?
- [ ] Dil modeli hâlâ yerleşik mi (boşaltılmıyor)?
- [ ] GPU'ya LLM dışında bir şey taşınmadı mı?
- [ ] TR ve ENG sürümleri tutarlı mı?
- [ ] `README.md`, `docs/mimari.md`, `docs/mtp-dogrulama.md`, `docs/faz2-olcum-plani.md`, `docs/faz2-sonuc.md`, `docs/akishli-hat.md`, `docs/kararlar.md` güncel mi?

## 8. Değişiklik günlüğü

| Tarih | Değişiklik | Dosyalar |
|---|---|---|
| 2026-10-19 | **MIT lisansı eklendi** (`LICENSE`; telif sahibi `workaybarsh`); karar #24 işlendi, README lisans bölümü ve kullanım satırı güncellendi. | LICENSE, README.md, docs/kararlar.md, AGENTS.md |
| 2026-10-19 | Depo adı **aybars_speaks**; metinler güncellendi. | tümü |
| 2026-10-18 | **Chatterbox `ğ` telaffuz hatası bulundu ve düzeltildi (kullanıcı kulağı → ölçüm).** Şikâyet: `çalıştığı` → "çalıştı ki". Geri-çevirim doğruladı ("Tam yarar çalıştı ki işin…"). **Kök neden:** grapheme sözlükte `ğ` **var**, NFKD ayrığı yok → hata tokenizer'da değil **akustik modelde**. Yeni `tr_softg()`: `ğ` iki ünlü arası → `y`, ünlüden sonra ünsüz/sonda → uzun ünlü (`dağ`→`daa`); `ş→sh`'den önce uygulanır. **A/B (seed 42, aynı metinler):** `çalıştığı` **düzeldi** (eski yama "çalış dışı", yamasız "çalıtıcı"), 9 kelimede kelime-doğru **%44 → %67**, guard retry **23,2 → 5,0 sn**. Kapatma: `--chatterbox-no-softg` / istek başına `{"softg": false}` (sunucu A/B kablolaması). **Kulak testi ✅ (2026-10-18): kullanıcı "yeni olan güzel" dedi → yama varsayılan kabul edildi (karar #23).** ⚠️ `yerel`/`için`/`Aybars` hataları sürüyor → Chatterbox TR kırılgan. **59 test** (+3). Ölçüm: `logs/softg-bench.py`, `logs/softg-asr.py`. | agent/tts-tools.py, scripts/tts-server.ps1, tests/test_tts_tools.py, docs/tts-kiyaslama.md (§9.4), docs/kararlar.md (#23), DURUM.md, AGENTS.md |
| 2026-10-18 | **TTS darboğazı çözüldü: Piper (CPU) akışlı hatta bağlandı.** `tts-tools.py --serve --backend piper` + `scripts/tts-server.ps1 -Backend piper` + `scripts/piper-kur.ps1` (ASCII dizine kurulum). **Ölçüm (aynı oturum, aynı istem):** ilk ses **Chatterbox 4,2–7,6 sn → Piper 0,77–0,90 sn** (hedefin <1 sn içinde); Piper `tr_TR-dfki-medium` **RTF 0,19**, geri-çevirim **WER 0,000** (5/5). Uçtan uca (ASR turbo ~9,9 sn + Piper) **~11,7 sn** → kalan tek darboğaz **ASR (%85)**. Piper CPU'da çalışır (ilke #1: GPU tümüyle LLM'e), guard retry üretmez. **Yeni tuzak #16:** Piper/onnxruntime ve `whisper-cli` non-ASCII yolda çöker (`Illegal byte sequence` / `0xC0000409`) → Piper ASCII dizinde, whisper-cli göreli yolla. **54 test** (+2: piper sunucu yolu). | agent/tts-tools.py, scripts/tts-server.ps1, scripts/piper-kur.ps1, tests/test_tts_tools.py, docs/akishli-hat.md, docs/tts-kiyaslama.md, DURUM.md, AGENTS.md, README.md |
| 2026-10-18 | **Akışlı hat eklendi (ilke #7 kodda).** `agent/llm-stream.py`: `llama-server` **SSE** → kademeli cümle bölme → cümle başına TTS → **arka planda** çalma (oynatma thread'i; `reasoning_content` yok sayılır, sembol-only atlanır) + `agent/pipeline-stream.ps1` (ASR sarmalayıcısı). **Ölçüm (LLM+TTS): ilk ses 18,8 sn → 7,05–7,60 sn (~2,5×)**; düşünme açıkken 9,52 sn; uçtan uca (ASR turbo CPU 9,91 sn) 13,4 sn. **Bulgular:** kısa cümlede guard retry ilk sesi 13–18 sn'ye çıkarıyor — uç enerjisi analizi kuyruğun **fazladan konuşma** olduğunu gösterdi (uç kırpma çözmez). Ölçüm sırasında iki gerçek `ConnectionResetError` **şeffaf telafi** edildi. **Kritik düzeltme:** PS 5.1 `Get-Content -Raw` BOM'suz UTF-8'i ANSI okuyordu → akışlı WAV'lar "kayıp" (tuzak #15); ASR yolu `--out` + UTF-8'e alındı; TTS sunucu çağrısı **2 deneme** (yerel yedeğe düşüp OOM olmak yerine dürüst hata). **52 test.** | agent/llm-stream.py, agent/pipeline-stream.ps1, agent/pipeline.ps1, tests/test_llm_stream.py, docs/akishli-hat.md, docs/kararlar.md, DURUM.md, AGENTS.md |
| 2026-10-17 | **Guard incelemesi: `out` yolu bug'ı bulundu ve düzeltildi.** Retry kazandığında `synth_chatterbox` silinmiş `.retry.wav` yolunu döndürüyordu; `pipeline.ps1` bu alanı `Test-Path` ile kullandığı için **düzeltilen cümle sessizce çalınamıyordu** (24 üretimlik ölçümde 6 kayıt). `out` artık gerçek dosya (eski yol `retry_out`), pipeline'a dosya adına düşen savunma, ölçüm için `guard_extra_seconds` eklendi. Regresyon ağı: fix'siz **3 test düşüyor**, fix'le **39 test**. | agent/tts-tools.py, agent/pipeline.ps1, tests/test_tts_tools.py, docs/tts-kiyaslama.md, DURUM.md |
| 2026-10-17 | **TTS uzun-kuyruk (halüsinasyon) guard'ı eklendi.** İnceleme sonucu: "boşları göndermeme" filtreleri **çökmeyi** engelliyordu (`IndexError: max()` / CUDA `device-side assert`); taşan sesi kesen ise Chatterbox'ın kendi `alignment_stream_analyzer`'ı (`forcing EOS, long_tail=True`) — **iki ayrı mekanizma** (karar #21). Guard: `audio_guard_limit = max(3×beklenen, beklenen+2 sn)` (beklenen ≈ harf/14) aşılırsa cümleyi **1 kez** daha üret, **kısa olanı** tut (`--no-guard` kapatır). **GPU ölçümü (24 üretim, 4 seed): 7 tetiklenme (%29), en uzun yakalanan kuyruk 6,04 sn, 0 hata**; uzun cümlede hiç tetiklenmedi; kalıcı sunucu yolu doğrulandı. Boş/emoji-only girdi `ensure_speakable` ile modele **hiç gitmiyor** (parti düşmez). **38 test**. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-kiyaslama.md, docs/kararlar.md, DURUM.md, AGENTS.md |
| 2026-10-17 | **Kalıcı TTS sunucusu eklendi** (`tts-tools.py --serve` + `scripts/tts-server.ps1`, port 8082). Ölçüm (4 cümle): cümle-cümle **106,6 sn** → toplu 48,4 sn → **kalıcı sunucu 16,6–18,5 sn**. Tam pipeline üç sunucuyla **tur başına ~23–27 sn**. Bozuk girdi CUDA bağlamını bozabildiği için sunucu metin olmayan öğeleri 400 ile reddeder, `/health` `fatal` bildirir. **32 test**. Disk temizliği ~15 GB. | agent/tts-tools.py, agent/pipeline.ps1, scripts/tts-server.ps1, tests/, docs/tts-kiyaslama.md, DURUM.md, AGENTS.md |
| 2026-10-17 | **Pipeline toplu TTS'e bağlandı + ASR optimize edildi.** `pipeline.ps1` artık tüm cümleleri tek çağrıda üretir (`--batch-file`+`--out-prefix`); ölçüm 4 cümlede **106,6 → 48,4 sn**. ASR: **f16→q5_0 quant** + mantıksal thread → **RTF 4,2→1,9**; `-ac` reddedildi (tekrar döngüsü). Model karşılaştırması (base/small/medium/turbo). **`whisper-server` kalıcı süreç** desteği (`--server-url`). Kritik bug: `uses_mtl` NameError + emoji `UnicodeEncodeError` (toplu üretimi düşürüyordu) düzeltildi. **30 test**. PS7 kuruldu (7.6.7). | agent/pipeline.ps1, agent/tts-tools.py, agent/asr-tools.py, scripts/whisper-server.ps1, scripts/asr-olcum.ps1, tests/, docs/faz2-sonuc.md, docs/kararlar.md, DURUM.md, BASLA.md, AGENTS.md |
| 2026-10-17 | **Pipeline uçtan uca çalıştı** (whisper→llama-server MTP→Chatterbox). LLM ölçüldü: ~103 tok/sn, TTFT ~0,3 sn, MTP acceptance ~0,7. Düşünme açık+bütçe 256 doğrulandı. `tts-tools.py`'ye **toplu mod** eklendi. | agent/pipeline.ps1, agent/tts-tools.py, DURUM.md, .gitignore, AGENTS.md |
| 2026-10-17 | **Chatterbox "ş" respell çözümü:** `ş→sh` kulak testinde doğrulandı → TR için otomatik (`--lang tr`). **20 test**. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-kiyaslama.md, docs/kararlar.md, DURUM.md, AGENTS.md |
| 2026-10-17 | **İki donanım profili (A: 8 GB VRAM/16 GB RAM · B: 16 GB VRAM/32 GB RAM)** kaynak bütçesine eklendi — model/CPU-GPU dağılımı, VRAM/RAM tahminleri ve B için varyantlar. | docs/mimari.md, DURUM.md, AGENTS.md |
| 2026-10-17 | **Chatterbox TR diakritik sorununun kök nedeni bulundu ve yaması yazıldı:** tokenizer'ın `NFKD` + Türkçe-duyarsız `lower()` hatası → `install_tr_tokenizer_fix()` / `--chatterbox-tr-fix` (offline, **19 test**). Ses doğrulaması GPU boşken. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-kiyaslama.md, docs/tts-tr-sonuc.md, docs/kararlar.md, DURUM.md, AGENTS.md |
| 2026-10-16 | **Bağımsız Türkçe TTS kıyası işlendi** (arXiv:2610.06057, Sestek): Chatterbox vs CosyVoice/OmniVoice/VoxCPM2/VITS. Chatterbox hiçbir metriği kazanmıyor + kısa cümlede çöküyor; VoxCPM2 klon/kararlılık, CosyVoice doğallık lideri. Karar #17. | docs/tts-kiyaslama.md, docs/kararlar.md, DURUM.md, README.md, AGENTS.md |
| 2026-10-16 | **Türkçe TTS değerlendirildi + `voxcpm` backend eklendi.** Trendyol-TTS (VoxCPM2 + TR LoRA) ölçüldü: ~5,6 GB VRAM, RTF ~3, geri-çevirim Whisper WER ~0,08 → **anlaşılır ama canlı hat için ağır**; çevrimdışı motor olarak `tts-tools.py`'ye eklendi. Testler 17'ye çıktı. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-tr-sonuc.md, docs/kararlar.md, DURUM.md, README.md, AGENTS.md, docs/mimari.md |
| 2026-10-16 | **Faz 2 ASR hattı iskeleti eklendi** (`asr-tools.py`, `asr-olcum.ps1`) ve **gerçek whisper.cpp ile uçtan uca doğrulandı** (base.en, CPU, RTF ~0,19). Testler 13'e çıktı. | agent/asr-tools.py, scripts/asr-olcum.ps1, tests/, docs/faz2-olcum-plani.md, AGENTS.md |
| 2026-10-16 | **İlk çalışan araç eklendi:** `agent/mtp_inject.py` (kanıtlı) + `scripts/mtp-dogrula.ps1` durum/enjeksiyon betiği. Depo "sesli" olarak işaretlendi. | agent/mtp_inject.py, scripts/mtp-dogrula.ps1, README.md, AGENTS.md |
| 2026-10-16 | **MTP doğrulandı ve zorunlu kılındı.** Hedef quant GGUF'ta MTP yok; kaynak 15 tensor mevcut; `mtp_inject.py` şart. Doğrulama + kabul testleri belgesi eklendi. | README.md, AGENTS.md, docs/mimari.md, docs/kararlar.md, docs/mtp-dogrulama.md |
| 2026-10-16 | LLM, **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (mradermacher imatrix quant) olarak belirlendi. | README.md, AGENTS.md, docs/mimari.md, docs/kararlar.md |
| 2026-10-16 | STT **Qwen3-ASR → whisper.cpp** (`large-v3-turbo`) olarak geri çevrildi. | README.md, AGENTS.md, docs/mimari.md, docs/faz2-olcum-plani.md, docs/kararlar.md |
| 2026-10-11 | README'ye **Durum** bölümü eklendi: taslak (`v0.1-plan`), kod yok, AR-GE yedek yolları not edildi. | README.md, AGENTS.md |
| 2026-10-11 | "Değerlendirilen ve vazgeçilen alternatifler" bölümü eklendi. | docs/kararlar.md, docs/mimari.md |
| 2026-10-11 | STT whisper'dan **Qwen3-ASR-1.7B**'ye çekildi (o dönem); hız yedeği 0.6B. | tümü |
| 2026-10-11 | Mimariye tur dizisi + sorumluluk tablosu; Faz 2 ölçüm planı. | docs/mimari.md, docs/faz2-olcum-plani.md |
| 2026-10-11 | Model MamidLabs LITE ile eşitlendi. | tümü |
| 2026-10-11 | Depo açıldı; plan yazıldı. | tümü |
