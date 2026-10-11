# mamidChats Chatbot · Geliştirici ve yapay zekâ ajanları için altyapı rehberi

Bu dosya, mamidChats Chatbot üzerinde çalışan geliştiriciler ve yapay zekâ ajanları için tek doğru
kaynaktır. Kullanıcıyla iletişim dili **Türkçe**dir.

> Bu depo **planlama** aşamasındadır. Kod yoktur; aşağıdaki yapı ve kurallar, üzerine inşa edilecek
> hedefi tanımlar.

## 1. Ürün tek paragrafta

Windows'ta tamamen yerel çalışan, gerçek zamanlı, yapay zekâ destekli **sesli sohbet botu**. Tek bir
WinForms penceresinde kullanıcı mikrofonla konuşur; uygulama konuşmayı yazıya çevirir (**Qwen3-ASR**),
yerel dil modeline verir (**Huihui-Qwen3.5 9B Q5_K_M**, **MTP daima açık**) ve yanıtı sesli okur
(TTS). Hedef, kullanıcı konuşmayı bitirdikten sonra **1 saniye içinde** ilk sesin çıkmasıdır.

## 2. Mimari ilkeler (değişmez)

1. **GPU'da yalnızca dil modeli çalışır.** STT ve TTS **CPU'da** çalışır.
2. **Dil modeli yerleşiktir.** Turlar arasında boşaltılmaz; model takası yok.
3. **Model MamidLabs LITE ile aynıdır:** Huihui-Qwen3.5 9B **Q5_K_M** GGUF + MTP (`mtp_inject.py`).
4. **MTP daima açık.** `--spec-type draft-mtp`; kapatılmaz. Kayıpsız çıktı.
5. **STT: Qwen3-ASR** (whisper kullanılmaz).
6. **Tek sahipli hat.** Yalnızca `llama-server` + CPU işçileri.
7. **Boru hattı.** LLM ilk cümle → TTS; kullanıcı dinlerken LLM yazmaya devam eder.

## 3. Modeller

### 3.1 Dil modeli (LITE ile aynı)

| Alan | Değer |
|---|---|
| Model | Huihui-Qwen3.5 9B **Q5_K_M** (GGUF) |
| MTP | `mtp_inject.py` ile `blk.<N>.nextn.*` (kaynak: `huihui-ai/Huihui-Qwen3.5-9B-abliterated`) |
| Çalıştırma | `llama-server` + `--spec-type draft-mtp` (daima) |
| Bağlam | varsayılan 32768 |
| Dosyalar | MamidLabs kökünde mevcut → yeniden indirme yok |

### 3.2 STT: Qwen3-ASR

