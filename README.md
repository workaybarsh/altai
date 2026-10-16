# aybars_says — sesli yerel yapay zekâ sohbet botu (Windows)

Gerçek zamanlı, **tamamen yerel** ve yapay zekâ destekli **sesli** sohbet botu (Windows): mikrofonla
konuşursun, bot **sesle** yanıt verir.

> Eski adı: **mamidChats Chatbot**. Bu depo ağırlıklı olarak **plandır**; ilk çalışan araç olarak
> `agent/mtp_inject.py` (MTP başlığı enjeksiyonu) eklenmiştir.

## Durum

**Taslak (planlama) — `v0.2-plan`. Ağırlıklı plan; çalışan ilk araç `agent/mtp_inject.py`.**


- Bu repo ağırlıklı olarak bir **tasarım/plan dokümanıdır**; ilk çalışan araç `agent/mtp_inject.py`.
- Her karar, gerekçesi ve **vazgeçilen alternatif** burada not edilir (bkz. [`docs/kararlar.md`](docs/kararlar.md)).
- Ölçüm ve AR-GE sonuçları geldikçe aynı belgeler güncellenir.
- Hedef (`<1 sn`) tutmazsa izlenecek yollar hazır: **daha küçük whisper.cpp modeli** (`small`/`medium`),
  akışlı ASR optimizasyonu, LLM quant düşürme (bkz. [`docs/faz2-olcum-plani.md`](docs/faz2-olcum-plani.md), [`docs/kararlar.md`](docs/kararlar.md)).

## Hedef

Kullanıcı konuşmayı bitirdikten sonra **1 saniye içinde** ilk sesin çıkması.

- **t₀** = kullanıcının son sözcüğü bittiği an
- **t₁** = ilk sesin hoparlörden çıktığı an
- **Hedef:** `t₁ − t₀ < 1000 ms`

Ölçü, metnin ekranda görünmesi değil **sesin başlaması**dır. Ayrıntılı bütçe: [`docs/mimari.md`](docs/mimari.md).

## Bir paragrafta ürün

Tek bir WinForms penceresinde, kullanıcı mikrofonla konuşur; uygulama konuşmayı yazıya çevirir
(**whisper.cpp**), yerel dil modeline verir (**Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** — imatrix
quant; **MTP daima açık**) ve yanıtı sesli okur (TTS). Tamamı çevrimdışı, hiçbir veri dışarı çıkmaz.
Bas-konuş ve sürekli dinleme (VAD) modları vardır.

## Özet mimari

**Ana kural: GPU'da yalnızca dil modeli çalışır; STT ve TTS CPU'da çalışır.**

```
Mikrofon → VAD/kayıt → whisper.cpp (CPU) → metin
        → Huihui-Qwen3.5-9B (GPU, MTP) → yanıt metni
        → TTS (CPU) → hoparlör
```

| Bileşen | Nerede | Neden |
|---|---|---|
| **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** + MTP | **GPU (8 GB)** | Yerel imatrix quant (~6,6 GB); boyut/kalite dengesi iyi; yerleşik kalır |
| **whisper.cpp** (`large-v3-turbo`) | **CPU** | GPU'yu LLM'e bırakır; Türkçe + çok dilli, CPU'da hızlı, olgun C/C++ ekosistem |
| TTS (Piper / Chatterbox / VoxCPM / SAPI) | **CPU** | VRAM'e dokunmaz; takas edilebilir katman (VoxCPM/Trendyol ağır → çevrimdışı) |

Bu projenin ayrı olmasının sebebi: mevcut çalışmada (MamidLabs) ComfyUI, OCR, mmproj gibi başka VRAM
tüketicileri var. Burada **tek sahipli** bir hat kurulur.

## Kesin kurallar

- **STT: whisper.cpp.** Varsayılan model **large-v3-turbo**; hız gerekirse `medium`/`small`'a inilir.
- **Model: Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (GGUF, imatrix quant).
  Kaynak: `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF`; taban: `huihui-ai/Huihui-Qwen3.5-9B-abliterated`.
  Dosya: `Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf` (~6,6 GB). MTP başlığı `mtp_inject.py` ile eklenir.
