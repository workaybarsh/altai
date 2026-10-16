# TTS kıyaslaması · Türkçe (Chatterbox merkezli, Fish hariç)

Bu belge, Türkçe TTS için **Chatterbox** ile diğer modern motorları karşılaştırır. **Fish S2 Pro
kapsam dışıdır** (karar #15 — projeye girmiyor).

## 1. Kaynak ve kapsam

| Alan | Değer |
|---|---|
| Birincil kaynak | **arXiv:2610.06057v1** — *"A Comprehensive Objective Evaluation of Modern Text-to-Speech for Turkish"* (Sestek, 05 Eki 2026) |
| Yöntem | 100 kısa + 100 orta + 100 uzun Türkçe cümle; **18 objektif metrik** + doğal ("gold") referans çıpası |
| Karşılaştırılan sistemler | **Chatterbox** (zero-shot), **CosyVoice** (finetuned, raw text), **OmniVoice** (finetuned + zero-shot), **VoxCPM2** (zero-shot), **VITS** (finetuned, klon değil) |
| Çıkarılan | **Fish S2 Pro** |
| Kod/sonuç | `github.com/EmreOzkose/tr-tts-eval` |

> **Konfig notu:** Chatterbox ve VoxCPM2 yalnızca **zero-shot**; CosyVoice/OmniVoice **finetuned**;
> VITS **finetuned** ve klonlama yapmaz. VoxCPM2 sütunu **çok dilli taban** modeldir; projenin adayı
> **Trendyol-TTS = VoxCPM2 + Türkçe LoRA** (finetuned) olduğundan Türkçede tabandan **daha iyi**
> olması beklenir.

## 2. Genel ortalamalar (tüm test kümesi)

> Her satırda en iyi **sentetik** sistem kalın; Gold yalnızca çıpadır, yarışmacı değildir.

| Metrik (yön) | Chatterbox | CosyVoice | OmniVoice (ZS) | **VoxCPM2** | VITS | Gold |
|---|---|---|---|---|---|---|
| **speaker-similarity ↑** | 0,873 | 0,878 | 0,870 | **0,881** | 0,875 | 0,894 |
| UTMOS-v2 (doğallık) ↑ | 3,092 | **3,441** | 3,105 | 2,886 | 3,064 | 3,079 |
| DNSMOS-Pro ↑ | 3,564 | 3,770 | 3,808 | 3,902 | **4,225** | 3,601 |
| SQUIM SI-SDR (anlaşılırlık) ↑ | 24,94 | 25,74 | **28,52** | 27,05 | 25,21 | 24,46 |
| SQUIM STOI ↑ | 3,762 | 3,753 | **3,926** | 3,788 | 3,690 | 3,639 |
| WhisQA ↑ | 4,341 | **4,720** | 4,448 | 4,575 | 4,515 | 4,331 |
| SCOREQ ↑ | 3,697 | **4,063** | 4,059 | 3,907 | 3,740 | 3,782 |
| NatScore ↑ | −1,447 | −1,233 | −1,128 | **−0,917** | −1,616 | −1,384 |
| Brouhaha ↑ | 50,13 | 60,25 | 58,07 | **62,47** | 59,51 | 55,31 |
| AudioBox-PQ ↑ | 7,643 | 7,793 | **7,831** | 7,793 | 7,654 | 7,657 |
| TTSDS ↑ | 77,01 | **79,74** | 78,58 | 79,16 | 78,28 | 77,86 |

**Okuma:** Metrik ailelerine göre liderler ayrışıyor —
**VITS** DNSMOS-Pro, **OmniVoice(ZS)** anlaşılırlık/sinyal (SQUIM), **CosyVoice** doğallık/dağılım
(UTMOS/WhisQA/SCOREQ/TTSDS), **VoxCPM2** konuşmacı-benzerliği + NatScore + Brouhaha.
👉 **Chatterbox hiçbir metriği kazanmıyor.**

## 3. Cümle uzunluğu — sesli asistan için kritik (**kısa** cümleler)

Sesli asistan tipik olarak **kısa** yanıt üretir (0–50 karakter). Paper'ın en çarpıcı bulgusu:
**Chatterbox kısa cümlede çöküyor.**

| Kısa cümle (0–50 kr.) | Chatterbox | CosyVoice | OmniVoice (ZS) | VoxCPM2 | Gold |
|---|---|---|---|---|---|
| speaker-similarity ↑ | 0,825 | 0,814 | 0,818 | **0,830** | 0,827 |
| SQUIM SI-SDR ↑ | **20,36** ⬅ en kötü | 26,03 | **28,54** | 26,91 | 25,80 |
| DNSMOS-Pro ↑ | **3,335** ⬅ en kötü | 3,621 | 3,784 | **3,805** | 3,412 |
| WhisQA ↑ | **3,607** ⬅ en kötü | 4,546 | 4,118 | 4,307 | 4,058 |
| UTMOS-v2 ↑ | 2,766 | **3,350** | 2,927 | 2,776 | 2,909 |
| NatScore ↑ | **−2,221** ⬅ en kötü | −1,250 | −1,675 | −1,556 | −1,501 |

> Paper: *"Deployments dominated by short prompts (voice assistants, IVR, command responses) should
> weight the short-group results far more heavily than the overall averages."*
> CosyVoice/OmniVoice/VoxCPM2 uzunluk dayanıklı; **Chatterbox yalnızca orta/uzunda toparlıyor.**

## 4. Uzun-form kararlılık (kimlik + doğallık sürüklenmesi)

| Sistem | Kimlik std ↓ | Kimlik drift → 0 | Kimlik Δilk-son → 0 | Doğallık drift | Doğallık Δilk-son |
|---|---|---|---|---|---|
| **Chatterbox (ZS)** | 0,0325 | −0,0391 | **−0,0613** (en kötü) | **−0,149** | **−0,321** (en kötü) |
| **CosyVoice** | **0,0212** | **−0,0077** | **−0,0094** | −0,041 | −0,067 |
| OmniVoice (ZS) | 0,0282 | −0,0184 | −0,0276 | −0,063 | −0,090 |
| **VoxCPM2 (ZS)** | 0,0233 | −0,0115 | **−0,0003** (≈sıfır) | −0,001 | −0,039 |
| VITS | 0,0226 | −0,0125 | −0,0175 | −0,118 | −0,147 |

**Okuma:** Kimlikte en kararlı **CosyVoice** ve **VITS**; **VoxCPM2** neredeyse sıfır kimlik kayması
(uzun metinde ideal). **Chatterbox** her iki eksende de en kararsız (doğallık belirgin **düşüyor**).

## 5. Projenin kendi ölçümleri (elle, bu makine)

| Motor | VRAM | RTF | TR anlaşılırlık (geri-çevirim WER) |
|---|---|---|---|
| **Trendyol-TTS** (=VoxCPM2 + TR LoRA) | ~5,3–5,6 GB | ~3,0 (gerçek zamandan ~3× yavaş) | ~0,08 (temiz örnek) |
| Chatterbox | ~2–3 GB (belgelenen) | GPU'da hızlı | **zayıf** (projede gözlendi) |
| SAPI | 0 (CPU) | çok hızlı | ❌ bu makinede **Türkçe ses yok** (yalnız Zira en-US) |

## 6. Sonuç ve projeye etkisi

| İhtiyaç | Kazanan (kanıta göre) | Chatterbox |
|---|---|---|
| Doğallık / algılanan kalite | **CosyVoice** | ✗ (hiçbir metriği kazanmıyor) |
| **Konuşmacı benzerliği / klon** | **VoxCPM2** | ✗ |
| Anlaşılırlık / sinyal temizliği | **OmniVoice (ZS)** / VITS | ✗ |
| **Kısa cümle (sesli asistan)** | CosyVoice / OmniVoice / VoxCPM2 | ✗ **çöküyor** |
| Uzun-form kimlik kararlılığı | **VoxCPM2** (≈0 kayma) | ✗ |
| Uzun-form doğallık kararlılığı | **CosyVoice** | ✗ |

**Kararlarımıza yansıması:**
1. **Türkçe birincil motor olarak Chatterbox elenir** — hiçbir metriği kazanmıyor, kısa cümlede
   çöküyor, doğallığı zamanla düşüyor. (Bulgumuzu bağımsız olarak doğruluyor.)
2. **VoxCPM2 ailesi (→ Trendyol-TTS) Türkçe için en güçlü aday** (klon/benzerlik + NatScore + uzun-form
   kararlılık). Ancak **canlı `<1 sn`** için hâlâ ağır (RTF ~3, ~5,6 GB VRAM) → çevrimdışı motor (karar #16).
3. **CosyVoice** doğallıkta en iyi ve uzunluk-dayanıklı → **canlı TR için birinci yedek aday** (hız/VRAM
   ölçülmeli). **OmniVoice(ZS)** anlaşılırlık için ilgi çekici (Türkçe klon adayı olarak izlenebilir).
4. VITS klonlamaz; ses-odaklı projede yalnızca referans noktası.

> ⚠️ Bu kaynak tamamen **objektif metrik** tabanlıdır (tek Türkçe test kümesi, sınırlı konuşmacı).
> Mutlak değerler gold'a göre okunmalı; **nihai yargı için kulak (MOS/tercih) testi** şarttır.

## 7. Kaynakça

- Özköse, Y. E., Kahraman, A., Haznedaroğlu, A. (Sestek). *A Comprehensive Objective Evaluation of
  Modern Text-to-Speech for Turkish Using Speech Quality Assessment Models.* **arXiv:2610.06057v1**, 2026.
