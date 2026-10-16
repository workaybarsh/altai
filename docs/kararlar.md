# Karar Günlüğü

Her karar: **ne**, **neden**, **alternatifler**. En yeni üstte.

| # | Tarih | Karar | Gerekçe | Alternatifler (neden değil) |
|---|---|---|---|---|
| 18 | 2026-10-16 | **Chatterbox Türkçe sorunu = ön-işleme hatası (kalite değil)** → Chatterbox TR için **elenmez**; yama ile geri kazanılacak **en ucuz/hızlı aday** | **Kök neden (kod, doğrulandı):** `MTLTokenizer.preprocess_text` her zaman `NFKD` uyguluyor (`ş`→`s`+cedilla, `ü`→`u`+diaeresis) + `lower()` Türkçe-duyarsız → diakritik düşüyor. `install_tr_tokenizer_fix()` yaması yazıldı, offline **19 test** geçiyor. Kayıtlar: chatterbox **#261**, HF **#33/#550**, `voicebox` **#846** (ve XTTS-v2 TR'de daha iyi iddiası). 0,5B + **~2 GB** + **RTF<1** + **MIT**. Ayrıntı: [`tts-kiyaslama.md`](tts-kiyaslama.md) §8–9 | Chatterbox'ı TR'de elemek (sorun kalite değil); pahalı LoRA'yı ilk çare yapmak |
| 17 | 2026-10-16 | **Bağımsız Türkçe TTS kanıtı işlendi** (arXiv:2610.06057, Sestek): Chatterbox TR'de **hiçbir metriği kazanmıyor** ve **kısa cümlede çöküyor**; **VoxCPM2** klon/benar./uzun-form kararlılık lideri, **CosyVoice** doğallık lideri, **OmniVoice(ZS)** anlaşılırlık lideri | Chatterbox'ın TR zayıflığını objektif doğruluyor; TR için VoxCPM2 ailesi (→ Trendyol) + CosyVoice öne çıkıyor. Ayrıntı: [`tts-kiyaslama.md`](tts-kiyaslama.md) | — (kanıt kaydı) |
| 16 | 2026-10-16 | TTS-TR: **Trendyol-TTS** (`openbmb/VoxCPM2` + TR LoRA, MIT, ~2B) **cevrimdisi/yuksek-kalite TR motoru** olarak eklendi (`tts-tools.py --backend voxcpm`). **Canli `<1 sn` hattinin varsayilani DEGIL** | TR native ve **anlasilir** (geri-ceviri Whisper WER ~0,08, 2026-10-16). Ama **agir**: ~5,6 GB VRAM + RTF ~3 (gercek zamandan ~3x yavas) → 8 GB kartta yerlesik 9B LLM ile sigmaz ve `<1 sn` hedefini yer | Canli hatta birincil yapmak (VRAM + gecikme → reddedildi); Piper (CPU hizli ama robotik); CosyVoice2 / XTTS-v2 (bkz. acik kararlar) |
| 15 | 2026-10-16 | **Fish S2 Pro yalnizca IZOLE WSL denemesi** — projeye entegre edilmez | Merak/karşılaştırma amaçlı; **Fish Audio Research License (ticari dışı)**, yalnız Linux/WSL, 24 GB önerilir. Proje MIT/cross-platform kalmalı | Projeye almak (lisans + Windows dışı + VRAM çakışması → reddedildi) |
| 14 | 2026-10-16 | TTS = **Chatterbox Multilingual v3** (Ingilizce icin birincil) | Gerçekçi (ElevenLabs'ı geçiyor), **MIT lisans**, 5 sn klonlama, 0,5B → CPU/GPU esnek; `agent/tts-tools.py` ile sarmalandı. ⚠️ **Türkçe çıktısı zayıf → bkz. #16** | Fish S2 Pro (lisans+WSL), Piper (robotik), XTTS-v2 (eskimiş) |
| 13 | 2026-10-16 | **MTP zorunlu + enjeksiyonla geri eklenir** | Quant GGUF MTP/`nextn` içermez (doğrulandı: hedefte 0, kaynakta 15 tensor); MTP olmadan `--spec-type draft-mtp` sunucuyu açmaz | MTP kapalı (~2x yavaş), MTP'li custom GGUF üretmek (zahmetli, kırılgan) |
| 12 | 2026-10-16 | LLM = **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (imatrix GGUF) | imatrix quant aynı boyutta daha iyi kalite verir; net HF kaynağı (`mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF`); Q5_K_M ~6,6 GB | Orijinal `huihui-ai` (static) Q5_K_M (imatrix'e göre biraz daha zayıf), Q4 (kalite kaybı) |
| 11 | 2026-10-16 | STT = **whisper.cpp** (`large-v3-turbo`) | Olgun, çok dilli, olgun C/C++ ekosistem, CPU'da hızlı (~0,2–0,4 sn); CUDA'sız iyi performans | Qwen3-ASR-1.7B (Türkçe+akışlı idi ama CPU'da yavaş), `large-v3` (yavaş) |
| 10 | 2026-10-11 | ~~STT = **Qwen3-ASR-1.7B** (whisper yerine); hız yedeği **0.6B**~~ → **#11 ile değiştirildi** | Türkçe + 30 dil, akışlı çıkarım, dil algılama, gürültü dayanıklılığı, Apache-2.0 | whisper large-v3-turbo (o dönem yedek olarak görülüyordu) |
| 9 | 2026-10-11 | LLM = **Huihui-Qwen3.5 9B Q5_K_M** (MamidLabs LITE ile aynı) | Kanıtlanmış, dosyalar zaten diskte, MTP ile ~97 tok/s | Başka 9B, 27B (8 GB'a sığmaz) — **kaynak #12 ile güncellendi** |
| 8 | 2026-10-11 | STT = **whisper.cpp `large-v3-turbo`** (ilk karar) | Sohbet doğruluk-kritik değil, hız kritik; turbo CPU'da ~0,2–0,4 sn → <1 sn hedefine sığar | large-v3 (CPU'da yavaş, hedefi yer), GPU'da whisper (LLM ile VRAM çakışır) |
| 7 | 2026-10-11 | **MTP daima açık** | ~2x hız, kayıpsız çıktı, ayrı draft model gerekmez; canlı sohbet için kritik | MTP kapalı (yavaş, gereksiz) |
| 6 | 2026-10-11 | Hedef gecikme **< 1 sn** | "Canlı" hissin eşiği; kullanıcı hedefi | <300 ms (8 GB/CPU gerçekleriyle imkânsız), >1 sn (robot hissi) |
| 5 | 2026-10-11 | Kullanım **kişisel/kapalı** | XTTS-v2 ticari lisansı sorun olmaktan çıkar | Ticari dağıtım (Chatterbox/Piper zorunlu olurdu) |
| 4 | 2026-10-11 | Dil: **TR + ENG** (iki sürüm) | MamidLabs ile aynı yaklaşım | Tek dil (sonradan ekleme maliyeti) |
| 3 | 2026-10-11 | TTS **takas edilebilir** katman | Gecikme/kalite dengesi sonradan ölçümle seçilir | Tek motora sabitlenmek (esneklik kaybı) |
| 2 | 2026-10-11 | Etkileşim: **bas-konuş + sürekli dinleme** | İkisi de farklı kullanımlar için | Yalnız PTT (eller serbest yok), yalnız VAD (yanlış tetikleme) |
| 1 | 2026-10-11 | Yığın: **PowerShell 7 + WinForms** | MamidLabs altyapısı/desenleri doğrudan yeniden kullanılır | Python/PySide6 (altyapı sıfırdan), web arayüzü (mikrofon/gecikme) |
| 0 | 2026-10-11 | **Ayrı proje** olarak kurulum | Mevcut çalışmada başka VRAM tüketicileri var (ComfyUI, OCR, mmproj) | MamidLabs'a eklemek (VRAM çakışması, karmaşıklık) |

## Mimari ilkeler (karar değil, değişmez)

- **GPU'da yalnızca dil modeli.** STT ve TTS CPU'da. Dil modeli boşaltılmaz (yerleşik).
- **Tek sahipli hat.** Yalnızca `llama-server` + CPU işçileri; başka VRAM tüketicisi yok.
- **Tahmin edilemez boşaltma yok.** Model takası yok; soğuk başlatma yok.

## Değerlendirilen ve vazgeçilen alternatifler

Planlama sırasında masaya gelip vazgeçilen seçenekler (kayıt için; en yeni üstte):

| Konu | Düşünülen | Neden vazgeçildi |
|---|---|---|
| STT | **Qwen3-ASR-1.7B** (ve `0.6B` yedeği) | Bir dönem whisper yerine seçilmişti; ancak CPU'da 1.7B gerçek zamanın ~4 katı olduğundan `<1 sn` hedefinde riskliydi. **#11** ile whisper.cpp'ye dönüldü. Türkçe/akışlı avantajı gerekirse tekrar değerlendirilebilir |
| STT | whisper `large-v3` (tam) | CPU'da yavaş; `<1 sn` hedefini tek başına yer (turbo tercih edildi) |
| LLM | Orijinal `huihui-ai` **static** Q5_K_M | Çalışır ama imatrix (i1) quant aynı boyutta daha iyi kalite verir → #12 |
| LLM | Qwen 3.5 **27B** (MamidLabs MAX/FLASH) | 8 GB VRAM'e sığmaz |
| TTS | **Fish Audio S2 Pro** (4.4B) | En gerçekçi ve Türkçe destekli, **ama** Fish Audio Research License (ticari dışı), yalnız Linux/WSL ve 24 GB önerilir → projeye uymaz. **Yalnızca izole WSL denemesi** olarak kalır (karar #15). |
| TTS | **Trendyol-TTS** canlı hatta **birincil** | TR native ve anlaşılır (geri-çevirim WER ~0,08) **ama** ~5,6 GB VRAM + RTF ~3 → 8 GB kartta yerleşik 9B LLM ile sığmaz ve `<1 sn` hedefini yer. **Çevrimdışı/yüksek-kalite motoru olarak alındı** (karar #16); canlı hat için uygun değil |
| TTS | **CosyVoice2**, **XTTS-v2** | TR destekli ama GPU/CPU'da yavaş; canlı `<1 sn` hattında riskli (yedek adaylar, karar #16) |
| TTS | **Kokoro-82M** | Türkçe desteklemiyor |
| TTS | **F5-TTS** | Sadece İngilizce/Çince |
| TTS | **XTTS-v2** | Daha eski; ticari dışı lisans + CPU'da yavaş (Chatterbox v3 daha yeni ve doğal) |
| Yığın | Python/PySide6, web arayüzü | MamidLabs altyapısı PowerShell 7 + WinForms olduğundan yeniden kullanım için o seçildi |

## Açık kararlar (henüz verilmedi)

- [ ] LLM quantizasyonu: **i1-Q5_K_M** (varsayılan) mı, VRAM için **i1-Q4_K_M** (~5,6 GB) mı?
- [x] **MTP:** quant GGUF'ta yok → `mtp_inject.py` ile enjekte edilir (kaynak doğrulandı). Kabul
  testleri: [`mtp-dogrulama.md`](mtp-dogrulama.md). *(Karar #13.)*
- [ ] MTP enjeksiyonu sonrası 8 GB VRAM'e sığıyor mu (gerçek ölçüm)?
- [ ] STT: **`large-v3-turbo`** yeterli mi, `medium`/`small`'a mı inilmeli (Faz 2 ölçümü)
- [x] TTS birincil = **Chatterbox Multilingual v3** (EN). TR = **Trendyol-TTS** çevrimdışı/yüksek-kalite motoru (`tts-tools.py --backend voxcpm`); Fish S2 Pro yalnızca izole WSL denemesi. *(Kararlar #14, #15, #16.)*
- [ ] **Canlı TR TTS** hâlâ açık: Piper (CPU, hızlı ama robotik) mi, yoksa GPU'ya alınan yüksek-kalite motor (LLM'i küçültür/boşaltır) mu? "İki mod" öneriliyor. Trendyol-TTS canlı için elendi (RTF ~3, ~5,6 GB VRAM)
- [ ] **Chatterbox TR ön-normalizasyon (G2P-lite) denemesi:** diakritikleri doğru okutacak metin dönüşümü + CER/WER ölçümü (#18). Başarılıysa TR için en hafif/hızlı yol
- [ ] **VoxCPM RTF'i yeniden ölç:** `inference_timesteps=10` + `torch.compile`/Triton'un Windows'ta çalıştığını doğrula (resmî ~0,3 vs bizim ~3)
- [ ] **Canlı TR adayları:** bağımsız kanıta göre (arXiv:2610.06057) **CosyVoice** (doğallık + uzunluk-dayanıklı) öncelikli, ardından **OmniVoice(ZS)** (anlaşılırlık). İkisinin de **RTF + VRAM**'i ölçülmeli. Ayrıntı: [`tts-kiyaslama.md`](tts-kiyaslama.md)
- [ ] Akışlı ASR penceresi / VAD eşiği kesinleşmesi
- [ ] Proje lisans metni
