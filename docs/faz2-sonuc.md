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

## Yapılacak (hedef donanım, `large-v3-turbo`)

- [ ] `large-v3-turbo` ile aynı ölçüm (kısa/orta/uzun × TR/EN, N=10, medyan + p95)
- [ ] **Thread ölçekleme** (4/6/8/fiziksel çekirdek) — doygunluk noktası
- [ ] Türkçe WER (elle referans)
- [ ] VAD endpoint gecikmesi
- [ ] `medium`/`small` karşılaştırması (gerekirse)
- [ ] Nihai karar → [`kararlar.md`](kararlar.md)