- **MTP daima açık.** `--spec-type draft-mtp`; kapatılmaz. Hız + kayıpsız çıktı.
  Quant GGUF MTP başlığını **içermez**; `mtp_inject.py` ile taban `huihui-ai` deposundan geri
  eklenir (kaynak tensorlar doğrulandı). Doğrulama + kabul testleri: [`docs/mtp-dogrulama.md`](docs/mtp-dogrulama.md).
- **GPU yalnızca LLM'e aittir.** STT ve TTS CPU'da; dil modeli yerleşik kalır, boşaltılmaz.

## Teknoloji kararları (özet)

| Konu | Karar |
|---|---|
| Yığın | PowerShell 7 + WinForms |
| Etkileşim | Bas-konuş **ve** sürekli dinleme (ayardan seçilir) |
| STT | **whisper.cpp** (`large-v3-turbo`; CPU) |
| LLM | **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (imatrix), **MTP daima açık**, GPU'da yerleşik |
| TTS | Takas edilebilir: Chatterbox v3 (EN) / Trendyol-TTS `voxcpm` (TR, ağır → çevrimdışı) / Piper (hızlı) / SAPI |
| Dil | Türkçe + İngilizce (iki sürüm) |
| Kullanım | Kişisel / kapalı |
| Hedef gecikme | < 1 sn |

Tüm kararlar: [`docs/kararlar.md`](docs/kararlar.md).

## Çalışan ilk araç: MTP enjeksiyonu

Quant GGUF, MTP/`nextn` başlığını **içermez**; bu yüzden `--spec-type draft-mtp` tek başına
llama.cpp'yi açmaz. `agent/mtp_inject.py` başlığı taban `huihui-ai` deposundan geri ekler (kayıpsız;
yalnızca 15 MTP tensoru, ana ağırlıklara dokunmaz).

```powershell
# Durum denetimi
pwsh -File scripts/mtp-dogrula.ps1 -Gguf "models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf"

# Eksikse enjekte et
pwsh -File scripts/mtp-dogrula.ps1 -Gguf "models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf" -Inject
```

Ayrıntı, kabul testleri (T1–T7) ve yedekler: [`docs/mtp-dogrulama.md`](docs/mtp-dogrulama.md).

## Faz planı

| Faz | İçerik | Durum |
|---|---|---|
| 0 | Kararlar | ✅ |
| 1 | Mimari + gecikme bütçesi | 🔄 |
| 2 | STT (whisper.cpp) hattı + < 1 sn ölçümü | ⬜ |
| 3 | LLM (9B i1-Q5_K_M + MTP) + prefix cache | ⬜ |
| 4 | TTS katmanı | ⬜ |
| 5 | WinForms arayüz + PTT/VAD + barge-in | ⬜ |
| 6 | TR/ENG sürümler + paketleme | ⬜ |

**Faz 2 neden ilk?** `<1 sn` hedefinin kaderi STT'de belirlenir; whisper.cpp'nin CPU hızı
orada ölçülür (`large-v3-turbo` yeterli mi, `medium`/`small`'a mı inilmeli).

## Dokümanlar

| Yol | İçerik |
|---|---|
| [`docs/mimari.md`](docs/mimari.md) | Mimari, veri akışı, tur dizisi, sorumluluk tablosu, gecikme bütçesi |
| [`docs/mtp-dogrulama.md`](docs/mtp-dogrulama.md) | MTP doğrulama + enjeksiyon planı (kabul testleri, yedekler) |
| [`docs/faz2-olcum-plani.md`](docs/faz2-olcum-plani.md) | Faz 2: whisper.cpp hattı ve `<1 sn` ölçüm planı |
| [`docs/faz2-sonuc.md`](docs/faz2-sonuc.md) | Faz 2 ölçüm sonuçları (duman testi kaydı) |
| [`docs/tts-tr-sonuc.md`](docs/tts-tr-sonuc.md) | Türkçe TTS (Trendyol-TTS) değerlendirmesi: VRAM, RTF, geri-çevirim WER |
| [`docs/kararlar.md`](docs/kararlar.md) | Karar günlüğü |
| [`AGENTS.md`](AGENTS.md) | Geliştirici/ajan altyapı rehberi |

## Lisans

Kişisel kullanım. (whisper.cpp MIT; LLM Llama/Qwen türevi; Chatterbox MIT; Trendyol-TTS/VoxCPM2 MIT.)
