# Faz 2 · Qwen3-ASR hattı ve `<1 sn` ölçüm planı

## 1. Amaç

`<1 sn` hedefinin **STT ayağını** gerçek donanımda ölçmek ve şu soruyu veriyle yanıtlamak:

> CPU'da **Qwen3-ASR-1.7B** sohbet cümlesini yeterince hızlı yazıya çeviriyor mu, yoksa
> **Qwen3-ASR-0.6B**'ye mi inilmeli (ya da akış penceresi mi daraltılmalı)?

## 2. Neden Faz 2 ilk

LLM (MTP ile ~97 tok/s) ve TTS hızlıdır; asıl değişken **ASR**'dir. Özellikle Qwen3-ASR-1.7B CPU'da
gerçek zamanın ~4 katı olduğundan bu, hedefin en riskli halkasıdır.

## 3. Kapsam

- **İçinde:** Qwen3-ASR-1.7B ve 0.6B çıkarımı, akışlı/segmented modlar, VAD, bağımlılıksız kayıt,
  ölçüm koşum takımı, rapor.
- **Dışında:** LLM, TTS, arayüz.

## 4. Hipotez

**1.7B** CPU'da tipik sohbet cümlesini **~0,7–1,2 sn**'de çevirir (sınıra yakın); **0.6B** ise
**<400 ms** verir. Akışlı mod algılanan gecikmeyi düşürür.

## 5. Ölçüm düzeni

| Alan | Değer |
|---|---|
| Donanım | Hedef: 8 GB VRAM makine, 16 GB RAM |
| Dil modeli | Kapalı (GPU boş; ölçülen yalnız ASR) |
| Modeller | **Qwen3-ASR-1.7B** (birincil), **0.6B** (karşılaştırma) |
| Quant | Q4 / Q8 / fp16 (boyut-hız-doğruluk dengesi) |
| Mod | segmented (offline) vs **streaming** (`--stream`) |
| VAD | Silero açık / kapalı |
| Girdi | Kısa (~2 sn), orta (~5 sn), uzun (~10 sn) × TR/EN |
| Tekrar | N = 10; medyan + p95 |

## 6. Ölçülecek metrikler

| Metrik | Tanım | Hedef |
|---|---|---|
| ASR gecikmesi | ses hazır → metin hazır (segment sonu) | ≤ 400 ms (0.6B) / ölç (1.7B) |
| İlk kısmi metin | akışta ilk token | < 300 ms (algılanan) |
| RTF | işlem / ses süresi | < 1,0 |
| VAD endpoint | son sözcük → "bitti" | ≤ 200 ms |
| Doğruluk | WER (TR), elle referans | Sohbet için kabul edilebilir |
| Bellek | süreç tepe RAM | Makul |

## 7. Senaryolar

1. **Bas-konuş (PTT)** — kısa/orta/uzun, sessiz ortam.
2. **Sürekli dinleme (VAD)** — endpoint gecikmesi.
3. **Gürültülü ortam** — Qwen3-ASR'ın iddia ettiği gürültü dayanıklılığı.
4. **1.7B vs 0.6B vs quant** — hız/doğruluk dengesi.
5. **Akışlı vs segmented** — algılanan gecikme farkı.

## 8. Başarı kriterleri

- [ ] PTT'de orta uzunlukta cümlede **ASR ≤ 400 ms** (0.6B) — veya 1.7B akışla kabul edilebilir.
- [ ] VAD endpoint ≤ 200 ms; cümle kesme yok.
- [ ] Türkçe WER sohbet için kabul edilebilir.
- [ ] Bellek, GPU'daki LLM ile birlikte çalışmaya izin veriyor.

**Karar kapısı:** 1.7B hedefi tutarsa kalır; tutmazsa **0.6B'ye in** veya akış penceresini daralt.

## 9. Çıktı

- `docs/faz2-sonuc.md`: ölçüm tabloları + WER notları.
- `docs/kararlar.md`: "1.7B mi 0.6B mi, akış gerekli mi" kararı.

## 10. Riskler

- **CPU farkı:** Laptop CPU'su sonuçları değiştirir.
- **VAD eşiği:** Agresif → kesme, yavaş → gecikme.
- **Gürültü:** Gerçek ortam testi şart.

## 11. Sonraki faz

Faz 2 geçince **Faz 3** (LLM 9B + MTP + prefix cache) → **Faz 4** (TTS) → **Faz 5** (arayüz + barge-in).
