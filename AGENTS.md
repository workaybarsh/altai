# aybars_says · sesli yerel yapay zekâ sohbet botu · Geliştirici ve yapay zekâ ajanları için altyapı rehberi

Bu dosya, aybars_says (eski adı: mamidChats Chatbot) üzerinde çalışan geliştiriciler ve yapay
zekâ ajanları için tek doğru kaynaktır. Kullanıcıyla iletişim dili **Türkçe**dir.

> Bu depo **ağırlıklı olarak planlama** aşamasındadır; ilk çalışan araç `agent/mtp_inject.py`.
> Aşağıdaki yapı ve kurallar, üzerine inşa edilecek hedefi tanımlar.

## 1. Ürün tek paragrafta

Windows'ta tamamen yerel çalışan, gerçek zamanlı, yapay zekâ destekli **sesli sohbet botu**. Tek bir
WinForms penceresinde kullanıcı mikrofonla konuşur; uygulama konuşmayı yazıya çevirir (**whisper.cpp**),
yerel dil modeline verir (**Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M**, **MTP daima açık**) ve yanıtı
sesli okur (TTS). Hedef, kullanıcı konuşmayı bitirdikten sonra **1 saniye içinde** ilk sesin çıkmasıdır.

## 2. Mimari ilkeler (değişmez)

1. **GPU'da yalnızca dil modeli çalışır.** STT ve TTS **CPU'da** çalışır.
2. **Dil modeli yerleşiktir.** Turlar arasında boşaltılmaz; model takası yok.
3. **Model:** Huihui-Qwen3.5-9B-abliterated **i1-Q5_K_M** GGUF (imatrix) + MTP (`mtp_inject.py`).
4. **MTP daima açık.** `--spec-type draft-mtp`; kapatılmaz. Kayıpsız çıktı.
5. **STT: whisper.cpp** (Qwen3-ASR kullanılmaz).
6. **Tek sahipli hat.** Yalnızca `llama-server` + CPU işçileri.
7. **Boru hattı.** LLM ilk cümle → TTS; kullanıcı dinlerken LLM yazmaya devam eder.

## 3. Modeller

### 3.1 Dil modeli

| Alan | Değer |
|---|---|
| Model | Huihui-Qwen3.5-9B-abliterated **i1-Q5_K_M** (GGUF, imatrix) |
| Dosya | `Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf` (~6,6 GB) |
| HF deposu | `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF` |
| Taban model | `huihui-ai/Huihui-Qwen3.5-9B-abliterated` (Qwen3.5-9B türevi, abliterated) |
| MTP | `mtp_inject.py` ile `blk.<N>.nextn.*` (kaynak: `huihui-ai/Huihui-Qwen3.5-9B-abliterated`) |
| Çalıştırma | `llama-server` + `--spec-type draft-mtp` (daima) |
| Bağlam | varsayılan 32768 |

> **Doğrulandı (2026-10-16):** hedef quant GGUF (`i1-Q5_K_M`) MTP/`nextn` katmanı **içermez**;
> kaynak `huihui-ai/Huihui-Qwen3.5-9B-abliterated` deposunda **15 MTP tensoru mevcut** ve
> `mtp_inject.py` eşlemesiyle birebir uyuşur. Enjeksiyon **zorunludur**. Riskler ve kabul testleri:
> [`docs/mtp-dogrulama.md`](docs/mtp-dogrulama.md).

### 3.2 STT: whisper.cpp

