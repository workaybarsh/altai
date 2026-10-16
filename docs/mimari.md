# Mimari

Bu belge, aybars_says'in (eski adı: mamidChats Chatbot) tasarımını, veri akışını ve **gecikme
bütçesini** tanımlar.

## 1. Ana ilke

**GPU'da yalnızca dil modeli çalışır; STT ve TTS CPU'da çalışır.**

Sebep: 8 GB VRAM'de Qwen 3.5 9B (imatrix Q5_K_M, MTP'li hâlde) kartın sınırına oturur. STT
(whisper.cpp) ve TTS'i GPU'ya almak model takasını zorunlu kılar — bu da `<1 sn` hedefini öldürür.
Bu yüzden iş bölümü yapılır ve dil modeli **yerleşik** kalır.

## 2. Veri akışı

```
                 ┌─────────────────────────── CPU ───────────────────────────┐
                 │                                                            │
 Mikrofon ──► VAD/kayıt ──► whisper.cpp ──► metin                            │
                 │                            │                              │
                 │                            ▼                              │
                 │                 ┌──── GPU: Qwen 3.5 9B (MTP) ────┐        │
                 │                 │  yanıt tokenları (akış)         │        │
                 │                 └────────────┬───────────────────┘        │
                 │                              ▼                            │
 Hoparlör ◄── çalma ◄── TTS (Chatterbox/Piper) ◄── ilk cümle ◄──┘             │
                 └────────────────────────────────────────────────────────────┘
```

**Boru hattı (paralel):** LLM ilk cümleyi üretir → hemen TTS'e gider → kullanıcı onu duyarken LLM
kalanı yazar. Toplam gecikme = en yavaş tek zincir.

### 2.1 Bir turun zaman çizelgesi

```mermaid
sequenceDiagram
    autonumber
    participant U as Kullanıcı
    participant AC as Ses yakalama (CPU)
    participant ASR as whisper.cpp (CPU)
    participant LLM as Qwen 3.5 9B (GPU, MTP)
    participant TTS as TTS (CPU)
    participant SP as Hoparlör

    U->>AC: konuşur
    AC->>AC: VAD / bas-konuş bitişi (0–200 ms)
    AC->>ASR: 16 kHz mono WAV
    ASR-->>LLM: metin (hedef ≤400 ms)
    LLM-->>TTS: ilk cümle (≤250 ms TTFT)
    TTS-->>SP: ilk ses (≤150 ms)
    Note over LLM,TTS: LLM kalan cümleleri yazmaya devam eder
    Note over U,SP: Kullanıcı konuşursa çalma anında durur (barge-in)
```

### 2.2 Bileşen sorumlulukları

| Bileşen | Sorumluluk | Girdi | Çıktı | Hata durumu |
|---|---|---|---|---|
| Ses yakalama | Kaydet, VAD/bitiş kararı | Mikrofon | 16 kHz mono WAV | Cihaz yok → bildir, turu iptal |
| ASR (whisper.cpp) | Konuşmayı yazıya çevir | WAV | Metin | Boş/anlamsız → "anlayamadım" |
| LLM (9B + MTP) | Yanıt üret (akış) | Metin + geçmiş | Token akışı | Sunucu yok → yeniden başlat |
| Boru hattı | Paralelleştir, cümleye böl | Token akışı | Cümleler | Zaman aşımı → kısmi yanıt |
| TTS | Cümleyi sese çevir | Cümle | Ses | Motor hatası → metne düş |
| Çalma | Ses çal, barge-in'de dur | Ses | Hoparlör | Cihaz yok → metne düş |
| Arayüz (WinForms) | Durum, geçmiş, mod | Olaylar | UI | — |

## 3. Gecikme bütçesi (hedef < 1000 ms)

| Aşama | Hedef | Yöntem |
|---|---|---|
| Endpoint | 0–200 ms | Bas-konuş = 0; VAD + ~200 ms eşik |
| STT (whisper.cpp) | ≤ 400 ms | `large-v3-turbo`; gerekirse `medium`/`small` |
| LLM ilk token | ≤ 250 ms | Yerleşik model + **KV prefix cache** |
| TTS ilk ses | ≤ 150 ms | Chatterbox/Piper, ilk cümlede |
| Çalma tamponu | ~50 ms | Küçük tampon |

> t₀ = son sözcük bitti · t₁ = ilk ses çıktı · Hedef `t₁ − t₀ < 1000 ms`

## 4. STT: whisper.cpp

Ses → yazı, **whisper.cpp** ile yapılır (Qwen3-ASR kullanılmaz).

> **Tarihçe:** İlk planda STT için whisper.cpp (`large-v3-turbo`) seçilmişti; bir ara
> **Qwen3-ASR-1.7B**'ye geçildi; **2026-10-16**'da whisper.cpp'ye geri dönüldü. Gerekçe ve
> alternatifler için bkz. [`kararlar.md`](kararlar.md) → karar #11.

