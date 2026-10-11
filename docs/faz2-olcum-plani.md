# Faz 2 · STT hattı prototipi ve `<1 sn` ölçüm planı

## 1. Amaç

`<1 sn` hedefinin **STT ayağının** gerçek donanımda karşılanıp karşılanmadığını ölçmek ve şu soruyu
**veriyle** yanıtlamak:

> `large-v3-turbo` CPU'da sohbet cümlesini yeterince hızlı yazıya çeviriyor mu, yoksa akışlı STT'ye
> mi geçmek gerekiyor?

## 2. Neden Faz 2 ilk

Hedefin kaderi burada belirlenir. LLM (MTP ile ~97 tok/s) ve TTS (Piper, anlık) hızlıdır; **asıl
değişken STT**'dir. O ölçülmeden arayüz/TTS'e yatırım yapmak risklidir.

## 3. Kapsam

- **İçinde:** whisper.cpp + `large-v3-turbo`, Silero VAD, bağımlılıksız ses yakalama (winmm), ölçüm
  koşum takımı, sonuç raporu.
- **Dışında:** LLM istemi, TTS, WinForms arayüz (sonraki fazlar).

## 4. Hipotez

`large-v3-turbo` (q5_0) CPU'da tipik bir sohbet cümlesini **< 400 ms**'de yazıya çevirir; bu,
`<1 sn` bütçesine rahat sığar ve akışlı STT'ye gerek kalmaz.

## 5. Ölçüm düzeni

| Alan | Değer |
|---|---|
| Donanım | Hedef: 8 GB VRAM makine (ör. RTX 4060 Laptop), 16 GB RAM |
| Dil modeli | Kapalı (GPU boş; ölçülen yalnız STT) |
| Modeller | `large-v3-turbo` q5_0 (**varsayılan**), karşılaştırma: `large-v3`, `base` |
| VAD | Silero açık / kapalı (iki koşul) |
| Girdi | Sabit test seti: kısa (~2 sn), orta (~5 sn), uzun (~10 sn) × TR/EN |
| Tekrar | Her senaryo **N = 10**; medyan + p95 raporlanır |
| Ses | 16 kHz mono WAV (whisper girdisi) |

## 6. Ölçülecek metrikler

| Metrik | Tanım | Hedef |
|---|---|---|
| STT gecikmesi | WAV hazır → metin hazır | ≤ 400 ms (kısa/orta) |
| RTF | işlem süresi / ses süresi | < 1,0 (gerçek zamanlı) |
| VAD endpoint | son sözcük → "bitti" kararı | ≤ 200 ms |
| Doğruluk | WER (elle referans) | Sohbet için kabul edilebilir |
| Bellek | süreç tepe RAM | Makul (paralel LLM'e yer bırakmalı) |

## 7. Senaryolar

1. **Bas-konuş (PTT)** — kısa / orta / uzun cümle, sessiz ortam. (Endpoint = 0)
2. **Sürekli dinleme (VAD)** — aynı cümleler; endpoint gecikmesi ölçülür.
3. **Gürültülü ortam** — arka plan sesi; VAD ve doğruluk etkisi.
4. **Model karşılaştırması** — turbo vs large-v3 vs base (hız/doğruluk dengesi).

## 8. Başarı kriterleri

- [ ] PTT + turbo: orta uzunlukta cümlede **STT ≤ 400 ms** (medyan).
- [ ] VAD endpoint **≤ 200 ms**; gereksiz cümle kesme yok.
- [ ] Turbo'nun WER'i sohbet için kabul edilebilir (large-v3'e göre belirgin kayıp yok).
- [ ] Bellek, GPU'daki LLM ile birlikte çalışmaya izin veriyor.

**Karar kapısı:** Hepsi geçerse → turbo **final** yeterli, akışlı STT **gerekmez** (mimari basitleşir).
En az biri düşerse → akışlı STT (kısmi metin + spekülatif başlatma) tasarıma eklenir.

## 9. Çıktı

- `docs/faz2-sonuc.md`: ölçüm sonuçları (medyan/p95, grafik veya tablo) + WER notları.
- `docs/kararlar.md`: "turbo final yeterli mi / akışlı STT gerekli mi" kararı eklenir.

## 10. Riskler

- **CPU farkı:** Hedef makinenin CPU'su laptop sınıfı olabilir; sonuçlar donanıma bağlı.
- **VAD eşiği:** Çok agresif → cümle kesme; çok yavaş → gecikme. Ayarlanabilir bırakılır.
- **Gürültü:** Gerçek ortam testleri gerekir; laboratuvar sonucu iyimser olabilir.

## 11. Sonraki faz (özet)

Faz 2 geçince **Faz 3** (LLM 9B + MTP + prefix cache ile ilk-token ölçümü) → **Faz 4** (TTS) →
**Faz 5** (arayüz + barge-in).
