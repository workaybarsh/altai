# Faz 2 · Sonuçlar

Bu belge, `<1 sn` STT hedefinin **ölçüm sonuçlarını** toplar. Ölçüm planı:
[`faz2-olcum-plani.md`](faz2-olcum-plani.md).

> ⚠️ Aşağıdaki duman testi **mekanizma doğrulamasıdır** (hat çalışıyor mu?); hedef donanım +
> `large-v3-turbo` ile **nihai ölçüm değildir**.

## Duman testi — 2026-10-16 (hat doğrulaması)

**Amaç:** `asr-tools.py` + `asr-olcum.ps1` hattının gerçek whisper.cpp ile uçtan uca çalıştığını
kanıtlamak.

| Alan | Değer |
|---|---|
| Motor | whisper.cpp (resmî Windows CPU yapısı, b5454) |
| Model | `ggml-base.en.bin` (~141 MB) — **yalnızca duman testi** |
| Girdi | Windows SAPI (Zira, en-US) ile üretilen konuşma, 16 kHz'ye çevrildi |
| Ses süresi | 7,16 sn |
| Thread | 4 |
| Tekrar | 3 |

**Sonuç:**

| Metrik | Değer |
|---|---|
| Transkript | "Hello, this is a test of the Local Voice Assistant. The quick brown fox jumps over the lazy dog." |
| ASR (medyan) | **1,39 sn** |
| p95 | 1,39 sn |
| RTF | **0,19** |
| Durum | ✅ Hat çalışıyor; transkript doğru |

**Çıkarımlar:**

- Dönüşüm (ffmpeg → 16 kHz mono), çıkarım, zamanlama ve JSON sözleşmesi **doğru** çalışıyor.
- `base.en` ile RTF 0,19 → 7 sn ses 1,4 sn'de yazıldı. **Hedef `large-v3-turbo` çok daha ağır**
  (≈10×); gerçek gecikme bu makinede ölçülmelidir (asıl Faz 2 işi).
- "Dürüst başarısızlık" doğrulandı: whisper yoksa araç `ok=false` döndürüyor, uydurmuyor.

## Nihai ölçüm — 2026-10-17 (`large-v3-turbo`, gerçek donanım, CPU)

**Donanım:** AMD Ryzen 5 3600 (6C/12T), RTX 5060 Ti 16 GB, Windows. **Motor:** whisper.cpp 1.9.5
(b5454, CPU backend `ggml-cpu-haswell.dll`). **Girdi:** 5,56 sn Türkçe konuşma (16 kHz mono).
**whisper-cli varsayılanı:** `-t 4`, `-fa açık`.

### 1) Model (f16 → q5_0) ve thread

| Model | Thread | encode | toplam (duvar) | RTF |
|---|---|---|---|---|
| f16 | 4 (varsayılan) | 20,9 sn | 23,0 sn | ~4,2 |
| f16 | 6 | 15,8 sn | 17,8 sn | 3,2 |
| f16 | 12 | 13,3 sn | 15,1 sn | 2,7 |
| **q5_0** | 6 | 13,1 sn | 14,2 sn | 2,6 |
| **q5_0** | **12** | **10,0 sn** | **11,0 sn** | **~1,9** |

- Model dosyası **f16**'ydı (`ftype=1`); CPU'da F16 GEMM **~127 GFLOPS**, Q8_0 **~252**, Q4_0 **~231**
  (`whisper-bench -w 2`) → **`whisper-quantize` ile `ggml-large-v3-turbo-q5_0.bin` (574 MB)** üretildi.
  **Transkript birebir aynı.** Q5_0 hem encode'u hem yükleme süresini (~1,2 → ~0,5 sn) düşürdü.
- **Thread:** `-t 12` > `-t 6` > `-t 4`. Yani bu makinede **SMT kazanç sağlıyor**
  ("fiziksel çekirdek" genel kuralı burada geçerli değil) → `asr-tools.py` varsayılanı **mantıksal
  çekirdek sayısı** yapıldı (`--threads` ile geçersiz kılınabilir).

### 2) Gerçek darboğaz: sabit 30 sn'lik encode penceresi

