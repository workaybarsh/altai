# Karar Günlüğü

Her karar: **ne**, **neden**, **alternatifler**. En yeni üstte.

| # | Tarih | Karar | Gerekçe | Alternatifler (neden değil) |
|---|---|---|---|---|
| 10 | 2026-10-11 | STT = **Qwen3-ASR-1.7B** (whisper yerine); hız yedeği **0.6B** | Türkçe + 30 dil, akışlı çıkarım, dil algılama, gürültü/BGM dayanıklılığı, Apache-2.0 | whisper large-v3-turbo (daha hızlı ama daha az yetenek), 0.6B (daha hızlı, biraz daha zayıf — yedek olarak duruyor) |
| 9 | 2026-10-11 | LLM = **Huihui-Qwen3.5 9B Q5_K_M** (MamidLabs LITE ile aynı) | Kanıtlanmış, dosyalar zaten diskte (yeniden indirme yok), MTP ile ~97 tok/s | Başka 9B (yeniden indirme + doğrulanmamış), 27B (8 GB'a sığmaz) |
| 8 | 2026-10-11 | STT = whisper.cpp **large-v3-turbo** | Sohbet doğruluk-kritik değil, hız kritik; turbo CPU'da ~0,2–0,4 sn → <1 sn hedefine sığar | large-v3 (CPU'da yavaş, hedefi yer), GPU'da whisper (LLM ile VRAM çakışır) |
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

## Açık kararlar (henüz verilmedi)

- [ ] ASR: **Qwen3-ASR-1.7B** yeterli mi, **0.6B**'ye mi inilmeli (Faz 2 ölçümü)
- [ ] TTS birincil motoru: **Chatterbox v3** (gerçekçi, GPU) mı **Piper** (hızlı, CPU) mı
- [ ] LLM quantizasyonu: Q5 mi Q4 mü (TTS'i GPU'ya almak için Q4 gerekebilir)
- [ ] Akışlı ASR penceresi / VAD eşiği kesinleşmesi
- [ ] Proje lisans metni
