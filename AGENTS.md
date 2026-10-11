# mamidChats Chatbot · Geliştirici ve yapay zekâ ajanları için altyapı rehberi

Bu dosya, mamidChats Chatbot üzerinde çalışan geliştiriciler ve yapay zekâ ajanları için tek doğru
kaynaktır. Kullanıcıyla iletişim dili **Türkçe**dir.

> Bu depo **planlama** aşamasındadır. Kod yoktur; aşağıdaki yapı ve kurallar, üzerine inşa edilecek
> hedefi tanımlar.

## 1. Ürün tek paragrafta

Windows'ta tamamen yerel çalışan, gerçek zamanlı, yapay zekâ destekli **sesli sohbet botu**. Tek bir
WinForms penceresinde kullanıcı mikrofonla konuşur; uygulama konuşmayı yazıya çevirir (whisper.cpp
**large-v3-turbo**), yerel dil modeline verir (**Huihui-Qwen3.5 9B Q5_K_M**, **MTP daima açık**) ve
yanıtı sesli okur (TTS). Hedef, kullanıcı konuşmayı bitirdikten sonra **1 saniye içinde** ilk sesin
çıkmasıdır.

## 2. Mimari ilkeler (değişmez)

1. **GPU'da yalnızca dil modeli çalışır.** STT ve TTS **CPU'da** çalışır.
2. **Dil modeli yerleşiktir.** Turlar arasında boşaltılmaz; model takası yok, soğuk başlatma yok.
3. **Model MamidLabs LITE ile aynıdır:** Huihui-Qwen3.5 9B **Q5_K_M** GGUF + MTP (`mtp_inject.py`).
4. **MTP daima açık.** `--spec-type draft-mtp`; kapatılmaz. Ayrı draft model gerekmez, çıktı kayıpsız.
5. **Tek sahipli hat.** Yalnızca `llama-server` + CPU işçileri; ComfyUI/OCR gibi başka VRAM tüketicisi yok.
6. **Boru hattı.** LLM ilk cümle → TTS; kullanıcı dinlerken LLM yazmaya devam eder.

## 3. Dil modeli (LITE ile aynı)

| Alan | Değer |
|---|---|
| Model | Huihui-Qwen3.5 9B **Q5_K_M** (GGUF) |
| MTP | `mtp_inject.py` ile `blk.<N>.nextn.*` eklenir (kaynak: `huihui-ai/Huihui-Qwen3.5-9B-abliterated`) |
| Çalıştırma | `llama-server` + `--spec-type draft-mtp` (daima) |
| Bağlam | varsayılan 32768 (ihtiyaca göre kısılabilir) |
| mmproj | Q8_0 **isteğe bağlı**; bu proje ses-odaklı, **varsayılan yükleme** (VRAM tasarrufu ~420 MiB) |
| Dosyalar | MamidLabs kökünde zaten mevcut → yeniden indirme yok |

