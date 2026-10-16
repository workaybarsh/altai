# Faz 2 · whisper.cpp hattı ve `<1 sn` ölçüm planı

## 1. Amaç

`<1 sn` hedefinin **STT ayağını** gerçek donanımda ölçmek ve şu soruyu veriyle yanıtlamak:

> CPU'da **whisper.cpp `large-v3-turbo`** sohbet cümlesini yeterince hızlı yazıya çeviriyor mu,
> yoksa **`medium`** ya da **`small`**'a mı inilmeli (ya da parça paralelliği mi artırılmalı)?

## 2. Neden Faz 2 ilk

LLM (MTP ile hızlı) ve TTS hızlıdır; asıl değişken **STT**'dir. whisper.cpp `large-v3-turbo` CPU'da
tipik cümlede ~0,2–0,4 sn olsa da uzun cümlelerde `<1 sn` bütçesini zorlar; bu, hedefin en riskli
halkasıdır.

## 3. Kapsam

- **İçinde:** whisper.cpp (`large-v3-turbo` / `medium` / `small`), çevrimdışı (segmented) ve parçalı
  modlar, VAD, bağımlılıksız kayıt, ölçüm koşum takımı, rapor.
- **Dışında:** LLM, TTS, arayüz.

## 4. Hipotez

**`large-v3-turbo`** CPU'da tipik sohbet cümlesini **~0,2–0,4 sn**'de çevirir; **`medium`** benzer
bantta kalabilir, **`small`** ise **<300 ms** verir. VAD ile bölütleme algılanan gecikmeyi düşürür.

## 5. Ölçüm düzeni

| Alan | Değer |
|---|---|
| Donanım | Hedef: 8 GB VRAM makine, 16 GB RAM |
| Dil modeli | Kapalı (GPU boş; ölçülen yalnız ASR) |
| Modeller | **`large-v3-turbo`** (birincil), **`medium`**, **`small`** (karşılaştırma) |
| Quant | Q5 / Q8 (boyut-hız-doğruluk dengesi) |
| Mod | segmented (offline) vs **parçalı / akış benzeri** |
| Thread | 4 / 6 / 8 / fiziksel çekirdek (ölçekleme) |
| VAD | Silero açık / kapalı |
| Girdi | Kısa (~2 sn), orta (~5 sn), uzun (~10 sn) × TR/EN |
| Tekrar | N = 10; medyan + p95 |

## 6. Ölçülecek metrikler

| Metrik | Tanım | Hedef |
|---|---|---|
| ASR gecikmesi | ses hazır → metin hazır (segment sonu) | ≤ 400 ms (turbo); ölç (tümü) |
| RTF | işlem / ses süresi | < 1,0 |
| VAD endpoint | son sözcük → "bitti" | ≤ 200 ms |
| Doğruluk | WER (TR), elle referans | Sohbet için kabul edilebilir |
| Thread ölçekleme | thread → hız eğrisi | Doygunluk noktasını bul |
| Bellek | süreç tepe RAM | Makul |

## 7. Senaryolar

1. **Bas-konuş (PTT)** — kısa/orta/uzun, sessiz ortam.
2. **Sürekli dinleme (VAD)** — endpoint gecikmesi.
3. **Gürültülü ortam** — gerçek ortam dayanıklılığı.
4. **turbo vs medium vs small** — hız/doğruluk dengesi.
5. **Thread sayısı** — fiziksel çekirdek ölçeklemesi.

## 8. Başarı kriterleri

- [ ] PTT'de orta uzunlukta cümlede **ASR ≤ 400 ms** (`large-v3-turbo`).
- [ ] VAD endpoint ≤ 200 ms; cümle kesme yok.
- [ ] Türkçe WER sohbet için kabul edilebilir.
- [ ] Bellek, GPU'daki LLM ile birlikte çalışmaya izin veriyor.

**Karar kapısı:** `large-v3-turbo` hedefi tutarsa kalır; tutmazsa **`medium`/`small`'a in** veya
parça paralelliğini/VAD bölütlemeyi ayarla.

## 9. Çıktı

- `docs/faz2-sonuc.md`: ölçüm tabloları + WER notları.
- `docs/kararlar.md`: "turbo mu medium/small mu, akış gerekli mi" kararı.

## 10. Riskler

- **CPU farkı:** Laptop CPU'su sonuçları değiştirir.
- **VAD eşiği:** Agresif → kesme, yavaş → gecikme.
- **Gürültü:** Gerçek ortam testi şart.
- **Thread aşırılığı:** Çok thread hızı düşürebilir; ölçümle ayarla.

## 11. Sonraki faz

Faz 2 geçince **Faz 3** (LLM 9B i1-Q5_K_M + MTP + prefix cache) → **Faz 4** (TTS) → **Faz 5**
(arayüz + barge-in).
