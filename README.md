# mamidChats Chatbot

Gerçek zamanlı, **tamamen yerel** ve yapay zekâ destekli sesli sohbet botu (Windows).

> Bu depo yalnızca **plandır**. Kurulum veya çalışan kod içermez; amaç, üzerine inşa edeceğimiz
> mimariyi ve kararları tek yerde toplamaktır.

## Durum

**Taslak (planlama) — `v0.1-plan`. Kod yok.**

- Bu repo bir **tasarım/plan dokümanıdır**; çalışan uygulama içermez.
- Her karar, gerekçesi ve **vazgeçilen alternatif** burada not edilir (bkz. [`docs/kararlar.md`](docs/kararlar.md)).
- Ölçüm ve AR-GE sonuçları geldikçe aynı belgeler güncellenir.
- Hedef (`<1 sn`) tutmazsa izlenecek yollar hazır: **Qwen3-ASR-0.6B**, **whisper yedeği**, akışlı ASR
  optimizasyonu, LLM quant düşürme (bkz. [`docs/faz2-olcum-plani.md`](docs/faz2-olcum-plani.md), [`docs/kararlar.md`](docs/kararlar.md)).

## Hedef

Kullanıcı konuşmayı bitirdikten sonra **1 saniye içinde** ilk sesin çıkması.

- **t₀** = kullanıcının son sözcüğü bittiği an
- **t₁** = ilk sesin hoparlörden çıktığı an
- **Hedef:** `t₁ − t₀ < 1000 ms`

Ölçü, metnin ekranda görünmesi değil **sesin başlaması**dır. Ayrıntılı bütçe: [`docs/mimari.md`](docs/mimari.md).

## Bir paragrafta ürün

Tek bir WinForms penceresinde, kullanıcı mikrofonla konuşur; uygulama konuşmayı yazıya çevirir
(**Qwen3-ASR-1.7B**), yerel dil modeline verir (**Huihui-Qwen3.5 9B Q5_K_M** — MamidLabs LITE ile
aynı; **MTP daima açık**) ve yanıtı sesli okur (TTS). Tamamı çevrimdışı, hiçbir veri dışarı çıkmaz.
Bas-konuş ve sürekli dinleme (VAD) modları vardır.

## Özet mimari

**Ana kural: GPU'da yalnızca dil modeli çalışır; STT ve TTS CPU'da çalışır.**

```
Mikrofon → VAD/kayıt → Qwen3-ASR (CPU) → metin
        → Huihui-Qwen3.5 9B (GPU, MTP) → yanıt metni
        → TTS (CPU) → hoparlör
```

| Bileşen | Nerede | Neden |
|---|---|---|
| **Huihui-Qwen3.5 9B Q5_K_M** + MTP | **GPU (8 GB)** | MamidLabs LITE ile **aynı model** (dosyalar zaten diskte); yerleşik kalır |
| **Qwen3-ASR-1.7B** | **CPU** | GPU'yu LLM'e bırakır; Türkçe + akışlı çıkarım + dil algılama |
| TTS (Piper / Chatterbox / SAPI) | **CPU** | VRAM'e dokunmaz; takas edilebilir katman |

Bu projenin ayrı olmasının sebebi: mevcut çalışmada (MamidLabs) ComfyUI, OCR, mmproj gibi başka VRAM
tüketicileri var. Burada **tek sahipli** bir hat kurulur.

## Kesin kurallar

- **STT: Qwen3-ASR-1.7B** (Apache-2.0). Whisper kullanılmaz. Hız öncelikliyse **Qwen3-ASR-0.6B**
  yedeği (aynı mimari/diller, CPU'da daha hızlı).
- **Model: MamidLabs LITE ile aynı.** **Huihui-Qwen3.5 9B Q5_K_M** GGUF'u; MTP başlığı indirmede
  `mtp_inject.py` ile eklenir. Dosyalar zaten MamidLabs kökünde → **yeniden indirme yok**.
- **MTP daima açık.** `--spec-type draft-mtp`; kapatılmaz. Hız + kayıpsız çıktı.
- **GPU yalnızca LLM'e aittir.** STT ve TTS CPU'da; dil modeli yerleşik kalır, boşaltılmaz.

## Teknoloji kararları (özet)

| Konu | Karar |
|---|---|
| Yığın | PowerShell 7 + WinForms |
| Etkileşim | Bas-konuş **ve** sürekli dinleme (ayardan seçilir) |
| STT | **Qwen3-ASR-1.7B** (CPU; hız yedeği 0.6B) |
| LLM | **Huihui-Qwen3.5 9B Q5_K_M** (LITE ile aynı), **MTP daima açık**, GPU'da yerleşik |
| TTS | Takas edilebilir: Chatterbox Multilingual v3 (en gerçekçi) / Piper (hızlı) / SAPI |
| Dil | Türkçe + İngilizce (iki sürüm) |
| Kullanım | Kişisel / kapalı |
| Hedef gecikme | < 1 sn |

Tüm kararlar: [`docs/kararlar.md`](docs/kararlar.md).

## Faz planı

| Faz | İçerik | Durum |
|---|---|---|
| 0 | Kararlar | ✅ |
| 1 | Mimari + gecikme bütçesi | 🔄 |
| 2 | STT (Qwen3-ASR) hattı + < 1 sn ölçümü | ⬜ |
| 3 | LLM (LITE 9B + MTP) + prefix cache | ⬜ |
| 4 | TTS katmanı | ⬜ |
| 5 | WinForms arayüz + PTT/VAD + barge-in | ⬜ |
| 6 | TR/ENG sürümler + paketleme | ⬜ |

**Faz 2 neden ilk?** `<1 sn` hedefinin kaderi STT'de belirlenir; Qwen3-ASR-1.7B'nin CPU hızı
orada ölçülür (1.7B yeterli mi, 0.6B'ye mi inilmeli).

## Dokümanlar

| Yol | İçerik |
|---|---|
| [`docs/mimari.md`](docs/mimari.md) | Mimari, veri akışı, tur dizisi, sorumluluk tablosu, gecikme bütçesi |
| [`docs/faz2-olcum-plani.md`](docs/faz2-olcum-plani.md) | Faz 2: Qwen3-ASR hattı ve `<1 sn` ölçüm planı |
| [`docs/kararlar.md`](docs/kararlar.md) | Karar günlüğü |
| [`AGENTS.md`](AGENTS.md) | Geliştirici/ajan altyapı rehberi |

## Lisans

Kişisel kullanım. (Qwen3-ASR Apache-2.0; LLM Llama/Qwen türevi; Chatterbox MIT.)