> LITE bayrakları referans alınır (ctx 32768, predict 3072, `--reasoning-budget 300`, batch 256/128,
> mmproj GPU'da). Bu projede ComfyUI/OCR olmadığı için GPU tamamen model için ayrılır.

## 4. Bileşen haritası (hedef)

| Yol | İçerik |
|---|---|
| `mamidchats-desktop.ps1` | Ana uygulama: WinForms arayüzü, sohbet durumu, olay döngüsü |
| `agent/llm-run.ps1` | `llama-server` başlat/durdur, MTP, VRAM kapısı (MamidLabs `manage-qwen.ps1` uyarlaması) |
| `agent/stt-tools.py` | 16 kHz mono dönüştürme + `whisper-cli` turbo + Silero VAD |
| `agent/tts-tools.py` | Takas edilebilir TTS: Piper / XTTS / Windows SAPI |
| `agent/pipeline.ps1` | Boru hattı: STT → LLM (akış) → cümle bölme → TTS |
| `agent/audio-capture.ps1` | winmm `mciSendString` ile bağımlılıksız kayıt (WAVE_MAPPER) |
| `scripts/` | kurulum, model indirme, tanı |
| `docs/` | `mimari.md`, `kararlar.md` |
| `tests/` | pytest; PowerShell fonksiyonlarını gerçek `pwsh` ile çalıştırır |

## 5. Süreçler ve portlar (hedef)

| Süreç | Port | Sahibi | Not |
|---|---|---|---|
| `llama-server.exe` | 8080 | `agent/llm-run.ps1` | MTP açık; profil `--alias` ile tanınır |
| Uygulama | — | `pwsh.exe … mamidchats-desktop.ps1` | İşçiler `Start-ThreadJob` runspace'leri |
| STT (whisper) | — | `agent/stt-tools.py` | Kısa ömürlü alt süreç |
| TTS | — | `agent/tts-tools.py` | Kısa ömürlü alt süreç |

## 6. Gecikme bütçesi (hedef < 1000 ms)

| Aşama | Hedef | Yöntem |
|---|---|---|
| Endpoint | 0–200 ms | Bas-konuş = 0; VAD + ~200 ms eşik |
| STT | ≤ 400 ms | large-v3-turbo (CPU) |
| LLM ilk token | ≤ 250 ms | Yerleşik model + KV prefix cache |
| TTS ilk ses | ≤ 150 ms | Piper, ilk cümlede |
| Çalma | ~50 ms | Küçük tampon |

## 7. Kritik tuzaklar (MamidLabs'tan miras, geçerli)

1. **Uygulama yalnızca gömülü PowerShell 7 ile çalışır.** `Start-ThreadJob` 5.1'de yoktur; yanlış
   host'la açılırsa sessizce takılır → kendini yeniden başlatmalı.
2. **`Start-ThreadJob -FilePath` içinde `$PSScriptRoot` boştur.** Kök `$JobData.root` üzerinden taşınır.
3. **Windows PowerShell 5.1 BOM'suz `.ps1`'i ANSI okur.** 5.1 betikleri ASCII tut ya da UTF-8 BOM'lu kaydet.
4. **KV önbellek eşleşmesi.** Arayüzün tuttuğu mesaj dizisi, sunucunun işlediğiyle bayt bayt aynı
   olmalı; yoksa bağlam her turda baştan işlenir. Tura özel metin son kullanıcı mesajına konur.
5. **`Start-DetachedProcess` kullan.** `Start-Process -Redirect…` çağıranın stdout borusunu devralır ve asılı kalır.
6. **VRAM payı küçük tutulur.** 9B MTP kartın sınırında; büyük pay modele hiç başlatmaz.
7. **MTP bayrağı yalnızca GGUF gerçekten MTP katmanı taşıyorsa eklenir** (`Test-GgufHasMtp`); taşımayan
   modele verilirse llama.cpp "model doesn't contain MTP layers" ile açılmaz.
8. **`%` bir `.cmd` dosyasında özeldir.** Eşleşmeyen her `%` sessizce silinir.

## 8. Değişiklik yaparken kontrol listesi

- [ ] İlgili testleri çalıştır; yeni davranışa test ekle.
- [ ] MTP hâlâ açık mı? (Kesin kural)
- [ ] Model hâlâ LITE (Huihui-Qwen3.5 9B Q5_K_M) mi?
- [ ] STT turbo mu, varsayılan değişmedi mi?
- [ ] Dil modeli hâlâ boşaltılmıyor mu (yerleşik)?
- [ ] GPU'ya LLM dışında bir şey taşınmadı mı?
- [ ] TR ve ENG sürümleri tutarlı mı?
- [ ] `README.md`, `docs/mimari.md`, `docs/kararlar.md` ve bu dosya güncel mi?

## 9. Değişiklik günlüğü

| Tarih | Değişiklik | Dosyalar |
|---|---|---|
| 2026-10-11 | Mimariye tur dizisi (Mermaid) + bileşen sorumluluk tablosu eklendi; Faz 2 ölçüm planı yazıldı. | docs/mimari.md, docs/faz2-olcum-plani.md, README.md |
| 2026-10-11 | Model MamidLabs LITE ile eşitlendi (Huihui-Qwen3.5 9B Q5_K_M + MTP enjekte). | README.md, AGENTS.md, docs/mimari.md, docs/kararlar.md |
| 2026-10-11 | Depo açıldı; plan yazıldı. STT turbo, MTP daima açık, hedef <1 sn. | README.md, AGENTS.md, docs/mimari.md, docs/kararlar.md |
