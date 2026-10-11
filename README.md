# mamidChats Chatbot

Gerçek zamanlı, **tamamen yerel** ve yapay zekâ destekli sesli sohbet botu (Windows).

> Bu depo yalnızca **plandır**. Kurulum veya çalışan kod içermez; amaç, üzerine inşa edeceğimiz
> mimariyi ve kararları tek yerde toplamaktır.

## Hedef

Kullanıcı konuşmayı bitirdikten sonra **1 saniye içinde** ilk sesin çıkması.

- **t₀** = kullanıcının son sözcüğü bittiği an
- **t₁** = ilk sesin hoparlörden çıktığı an
- **Hedef:** `t₁ − t₀ < 1000 ms`

Ölçü, metnin ekranda görünmesi değil **sesin başlaması**dır; "canlı sohbet" hissi buna bağlıdır.
Ayrıntılı bütçe: [`docs/mimari.md`](docs/mimari.md).

## Bir paragrafta ürün

Tek bir WinForms penceresinde, kullanıcı mikrofonla konuşur; uygulama konuşmayı yazıya çevirir
(whisper.cpp **large-v3-turbo**), yerel dil modeline verir (**Huihui-Qwen3.5 9B Q5_K_M** — MamidLabs
LITE ile aynı; **MTP daima açık**) ve yanıtı sesli okur (TTS). Tamamı çevrimdışı, hiçbir veri dışarı
çıkmaz. Bas-konuş ve sürekli dinleme (VAD) modları vardır.

## Özet mimari

**Ana kural: GPU'da yalnızca dil modeli çalışır; STT ve TTS CPU'da çalışır.**

```
Mikrofon → VAD/kayıt → whisper.cpp turbo (CPU) → metin
        → Huihui-Qwen3.5 9B (GPU, MTP) → yanıt metni
        → TTS (CPU) → hoparlör
```

| Bileşen | Nerede | Neden |
|---|---|---|
| **Huihui-Qwen3.5 9B Q5_K_M** + MTP | **GPU (8 GB)** | MamidLabs LITE ile **aynı model** (dosyalar zaten diskte); yerleşik kalır, model takası yok |
| whisper.cpp **large-v3-turbo** | **CPU** | GPU'yu LLM'e bırakır; turbo CPU'da gerçek zamanlı (~0,2–0,4 sn) |
| TTS (Piper / XTTS / SAPI) | **CPU** | VRAM'e dokunmaz; takas edilebilir katman |

Bu projenin ayrı olmasının sebebi: mevcut çalışmada (MamidLabs) ComfyUI, OCR, mmproj gibi başka VRAM
tüketicileri var. Burada **tek sahipli** bir hat kurulur — yalnızca `llama-server` ve CPU işçileri.

## Kesin kurallar

- **Model: MamidLabs LITE ile aynı.** **Huihui-Qwen3.5 9B Q5_K_M** GGUF'u kullanılır; MTP/`nextn`
  başlığı indirmede `mtp_inject.py` ile geri eklenir. Dosyalar zaten MamidLabs kökünde mevcut →
  **yeniden indirme yok** (istersen dosya yönü paylaşılır).
- **MTP daima açık.** Yerel dil modeli `--spec-type draft-mtp` ile çalışır; kapatılmaz. Amaç hem hız
  hem kayıpsız çıktı. (GGUF'un MTP katmanı taşıdığı `Test-GgufHasMtp` ile doğrulanır.)
- **STT için turbo.** Sohbet doğruluğu için `large-v3-turbo` yeterli; `large-v3` yalnızca gerekirse
  "yüksek doğruluk" modu olarak düşünülür (varsayılan değil).
- **GPU yalnızca LLM'e aittir.** STT ve TTS CPU'da çalışır; dil modeli yerleşik kalır, boşaltılmaz.

## Teknoloji kararları (özet)

| Konu | Karar |
|---|---|
| Yığın | PowerShell 7 + WinForms (MamidLabs ile aynı desen) |
| Etkileşim | Bas-konuş **ve** sürekli dinleme (ayardan seçilir) |
| STT | whisper.cpp **large-v3-turbo** (CPU'da, sohbet için) |
| LLM | **Huihui-Qwen3.5 9B Q5_K_M** (MamidLabs LITE ile aynı), **MTP daima açık**, GPU'da yerleşik |
| TTS | Takas edilebilir: Piper (varsayılan) / XTTS-v2 (yüksek kalite) / SAPI |
| Dil | Türkçe + İngilizce (iki sürüm) |
| Kullanım | Kişisel / kapalı (ticari dağıtım yok) |
| Hedef gecikme | < 1 sn |

Tüm kararlar ve gerekçeleri: [`docs/kararlar.md`](docs/kararlar.md).

## Faz planı

| Faz | İçerik | Durum |
|---|---|---|
| 0 | Kararlar | ✅ |
| 1 | Mimari + gecikme bütçesi | 🔄 (bu depo) |
| 2 | STT (turbo) hattı prototipi + < 1 sn ölçümü | ⬜ |
| 3 | LLM (LITE 9B + MTP) + prefix cache | ⬜ |
| 4 | TTS katmanı (takas edilebilir) | ⬜ |
| 5 | WinForms arayüz + PTT/VAD + barge-in | ⬜ |
| 6 | TR/ENG sürümler + paketleme | ⬜ |

**Faz 2 neden ilk?** < 1 sn hedefinin kaderi STT'de belirlenir; o ölçülmeden UI/TTS'e yatırım riskli.

## Dokümanlar

| Yol | İçerik |
|---|---|
| [`docs/mimari.md`](docs/mimari.md) | Mimari, veri akışı, tur dizisi, sorumluluk tablosu, gecikme bütçesi, STT/TTS analizi |
| [`docs/faz2-olcum-plani.md`](docs/faz2-olcum-plani.md) | Faz 2: STT hattı ve `<1 sn` ölçüm planı |
| [`docs/kararlar.md`](docs/kararlar.md) | Karar günlüğü (ne, neden, alternatifler) |
| [`AGENTS.md`](AGENTS.md) | Geliştirici ve yapay zekâ ajanları için altyapı rehberi |

## Lisans

Kişisel kullanım. (Not: yüksek kalite TTS adayı XTTS-v2 ticari kullanıma kapalıdır — bkz.
`docs/mimari.md`; bu proje kişisel olduğu için sorun değil.)