whisper her istekte **30 sn mel penceresini** encode eder; kısa cümlede bile maliyet sabittir.
5,56 sn'lik ses için encode ~10 sn (q5_0, 12 thread) → **RTF kısa seste yapay olarak yüksek**.
Bu yüzden `asr-tools.py` artık `load_seconds` / `infer_seconds` / `infer_rtf` alanlarını raporluyor
(whisper.cpp `whisper_print_timings` satırları ayrıştırılıyor).

### 2) Model karşılaştırması (hepsi q5_0, `-t 12`, aynı 5,6 sn TR ses)

| Model | Boyut | yükleme | encode | toplam | RTF | Transkript kalitesi |
|---|---|---|---|---|---|---|
| `base` | 53 MB | 0,07 sn | 0,47 sn | **0,84 sn** | **0,15** | ❌ zayıf ("yere çalışan bir sesde aslanım") |
| `small` | 167 MB | 0,16 sn | 1,73 sn | 2,53 sn | 0,45 | ❌ zayıf ("yere… sesti aslı tanım") |
| `medium` | 514 MB | 0,42 sn | 5,51 sn | 7,51 sn | 1,35 | ✅ iyi (yalnız "asistanım"→"aslanım") |
| `turbo` | 547 MB | 0,46 sn | 10,08 sn | **11,00 sn** | 1,98 | ✅ en iyi (birebir) |

- **`<1 sn` hedefini tek başına `base` tutuyor** — ama Türkçe doğruluğu sohbet için kabul edilemez.
  `small` ~2,5 sn ve yine zayıf; `medium`/`turbo` doğru ama 7,5–11 sn.
- Yani bu CPU'da **doğruluk ve `<1 sn` birlikte tutmuyor** → açık karar (daha küçük model mi,
  GPU'ya whisper mı, hedef mi revize?).

### 3) ❌ `-ac` (audio context) DENENDİ ve REDDEDİLDİ

`-ac` ile encoder penceresini kısmak cazip görünüyor (q5_0 t=12: `-ac 768` → encode 4,9 sn;
`-ac 512` → 3,2 sn). **Ama güvenli değil:** yanlış/eksik transkript ve **tekrar döngüleri**
("asistanım"→"hastanım"; 11 sn seste cümle 5× tekrar, 22 sn seste 115 kelimeye şişme) üretiyor.
**Kullanılmayacak.**

### 4) Kalıcı süreç (whisper-server) — model yükleme tekrarını bitirir

`whisper-cli` her çağrıda modeli yeniden yükler (q5_0 ~0,5 sn, f16 ~1,2 sn). `scripts/whisper-server.ps1`
+ `asr-tools.py --server-url http://127.0.0.1:8081` ile model **bellekte kalır** → her istek saf çıkarım.
Ölçüm (turbo q5_0, sunucu modu): **9,94 sn** (tek-atım 10,48 sn; fark ~0,5 sn'lik yükleme).
⚠️ Sunucu **`-ng`** ile başlatılmalı (GPU'yu denerse `0xC0000409` ile çöker) ve repo yolu non-ASCII
olduğu için **göreli model yolu + `-WorkingDirectory`** kullanılmalı.

> **Sonuç:** güvenli ayarlarla (`q5_0` + 12 thread) RTF **~4,2 → ~1,9**; model karşılaştırması
> `base`/`small`/`medium`/`turbo` için yukarıda. **Hedef `<1 sn`, bu CPU'da kabul edilebilir Türkçe
> doğrulukla tutulamıyor** (turbo encoder tek başına ~10 sn; whisper her istekte 30 sn penceresi
> encode ediyor). Karar: daha küçük model / GPU'ya whisper / hedefi revize etme.

## Yapılacak (hedef donanım)

- [x] `large-v3-turbo` ile ölçüm (5,6 sn TR, N=3, medyan + p95) — 2026-10-17
- [x] **Thread ölçekleme** (4/6/12) — `-t 12` en hızlı (SMT kazanç sağlıyor)
- [x] `medium`/`small`/`base` karşılaştırması — 2026-10-17 (tablo yukarıda)
- [x] Kalıcı `whisper-server` modu ölçümü
- [ ] Türkçe WER (gerçek konuşma, elle referans)
- [ ] VAD endpoint gecikmesi + akışlı pencere
- [ ] Kısa/orta/uzun × TR/EN genişletilmiş ölçüm (N=10)
- [ ] Nihai karar (model + CPU/GPU) → [`kararlar.md`](kararlar.md)
