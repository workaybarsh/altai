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
| Chatterbox | **~3,3 GB** (ölçüm) | **RTF ~1,1** (ölçüm) | ✅ iyi (tr-fix+respell ile) |
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

## 8. Kaynak kullanımı (araştırma; yerel çalıştırma yapılmadı)

> Bu bölüm **yayınlanmış kaynaklardan** derlenmiştir (henüz kendi donanımımızda ölçülmedi). Amaç:
> motorların **parametre / VRAM / hız / lisans** profillerini karşılaştırmak.

| Motor | Parametre | VRAM (çıkarım) | RTF (üst düzey GPU) | İlk ses (streaming) | TR zero-shot | Lisans |
|---|---|---|---|---|---|---|
| **Chatterbox Multilingual v3** | 0,5B | **~2 GB** (min) – ~4 GB | **~0,05–0,2** | var (chunked) | ✅ (ama diakritik hatası) | **MIT** |
| **VoxCPM2** (→ Trendyol-TTS) | 2B (2,3B) | ~5 (bf16) – ~8 GB | ~0,30 (4090) / ~0,13 Nano-vLLM | var (chunk) | ✅ | Apache-2.0 |
| **CosyVoice 1** (CosyVoice-300M) | 0,3B | ~2–6 GB (kaynak) | eski/orta (2024-07) | ~150 ms | ❌ TR yok (5 dil: zh/en/ja/ko/yue) | Apache-2.0 |
| **CosyVoice 2** | 0,5B | ~4–8 GB (kaynak) | iyi (streaming) | **~150 ms** | ❌ TR yok (zh/en/ja/ko/yue) → finetune | Apache-2.0 |
| **CosyVoice 3** (Fun-CosyVoice3-0.5B) | 0,5B (1,5B **açık değil**) | ~4–10 GB (kaynak) | **SOTA (0,5B'de)** | **~150 ms** | ❌ **TR yok** (9 dil: zh/en/ja/ko/de/es/fr/it/ru) → finetune | Apache-2.0 |
| **OmniVoice** | 0,81B | **~2,3 GB** (fp16) | **~0,04** (L40S) / ~0,025 (H100) | NAR (batch) | ✅ (600+ dil) | Apache-2.0 |

Kaynaklar: VoxCPM2 README/teknik rapor (arXiv:2606.06928) + voxcpm.readthedocs; OmniVoice makalesi
(arXiv:2604.00688) + k2-fsa/OmniVoice + L40S/Jetson ölçümleri; CosyVoice2 (arXiv:2412.10117) +
fun-audiollm; Chatterbox (Resemble AI, GitHub/HF). VRAM rakamları model kartları/bildirimlerle
değişir; **kesin değer kendi kartımızda ölçülmeli**.

**Chatterbox öne çıkıyor:** en küçük (0,5B), **en az VRAM (~2 GB)**, MIT, ve RTF <1 (gerçek zamandan
hızlı). Bizim gözlemimizle tutarlı: **kalite iyi**, tek sorun Türkçe karakterler.

**CosyVoice 3 (2025-05, arXiv:2505.17589):** 0,5B açık (**1,5B yalnız makalede — ağırlık yok**),
Apache-2.0, **native streaming ~150 ms**, 25 Hz, TensorRT-LLM ile ~4×. 0,5B için SOTA kalite
(test-zh CER 1,21 / test-en WER 2,24). **Ama resmî diller 9 tane** (zh/en/ja/ko/de/es/fr/it/ru + 18
Çince diyalekt) → **Türkçe YOK** (GitHub **#1904** ile talep ediliyor). TR için **finetune şart**;
Sestek benchmark'ı da CosyVoice'u **finetune** ederek TR'de doğallık lideri yapmıştı. Yani
**zero-shot TR motoru değil**, ama "TR için finetune edilecek en güçlü aday".

### 8.1 VoxCPM2 RTF uyumsuzluğu (önemli açık soru)

| Kaynak | RTF |
|---|---|
| Resmî (RTX 4090, 10 adım, torch.compile) | ~0,30 |
| **Bizim ölçüm (RTX 5060 Ti, 16 adım, `optimize=True`)** | **~3,0** (10× yavaş) |

Muhtemel nedenler: (a) 16 adım vs 10 adım (~1,6×); (b) **Windows/sm_120'de `torch.compile`/Triton
devreye girmemiş olabilir** (VoxCPM FAQ), saf eager moda düşme; (c) 5060 Ti, 4090'dan yavaş. Yani
**bizim RTF ~3 ölçümü muhtemelen iyimser değil, kötümser**; `inference_timesteps=10` + derlemenin
çalıştığı doğrulanarak **yeniden ölçülmeli**.

## 9. Chatterbox Türkçe sorunu ve çözümü

**Sorun (kanıtlı):** Chatterbox çok dilli tokenizer'ı Türkçeyi **grafem** olarak işler; `ç, ş, ü, ğ,
ö` (ve `ı`) ya atlanıyor ya yanlış seslendiriliyor — tam kullanıcının gözlemi ("bugün→bugun",
"nasıl→nasil"). Resmî kayıtlar: resemble-ai/chatterbox **#261**, HF **discussion #33**
("Turkish characters skipped"), ve #550 (fonem/IPA girişi talep ediliyor — henüz yok).

**Neden oluyor:** referans ses Türkçe değilse + tokenizer diakritikleri tanımıyorsa harfler düşüyor,
vurgu yanlış yere kayıyor. Türkçe'nin **sondan eklemeli** yapısı ve telaffuz kuralları (yumuşak ğ,
noktasız ı, ünlü uyumu) grafem modelinde bozuluyor.

**Kök neden (kod düzeyinde, doğrulandı):** `chatterbox` çok dilli tokenizer'ı
(`MTLTokenizer.preprocess_text`) metne **her zaman `NFKD`** uygular; `generate()` bunu
`nfkd_normalize=False` ile **kapatmaz**. NFKD, `ş/ğ/ü/ö/ç`'yi *taban harf + birleşen işaret*e ayırır
(`ş`→`s`+U+0327, `ü`→`u`+U+0308). Sözlükte bu birleşen işaretler yoksa **diakritik kaybolur**
(`ş`→`s`, `ü`→`u`). Ayrıca `lower()` Türkçe-duyarsızdır (`I`→`i`, `İ`→`i`+nokta). Dış kayıt:
`jamiepine/voicebox` **#846** — *"Incorrect pronunciation of Turkish vowels (ı, ö, ü)"*.

**Uygulanan yama (offline, test edildi):** `agent/tts-tools.py` → `install_tr_tokenizer_fix()` +
`tr_lower()`. `--backend chatterbox --lang tr --chatterbox-tr-fix` ile TR için **NFKD kapatılır**
(NFC/precomposed korunur) ve **Türkçe küçültme** uygulanır; diğer diller etkilenmez.
`python -m pytest -q` → **19 test** (2 yeni). ⏳ Etki (ses) **GPU boşken** ölçülecek.

> 📌 Aynı kaynakta bir kullanıcı, **XTTS-v2**'nin Türkçede Chatterbox'tan **belirgin daha iyi**
> olduğunu bildiriyor (ı/ö/ü + kelime ayrımı + prozodi). XTTS-v2'yi (ticari dışı lisans, CPU'da
> yavaş) TR için **yeniden değerlendirmek** gerekebilir.

### 9.1 GPU boşken çalıştırılacak A/B planı

Amaç: "sorun girdi mi (ASCII), motor mu (tokenizer), yama mı çözüyor?" Aynı cümle, 4 koşul:

```powershell
# metinler (UTF-8, --text-file ile) :
#  A) dogru TR : "Merhaba! Ben tamamen yerel çalışan bir sesli asistanım. Bugün size nasıl yardımcı olabilirim?"
#  B) ASCII    : "Merhaba! Ben tamamen yerel calisan bir sesli asistanim. Bugun size nasil yardimci olabilirim?"

$py = "$env:TEMP\opencode\tts-venv\Scripts\python.exe"
# 1) dogru TR + yama
& $py agent\tts-tools.py --backend chatterbox --lang tr --chatterbox-tr-fix --text-file logs\tts\ab-tr.txt  --out logs\tts\cb-tr-fix.wav
# 2) dogru TR + yamasiz
& $py agent\tts-tools.py --backend chatterbox --lang tr                      --text-file logs\tts\ab-tr.txt  --out logs\tts\cb-tr-raw.wav
# 3) ASCII + yama
& $py agent\tts-tools.py --backend chatterbox --lang tr --chatterbox-tr-fix --text-file logs\tts\ab-ascii.txt --out logs\tts\cb-ascii-fix.wav
```

Sonra her WAV'ı **Whisper geri-çevirimi + WER** ile ölç (bkz. `docs/tts-tr-sonuc.md` §3 yöntemi) ve
kulakla dinle. Beklenti: **(1) ≫ (2)** ise yama çalışıyor; **(1) ≈ (3)** ise sorun yalnız girdiydi.

> ⚠️ Ön koşul: Chatterbox ağırlıkları ilk çalıştırmada indirilir (~2 GB, `ResembleAI/chatterbox`).

### 9.2 Kulak testi + sözlük incelemesi (2026-10-17)

Aynı **doğru Türkçe** cümleyle üretilen örnekler dinlendi:

| Sonuç | Örnek |
|---|---|
| ✅ **İyi** | **Chatterbox (yama açık)**, **Trendyol (VoxCPM2 + TR LoRA)** |
| ❌ Bozuk | Chatterbox **yamasız**, **ASCII** örnekleri, eski (ASCII) Trendyol örnekleri |

- ⚠️ **Kalan tek kusur:** Chatterbox "**çalışan**" → "**çalıyan**" (yani **"ş"** yanlış).
  Whisper geri-çevirimi de "çalayan" duydu → **kulak + ASR uyumlu**.
- **Tokenizer sözlüğü** (`grapheme_mtl_merged_expanded_v1.json`, 2454 token): `ş, ç, ğ, ı, ö, ü, â`
  **ve** birleşen işaretler (`U+0327/U+0308/U+0306/U+0307`) **mevcut**. → Sorun "harf yok" değil:
  **NFKD** metni `s`+cedilla gibi **iki tokene** böler, model tek harf gibi okumaz. **Yama** precomposed
  **tek token**'ı korur → düzelme bundan.
- **"ş" kalıntısı → akustik hata** (modelin Türkçe fonem kalitesi), tokenizer değil. Giderme yolları:
  (a) küçük **respell / G2P-lite** katmanı (ş→"sh" gibi), (b) Türkçe **fine-tune / LoRA**.

**Karar (kulak testiyle, 2026-10-17):** **Her ikisi de iyi** — **Chatterbox (tr-fix + respell)** ve
**Trendyol**. Diğer varyantlar (yamasız / ASCII) elendi. Fark:
- **Chatterbox** → **hafif + hızlı** (ölçüm: ~3,3 GB, RTF ~1,1) ⇒ **canlı hat adayı** (İngilizce de iyi).
- **Trendyol** → **native TR** ama **ağır + yavaş** (~5,6 GB, RTF ~3,4) ⇒ **çevrimdışı / yüksek kalite**.

### 9.3 "ş" için respell çözümü (2026-10-17)

Kalan tek hata ("çalışan"→"çalıyan") için **respell** denendi: **`ş` → `sh`**.
- `respell-base` (normal "ş") → hâlâ "çalıyan" ❌
- **`respell-main-sh2` (ş→sh)** → **doğru** ✅ (kulak testi)

→ `agent/tts-tools.py`'ye ön-işleme **otomatik** eklendi: `--backend chatterbox --lang tr` verilince
**tr_fix + respell kendiliğinden** uygulanır (kapatmak için `--chatterbox-tr-raw`). Offline test:
`python -m pytest -q` → **20 test**.

> Not: bazı üretimlerde model "forcing EOS" uyarısı verip bir kelimeyi bozabiliyor (üretim varyansı) →
> şüpheli örnekte aynı cümle yeniden üretilir. Respell, "ş"yi düzeltir; **ğ/ç için gerekirse** benzer
> ipuçları eklenebilir (henüz gerekmedi).

**Çözüm yolları (kolaydan ağıra):**

| Yol | Ne yapar | Emek | Beklenti |
|---|---|---|---|
| **1. UTF-8 metin + güncel sürüm** | Doğru Türkçe karakterleri + tokenizer düzeltmeleri (çok dilli v2/v3; HF'de "problem solved" notu) | Az | Kısmi iyileşme |
| **2. Türkçe ön-normalizasyon / respelling (G2P-lite)** | Metni modelin doğru okuyacağı forma çevir (ör. `ç→ch`, `ş→sh`, `ı→ı`→fonetik ipucu); sorunlu sözcükler için sözlük | Orta | **En pratik**; CER/WER ile ölçülür |
| **3. espeak-ng tabanlı G2P** | Türkçe metni IPA/foneme çevir | Orta | Chatterbox **fonem kabul etmiyor** (#550) → şimdilik sınırlı |
| **4. Türkçe ince-ayar / LoRA** | Chatterbox'ı Türkçe veriyle eğit (Trendyol'un VoxCPM2'ye yaptığı gibi) | Yüksek | En iyi sonuç, ama maliyetli |

**Sonuç:** Chatterbox'ı "Türkçede elenmiş" saymak **yanlış olur** — sorun **kalite değil, metin
ön-işleme**. En ucuz (0,5B, ~2 GB, MIT) ve en hızlı (RTF <1) motor olduğu için, **Türkçe
ön-normalizasyon (yol 2)** ile ciddi biçimde geri kazanılabilir. Ayrıca yukarıdaki benchmark'taki
"kısa cümlede çökme" bulgusunun bir kısmı da bu diakritik/tokenizer hatasından kaynaklanıyor olabilir.

## 10. Pipeline TTS çalıştırma modları (2026-10-17)

Aynı 4 cümle (LLM çıktısı), RTX 5060 Ti, `--lang tr` (tr-fix + respell otomatik):

| Mod | Toplam (4 cümle) | Not |
|---|---|---|
| Cümle-cümle (her cümle ayrı süreç) | **106,6 sn** | her cümlede torch import (~8 sn) + model yükleme (~13 sn) **tekrar eder** |
| Toplu (`--batch-file`, tek süreç) | **48,4 sn** | yükleme (19,8 sn) **bir kez** + üretim 28,6 sn |
| **Kalıcı sunucu (`--serve`, sıcak)** | **16,6–18,5 sn** | yükleme **yok**; yalnız üretim |

**Tam pipeline** (ASR → LLM → TTS), kalıcı sunucularla (`whisper-server` + `tts-server` + `llama-server`):
**tur başına ~23–27 sn** (3 cümle: ASR ~10 sn + LLM ~4 sn + TTS ~9–12 sn), hiç model yüklemesi yok.

- Chatterbox üretim **RTF ~1,2–1,4** (gerçek zamandan yavaş) → üretim süresi çıktı sesinden uzun;
  ilk ses `<1 sn` hedefi TTS tarafında da tutmuyor.
- ⚠️ Çok kısa cümlede ("Merhaba!") RTF ~3,7'ye çıkıyor ve 9,6 sn'lik ses üretilebiliyor
  (kısa cümle kararsızlığı, bkz. §3).
- ⚠️ **CUDA tuzağı:** bozuk/uygunsuz girdi `device-side assert` ile CUDA bağlamını **kalıcı** bozar;
  sunucu yeniden başlatılmalıdır. Bu yüzden `tts-server` artık metin olmayan öğeleri **400** ile
  reddeder ve `/health` içinde `fatal` alanıyla bunu bildirir.