| Alan | Değer |
|---|---|
| Model | **Qwen3-ASR-1.7B** (Qwen3-1.7B + projector + AuT encoder) |
| Lisans | Apache-2.0 |
| Dil | 30 dil + 22 Çince lehçe; **Türkçe (tr)** |
| Yetenek | Dil algılama (LID), **akışlı + çevrimdışı**, gürültü/BGM/söylenen ses dayanıklı |
| Boyut | fp16 ~4,7 GB · Q8 ~2,5 GB · **Q4 ~1,3 GB** |
| Nerede | **CPU** (GPU LLM'e ait) — saf C (`antirez/qwen-asr`) veya `qwen-asr` |
| Yedek | **Qwen3-ASR-0.6B** (CPU tatlı noktası, ~2× hızlı) |

> **Hız notu:** CPU'da 1.7B gerçek zamanın ~4 katı (ölçüm: 11 sn ses ~2,6 sn). Uzun cümlede `<1 sn`
> sınırda; akışlı çıkarım + VAD ile algılanan gecikme düşürülür. Gerekirse 0.6B'ye inilir.

## 4. Bileşen haritası (hedef)

| Yol | İçerik |
|---|---|
| `mamidchats-desktop.ps1` | Ana uygulama: WinForms arayüzü, sohbet durumu, olay döngüsü |
| `agent/llm-run.ps1` | `llama-server` başlat/durdur, MTP, VRAM kapısı |
| `agent/asr-tools.py` | 16 kHz mono dönüştürme + Qwen3-ASR çıkarımı (akışlı) |
| `agent/tts-tools.py` | Takas edilebilir TTS: Chatterbox / Piper / SAPI |
| `agent/pipeline.ps1` | Boru hattı: ASR → LLM (akış) → cümle bölme → TTS |
| `agent/audio-capture.ps1` | winmm `mciSendString` ile bağımlılıksız kayıt |
| `scripts/`, `docs/`, `tests/` | kurulum/tanı, belgeler, pytest |

## 5. Gecikme bütçesi (hedef < 1000 ms)

| Aşama | Hedef | Yöntem |
|---|---|---|
| Endpoint | 0–200 ms | Bas-konuş = 0; VAD + ~200 ms eşik |
| STT | ≤ 400 ms (0.6B) / sınırda (1.7B) | Akışlı Qwen3-ASR |
| LLM ilk token | ≤ 250 ms | Yerleşik model + KV prefix cache |
| TTS ilk ses | ≤ 150 ms | Chatterbox/Piper, ilk cümlede |

## 6. Kritik tuzaklar

1. **Uygulama yalnızca gömülü PowerShell 7 ile çalışır.** `Start-ThreadJob` 5.1'de yoktur.
2. **`Start-ThreadJob -FilePath` içinde `$PSScriptRoot` boştur.** Kök `$JobData.root` ile taşınır.
3. **Windows PowerShell 5.1 BOM'suz `.ps1`'i ANSI okur.** 5.1 betikleri ASCII tut ya da UTF-8 BOM'lu kaydet.
4. **KV önbellek eşleşmesi.** Arayüzün mesaj dizisi sunucununkiyle bayt bayt aynı olmalı.
5. **`Start-DetachedProcess` kullan.** `Start-Process -Redirect…` çağıranın stdout'unu devralır.
6. **VRAM payı küçük tutulur.** 9B MTP kartın sınırında.
7. **MTP bayrağı yalnızca GGUF MTP katmanı taşıyorsa eklenir** (`Test-GgufHasMtp`).
8. **ASR/TTS CPU'yu paylaşır.** Aynı anda çalışmazlar (dinleme vs konuşma), ama gürültülü makinede ölçüm şart.

## 7. Değişiklik kontrol listesi

- [ ] MTP hâlâ açık mı? (Kesin kural)
- [ ] LLM hâlâ LITE (Huihui-Qwen3.5 9B Q5_K_M) mi?
- [ ] STT hâlâ Qwen3-ASR mi (whisper'a dönülmedi)?
- [ ] Dil modeli hâlâ yerleşik mi (boşaltılmıyor)?
- [ ] GPU'ya LLM dışında bir şey taşınmadı mı?
- [ ] TR ve ENG sürümleri tutarlı mı?
- [ ] `README.md`, `docs/mimari.md`, `docs/faz2-olcum-plani.md`, `docs/kararlar.md` güncel mi?

## 8. Değişiklik günlüğü

| Tarih | Değişiklik | Dosyalar |
|---|---|---|
| 2026-10-11 | STT whisper'dan **Qwen3-ASR-1.7B**'ye çekildi (Türkçe, akışlı, Apache-2.0); hız yedeği 0.6B. | README.md, AGENTS.md, docs/mimari.md, docs/faz2-olcum-plani.md, docs/kararlar.md |
| 2026-10-11 | Mimariye tur dizisi + sorumluluk tablosu; Faz 2 ölçüm planı. | docs/mimari.md, docs/faz2-olcum-plani.md |
| 2026-10-11 | Model MamidLabs LITE ile eşitlendi. | tümü |
| 2026-10-11 | Depo açıldı; plan yazıldı. | tümü |
