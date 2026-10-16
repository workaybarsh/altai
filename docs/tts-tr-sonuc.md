# TTS-TR · Trendyol-TTS değerlendirmesi (2026-10-16)

Bu belge, Türkçe TTS adayı **Trendyol-TTS**'in (`openbmb/VoxCPM2` + Türkçe LoRA, **MIT**, ~2B)
ölçüm ve kalite sonuçlarını toplar. Karar: [`kararlar.md`](kararlar.md) → **#16**.

> ⚠️ Ölçüm, proje hedef donanımı değil, geliştirme makinesinde (RTX 5060 Ti **16 GB**) yapıldı.
> Hedef 8 GB kartta VRAM durumu daha da kritiktir.

## 1. Ortam

| Alan | Değer |
|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti (16.283 MiB) |
| Runtime | `%TEMP%\opencode\tts-venv` — `voxcpm 2.0.3`, `torch 2.11.0+cu128` |
| Model | `Trendyol/Trendyol-TTS` (HF önbellekte; diskte ~4,8 GB) |
| Üretim ayarı | `cfg_value=2.0`, `inference_timesteps=16`, `optimize=True` (model kartı önerisi) |
| Çıkış | 48 kHz mono WAV |

## 2. Kaynak kullanımı

| Metrik | Değer | Not |
|---|---|---|
| **VRAM (yükleme sonrası alloc)** | **5.248 MiB (~5,1 GB)** | `torch.cuda.memory_allocated` |
| **VRAM (peak alloc)** | **5.458 MiB (~5,3 GB)** | tüm üretim boyunca tepe |
| **VRAM (peak reserved)** | **5.688 MiB (~5,6 GB)** | CUDA ayırıcı rezervi |
| nvidia-smi tepe (masaüstü 510 MiB dahil) | 6.223 MiB | bağımsız doğrulama |
| Yükleme (sıcak disk) | **17,5 sn** | soğuk diskte ilk yükleme **575 sn (~9,6 dk)** |
| RTF | **2,9 – 3,3** | gerçek zamandan **~3× yavaş** |

> **Kritik:** ~5,6 GB VRAM, projenin "GPU yalnızca LLM'e ait" kuralıyla çelişir. Yerleşik 9B
> LLM (~6,6 GB) ile birlikte ≈12 GB gerekir → **8 GB hedef kartına sığmaz**. RTF ~3 ise `<1 sn`
> hedefini (TTS ilk ses ≤150 ms) doğrudan yer.

## 3. Türkçe anlaşılırlığı (geri-çevirim)

Yöntem: üretilen ses, **projenin STT'siyle aynı aileden** `openai/whisper-large-v3-turbo` ile tekrar
yazıya çevrilip referans metinle WER (kelime hata oranı) karşılaştırıldı. Diakritikler katlanarak
adil kıyaslandı (referans ASCII, model doğru Türkçe üretti).

| # | Referans | Geri-çevirim (Whisper) | WER |
|---|---|---|---|
| 1 | Merhaba! Ben tamamen yerel calisan bir sesli asistanim. Bugun size nasil yardimci olabilirim? | Merhaba, ben tamamen yerel calisan bir **sessi** asistanım. Bugün size nasil yardımcı olabilirim. | **0,08** |
| 2 | Saat su anda on dort otuz. Istanbul'da hava bugun cok guzel ve gunesli. | Saat **şoğanda** 14.30 İstanbul'da hava bugün çok güzel ve güneşli. | **~0,43**\* |

\* Örnek-2'de sayı `14.30` olarak (rakam) yazıldığı için WER şişti; ayrıca **"şu anda" → "şoğanda"**
şeklinde gerçek bir telaffuz bozulması var. Örnekler: `logs\tts\trendyol-tr.wav`,
`logs\tts\trendyol-tr2.wav`.

**Yorum:** Genelde **anlaşılır** ve doğru Türkçe (diakritikler dahil), ancak tek tek sözcüklerde
telaffuz bozulmaları olabiliyor. Kulakla doğallık değerlendirmesi kullanıcıya bırakılır.

## 4. Sonuç / karar

| Boyut | Değerlendirme |
|---|---|
| Türkçe kalite | ✅ Anlaşılır (WER ~0,08 temiz örnekte); ara sıra telaffuz hatası |
| Lisans | ✅ MIT |
| VRAM | ❌ ~5,6 GB → "GPU yalnız LLM" kuralı ihlali; 8 GB karta LLM ile sığmaz |
| Gecikme | ❌ RTF ~3 → `<1 sn` hedefiyle uyumsuz |
| **Hüküm** | **Canlı `<1 sn` hattının varsayılanı DEĞİL.** `tts-tools.py --backend voxcpm` olarak **çevrimdışı/yüksek-kalite TR motoru** eklendi (karar #16) |

## 5. Yeniden üretme

```powershell
# Üretim (venv gerekir: voxcpm + torch-cu128 + soundfile)
python scripts\tts-trendyol-test.py                 # -> logs\tts\trendyol-tr.wav
python agent\tts-tools.py --backend voxcpm --text "Merhaba dunya" --out out.wav

# Geri-çevirim (anlaşılırlık) — Whisper gerekir
python tts-roundtrip.py --wav logs\tts\trendyol-tr.wav --ref "<referans metin>"
```

> Kurulum: `pip install voxcpm soundfile` (CUDA'lı torch ayrıca). Model ilk seferde Hugging Face'ten
> indirilir (~4,8 GB).
