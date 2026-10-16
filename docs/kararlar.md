# Karar Günlüğü

Her karar: **ne**, **neden**, **alternatifler**. En yeni üstte.

| # | Tarih | Karar | Gerekçe | Alternatifler (neden değil) |
|---|---|---|---|---|
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
| TTS | **Kokoro-82M** | Türkçe desteklemiyor |
| TTS | **F5-TTS** | Sadece İngilizce/Çince |
| TTS | **XTTS-v2** | Daha eski; ticari dışı lisans + CPU'da yavaş (Chatterbox v3 daha yeni ve doğal) |
| Yığın | Python/PySide6, web arayüzü | MamidLabs altyapısı PowerShell 7 + WinForms olduğundan yeniden kullanım için o seçildi |

## Açık kararlar (henüz verilmedi)

- [ ] LLM quantizasyonu: **i1-Q5_K_M** (varsayılan) mı, VRAM için **i1-Q4_K_M** (~5,6 GB) mı?
- [ ] **MTP uyumu:** i1 imatrix quant + `mtp_inject.py` çalışıyor mu? Çalışmazsa orijinal `huihui-ai` GGUF'a mı dönülür?
- [ ] STT: **`large-v3-turbo`** yeterli mi, `medium`/`small`'a mı inilmeli (Faz 2 ölçümü)
- [ ] TTS birincil motoru: **Chatterbox v3** (gerçekçi, GPU) mı **Piper** (hızlı, CPU) mı
- [ ] Akışlı ASR penceresi / VAD eşiği kesinleşmesi
- [ ] Proje lisans metni