| Alan | Değer |
|---|---|
| Motor | **whisper.cpp** (MIT, C/C++) |
| Model | **large-v3-turbo** (varsayılan); hız yedekleri `medium` / `small` |
| Lisans | MIT (motor) · model ağırlıkları MIT |
| Dil | Çok dilli; **Türkçe (tr)** destekli |
| Yetenek | Çevrimdışı toplu çıkarım; akışlı/parçalı kullanım mümkün |
| Boyut | turbo ~1,6 GB (Q5) · medium ~1,5 GB · small ~0,5 GB |
| Nerede | **CPU** (GPU LLM'e ait) |
| Yedek | `medium` / `small` (CPU'da daha hızlı) |

> **Hız notu:** whisper.cpp `large-v3-turbo` CPU'da tipik sohbet cümlesini ~0,2–0,4 sn'de çevirir
> (thread ayarına bağlı). Uzun cümlede `<1 sn` sınırda; VAD bölütleme + parça paralelliği ile telafi
> edilir. Gerekirse `medium`/`small`'a inilir. Faz 2'de ölçülür.

### 3.3 TTS: takas edilebilir katman

| Motor | Doğallık | Türkçe | Canlı hız | Lisans | Rol |
|---|---|---|---|---|---|
| **Chatterbox Multilingual v3** | En yüksek | ⚠️ zayıf | GPU | MIT | EN birincil |
| **Trendyol-TTS** (`voxcpm`, VoxCPM2 + TR LoRA, ~2B) | Yüksek | ✅ anlaşılır | ❌ RTF ~3, ~5,6 GB VRAM | MIT | **TR çevrimdışı/yüksek kalite** |
| **Piper** | Orta | ✅ | ✅ CPU | GPL-3.0 | Hızlı/yedek |
| Windows SAPI | Düşük | ✅ | ✅ | — | Son çare |

> **Ölçüldü (2026-10-16):** Trendyol-TTS Türkçe **anlaşılır** (geri-çevirim Whisper WER ~0,08) ama
> ~5,6 GB VRAM + RTF ~3 → hedef 8 GB kartta yerleşik LLM ile sığmaz ve `<1 sn` hedefini yer.
> Bu yüzden **canlı hattın varsayılanı değil**; `tts-tools.py --backend voxcpm` ile çevrimdışı
> motor olarak eklendi (karar #16). Ayrıntı: [`docs/tts-tr-sonuc.md`](docs/tts-tr-sonuc.md).

## 4. Bileşen haritası

✅ = mevcut · ⬜ = hedef

| Durum | Yol | İçerik |
|---|---|---|
| ⬜ | `mamidchats-desktop.ps1` | Ana uygulama: WinForms arayüzü, sohbet durumu, olay döngüsü |
| ⬜ | `agent/llm-run.ps1` | `llama-server` başlat/durdur, MTP, VRAM kapısı |
| ✅ | `agent/mtp_inject.py` | Quant GGUF'a MTP/`nextn` başlığı ekler (taban `huihui-ai` deposundan) |
| ✅ | `agent/mtp-durum.py` | Bir GGUF'un MTP durumunu JSON olarak yazar |
| ✅ | `scripts/mtp-dogrula.ps1` | MTP durumunu denetler; `-Inject` ile başlığı ekler |
| ✅ | `agent/asr-tools.py` | 16 kHz mono dönüştürme + **whisper.cpp** çıkarımı + gecikme/RTF ölçümü |
| ✅ | `scripts/asr-olcum.ps1` | Faz 2 ASR ölçüm koşum takımı (sarmalayıcı) |
| ✅ | `agent/tts-tools.py` | Takas edilebilir TTS: Chatterbox / **voxcpm** (Trendyol-TTS, TR) / Piper / SAPI |
| ⬜ | `agent/pipeline.ps1` | Boru hattı: ASR → LLM (akış) → cümle bölme → TTS |
| ⬜ | `agent/audio-capture.ps1` | winmm `mciSendString` ile bağımlılıksız kayıt |
| ✅ | `tests/` | pytest (MTP enjeksiyonu + ASR araçları) |
| ✅ | `scripts/`, `docs/` | kurulum/tanı, belgeler |

## 5. Gecikme bütçesi (hedef < 1000 ms)

| Aşama | Hedef | Yöntem |
|---|---|---|
| Endpoint | 0–200 ms | Bas-konuş = 0; VAD + ~200 ms eşik |
| STT | ≤ 400 ms | whisper.cpp `large-v3-turbo` (gerekirse `medium`/`small`) |
| LLM ilk token | ≤ 250 ms | Yerleşik model + KV prefix cache |
| TTS ilk ses | ≤ 150 ms | Chatterbox/Piper, ilk cümlede. **Trendyol-TTS (`voxcpm`) canlı için uygun değil** (RTF ~3, ~5,6 GB VRAM) — çevrimdışı/yüksek kalite |

## 6. Kritik tuzaklar

1. **Uygulama yalnızca gömülü PowerShell 7 ile çalışır.** `Start-ThreadJob` 5.1'de yoktur.
2. **`Start-ThreadJob -FilePath` içinde `$PSScriptRoot` boştur.** Kök `$JobData.root` ile taşınır.
3. **Windows PowerShell 5.1 BOM'suz `.ps1`'i ANSI okur.** 5.1 betikleri ASCII tut ya da UTF-8 BOM'lu kaydet.
4. **KV önbellek eşleşmesi.** Arayüzün mesaj dizisi sunucununkiyle bayt bayt aynı olmalı.
5. **`Start-DetachedProcess` kullan.** `Start-Process -Redirect…` çağıranın stdout'unu devralır.
6. **VRAM payı küçük tutulur.** 9B i1-Q5_K_M (~6,6 GB) + MTP + KV, 8 GB kartın sınırında.
7. **MTP bayrağı yalnızca GGUF MTP katmanı taşıyorsa eklenir** (`Test-GgufHasMtp`). Quant GGUF
   MTP'yi içermez; indirmede `mtp_inject.py` ile geri eklenir (bkz. [`docs/mtp-dogrulama.md`](docs/mtp-dogrulama.md)).
8. **ASR/TTS CPU'yu paylaşır.** Aynı anda çalışmazlar (dinleme vs konuşma), ama gürültülü makinede ölçüm şart.
9. **whisper.cpp thread sayısı.** Fiziksel çekirdek sayısına göre ayarlanır; aşırı thread hızı düşürür.

## 7. Değişiklik kontrol listesi

- [ ] MTP hâlâ açık mı? (Kesin kural)
- [ ] LLM hâlâ i1-Q5_K_M (Huihui-Qwen3.5-9B-abliterated) mi?
- [ ] STT hâlâ whisper.cpp mi (Qwen3-ASR'a dönülmedi)?
- [ ] Dil modeli hâlâ yerleşik mi (boşaltılmıyor)?
- [ ] GPU'ya LLM dışında bir şey taşınmadı mı?
- [ ] TR ve ENG sürümleri tutarlı mı?
- [ ] `README.md`, `docs/mimari.md`, `docs/mtp-dogrulama.md`, `docs/faz2-olcum-plani.md`, `docs/faz2-sonuc.md`, `docs/kararlar.md` güncel mi?

## 8. Değişiklik günlüğü

| Tarih | Değişiklik | Dosyalar |
|---|---|---|
| 2026-10-17 | **Chatterbox TR diakritik sorununun kök nedeni bulundu ve yaması yazıldı:** tokenizer'ın `NFKD` + Türkçe-duyarsız `lower()` hatası → `install_tr_tokenizer_fix()` / `--chatterbox-tr-fix` (offline, **19 test**). Ses doğrulaması GPU boşken. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-kiyaslama.md, docs/tts-tr-sonuc.md, docs/kararlar.md, DURUM.md, AGENTS.md |
| 2026-10-16 | **Bağımsız Türkçe TTS kıyası işlendi** (arXiv:2610.06057, Sestek): Chatterbox vs CosyVoice/OmniVoice/VoxCPM2/VITS. Chatterbox hiçbir metriği kazanmıyor + kısa cümlede çöküyor; VoxCPM2 klon/kararlılık, CosyVoice doğallık lideri. Karar #17. | docs/tts-kiyaslama.md, docs/kararlar.md, DURUM.md, README.md, AGENTS.md |
| 2026-10-16 | **Türkçe TTS değerlendirildi + `voxcpm` backend eklendi.** Trendyol-TTS (VoxCPM2 + TR LoRA) ölçüldü: ~5,6 GB VRAM, RTF ~3, geri-çevirim Whisper WER ~0,08 → **anlaşılır ama canlı hat için ağır**; çevrimdışı motor olarak `tts-tools.py`'ye eklendi. Testler 17'ye çıktı. | agent/tts-tools.py, tests/test_tts_tools.py, docs/tts-tr-sonuc.md, docs/kararlar.md, DURUM.md, README.md, AGENTS.md, docs/mimari.md |
| 2026-10-16 | **Faz 2 ASR hattı iskeleti eklendi** (`asr-tools.py`, `asr-olcum.ps1`) ve **gerçek whisper.cpp ile uçtan uca doğrulandı** (base.en, CPU, RTF ~0,19). Testler 13'e çıktı. | agent/asr-tools.py, scripts/asr-olcum.ps1, tests/, docs/faz2-olcum-plani.md, AGENTS.md |
| 2026-10-16 | **İlk çalışan araç eklendi:** `agent/mtp_inject.py` (kanıtlı) + `scripts/mtp-dogrula.ps1` durum/enjeksiyon betiği. Depo "sesli" olarak işaretlendi. | agent/mtp_inject.py, scripts/mtp-dogrula.ps1, README.md, AGENTS.md |
| 2026-10-16 | **MTP doğrulandı ve zorunlu kılındı.** Hedef quant GGUF'ta MTP yok; kaynak 15 tensor mevcut; `mtp_inject.py` şart. Doğrulama + kabul testleri belgesi eklendi. | README.md, AGENTS.md, docs/mimari.md, docs/kararlar.md, docs/mtp-dogrulama.md |
| 2026-10-16 | LLM, **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (mradermacher imatrix quant) olarak belirlendi. | README.md, AGENTS.md, docs/mimari.md, docs/kararlar.md |
| 2026-10-16 | STT **Qwen3-ASR → whisper.cpp** (`large-v3-turbo`) olarak geri çevrildi. | README.md, AGENTS.md, docs/mimari.md, docs/faz2-olcum-plani.md, docs/kararlar.md |
| 2026-10-16 | Depo adı **mamidChats-Chatbot → aybars_says**; metinler güncellendi. | tümü |
| 2026-10-11 | README'ye **Durum** bölümü eklendi: taslak (`v0.1-plan`), kod yok, AR-GE yedek yolları not edildi. | README.md, AGENTS.md |
| 2026-10-11 | "Değerlendirilen ve vazgeçilen alternatifler" bölümü eklendi. | docs/kararlar.md, docs/mimari.md |
| 2026-10-11 | STT whisper'dan **Qwen3-ASR-1.7B**'ye çekildi (o dönem); hız yedeği 0.6B. | tümü |
| 2026-10-11 | Mimariye tur dizisi + sorumluluk tablosu; Faz 2 ölçüm planı. | docs/mimari.md, docs/faz2-olcum-plani.md |
| 2026-10-11 | Model MamidLabs LITE ile eşitlendi. | tümü |
| 2026-10-11 | Depo açıldı; plan yazıldı. | tümü |