| Alan | Değer |
|---|---|
| Motor | **whisper.cpp** (MIT, C/C++) |
| Model | **large-v3-turbo** (varsayılan) |
| Lisans | MIT (motor ve ağırlıklar) |
| Dil | Çok dilli; **Türkçe (tr) destekli** |
| Yetenek | Çevrimdışı toplu çıkarım; akışlı/parçalı kullanım mümkün |
| Boyut | turbo ~1,6 GB (Q5) · medium ~1,5 GB · small ~0,5 GB |
| Nerede | **CPU** — `whisper.cpp` / `whisper-cli` |
| Yedek | `medium`, `small` (daha hızlı, biraz daha zayıf) |

- Olgun, yaygın; CPU thread ayarıyla iyi ölçeklenir.
- **Hız uyarısı:** `large-v3-turbo` CPU'da tipik cümlede ~0,2–0,4 sn. Uzun cümlede `<1 sn` sınırda;
  VAD ile bölütleme + parça paralelliği telafi eder. Gerekirse `medium`/`small`'a inilir. Faz 2'de ölçülür.
- Silero VAD ile konuşma bölütlenir (boş bölge filtresi).

## 5. LLM: Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M + MTP (daima açık)

| Alan | Değer |
|---|---|
| Model | **Huihui-Qwen3.5-9B-abliterated i1-Q5_K_M** (GGUF, imatrix) |
| Dosya | `Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf` (~6,6 GB) |
| HF deposu | `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF` |
| Taban | `huihui-ai/Huihui-Qwen3.5-9B-abliterated` |
| MTP | `mtp_inject.py` ile `blk.<N>.nextn.*` |
| Çalıştırma | `llama-server` + `--spec-type draft-mtp` |
| mmproj | İsteğe bağlı; ses-odaklı → **varsayılan yüklenmez** |

- GPU'da **yerleşik**; turlar arasında boşaltılmaz.
- **MTP kayıpsız** (kabul edilen tokenlar hedef modelle doğrulanır); MamidLabs ölçümü ~2x hız.
- **KV prefix cache**: her turda yalnızca yeni tokenlar işlenir.
- **Doğrulanacak:** imatrix quant ile MTP katmanı uyumu (bkz. [`kararlar.md`](kararlar.md) açık kararlar).

## 6. TTS: takas edilebilir katman

| Motor | Doğallık | Türkçe | CPU'da gerçek zamanlı | Lisans | Rol |
|---|---|---|---|---|---|
| **Chatterbox Multilingual v3** | En yüksek | ✅ | ❌ (GPU ister) | MIT | **Birincil (gerçekçi)** |
| **Piper** | Orta | ✅ | ✅ | GPL-3.0 | Hızlı/yedek |
| XTTS-v2 | Yüksek | ✅ | ❌ | Ticari dışı | Alternatif |
| Kokoro / F5-TTS | Yüksek | ❌ | ✅ / ❌ | Apache / CC-BY-NC | TR yok → elenir |
| Windows SAPI | Düşük | ✅ | ✅ | — | Son çare |

- Varsayılan **Chatterbox v3**; GPU'da ~2–3 GB → LLM Q4 ile ~8 GB (ölçüm şart).
- GPU sıkışırsa **Piper** (CPU) canlı moda düşer.
- Chatterbox çıktıları PerTh filigranı taşır (MIT, duyulmaz) — engel değil.

## 7. Kaynak bütçesi (8 GB VRAM)

| Kaynak | Kullanım |
|---|---|
| GPU (8 GB) | Huihui-Qwen3.5-9B i1-Q5_K_M (~6,6 GB) + MTP + KV cache (kartın sınırında) |
| CPU çekirdekleri | whisper.cpp (dinleme) **veya** TTS (konuşma) — sırayla |

> **Not:** i1-Q5_K_M tek başına ~6,6 GB; MTP + KV cache ile 8 GB'a çok yaklaşır. Sıkışırsa
> **i1-Q4_K_M** (~5,6 GB) değerlendirilir.

## 8. Önerilen dosya yapısı

| Yol | İçerik |
|---|---|
| `mamidchats-desktop.ps1` | WinForms arayüzü, olay döngüsü |
| `agent/llm-run.ps1` | `llama-server`, MTP, VRAM kapısı |
| `agent/asr-tools.py` | whisper.cpp çıkarımı |
| `agent/tts-tools.py` | Chatterbox / Piper / SAPI |
| `agent/pipeline.ps1` | ASR → LLM (akış) → cümle → TTS |
| `agent/audio-capture.ps1` | winmm kayıt |

## 9. Riskler ve açık sorular

1. **whisper.cpp CPU hızı.** `large-v3-turbo` `<1 sn` için genelde yeterli; uzun cümlede `medium`/`small`
   yedeği veya akış optimizasyonu gerekebilir.
2. **MTP + imatrix quant uyumu.** Yeni quant dosyasında MTP katmanı sorun çıkarırsa orijinal
   `huihui-ai` GGUF'a dönülür.
3. **Endpoint sezgisi.** VAD agresif/yavaş dengesi; bas-konuş sıfırlar.
4. **Barge-in.** Yankı riski → kulaklık/yankı bastırma.
5. **TTS GPU payı.** Chatterbox GPU'ya alınırsa LLM Q4'e inmeli; ölçüm gerek.
6. **VRAM sınırı.** i1-Q5_K_M + MTP + KV 8 GB'ın sınırında; gerçek ölçüm şart.
