# Mimari

Bu belge, mamidChats Chatbot'un tasarımını, veri akışını ve **gecikme bütçesini** tanımlar.

## 1. Ana ilke

**GPU'da yalnızca dil modeli çalışır; STT ve TTS CPU'da çalışır.**

Sebep: 8 GB VRAM'de Qwen 3.5 9B MTP'li hâlde kartın sınırına oturur. STT (Qwen3-ASR) ve TTS'i
GPU'ya almak model takasını zorunlu kılar — bu da `<1 sn` hedefini öldürür. Bu yüzden iş bölümü
yapılır ve dil modeli **yerleşik** kalır.

## 2. Veri akışı

```
                 ┌─────────────────────────── CPU ───────────────────────────┐
                 │                                                            │
 Mikrofon ──► VAD/kayıt ──► Qwen3-ASR ──► metin                              │
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
    participant ASR as Qwen3-ASR (CPU)
    participant LLM as Qwen 3.5 9B (GPU, MTP)
    participant TTS as TTS (CPU)
    participant SP as Hoparlör

    U->>AC: konuşur
    AC->>AC: VAD / bas-konuş bitişi (0–200 ms)
    AC->>ASR: 16 kHz mono WAV
    ASR-->>LLM: metin (hedef ≤400 ms; 1.7B'de sınırda)
    LLM-->>TTS: ilk cümle (≤250 ms TTFT)
    TTS-->>SP: ilk ses (≤150 ms)
    Note over LLM,TTS: LLM kalan cümleleri yazmaya devam eder
    Note over U,SP: Kullanıcı konuşursa çalma anında durur (barge-in)
```

### 2.2 Bileşen sorumlulukları

| Bileşen | Sorumluluk | Girdi | Çıktı | Hata durumu |
|---|---|---|---|---|
| Ses yakalama | Kaydet, VAD/bitiş kararı | Mikrofon | 16 kHz mono WAV | Cihaz yok → bildir, turu iptal |
| ASR (Qwen3-ASR) | Konuşmayı yazıya çevir | WAV | Metin | Boş/anlamsız → "anlayamadım" |
| LLM (9B + MTP) | Yanıt üret (akış) | Metin + geçmiş | Token akışı | Sunucu yok → yeniden başlat |
| Boru hattı | Paralelleştir, cümleye böl | Token akışı | Cümleler | Zaman aşımı → kısmi yanıt |
| TTS | Cümleyi sese çevir | Cümle | Ses | Motor hatası → metne düş |
| Çalma | Ses çal, barge-in'de dur | Ses | Hoparlör | Cihaz yok → metne düş |
| Arayüz (WinForms) | Durum, geçmiş, mod | Olaylar | UI | — |

## 3. Gecikme bütçesi (hedef < 1000 ms)

| Aşama | Hedef | Yöntem |
|---|---|---|
| Endpoint | 0–200 ms | Bas-konuş = 0; VAD + ~200 ms eşik |
| STT (Qwen3-ASR) | ≤ 400 ms | Akışlı çıkarım; 0.6B hızlı, 1.7B sınırda |
| LLM ilk token | ≤ 250 ms | Yerleşik model + **KV prefix cache** |
| TTS ilk ses | ≤ 150 ms | Chatterbox/Piper, ilk cümlede |
| Çalma tamponu | ~50 ms | Küçük tampon |

> t₀ = son sözcük bitti · t₁ = ilk ses çıktı · Hedef `t₁ − t₀ < 1000 ms`

## 4. STT: Qwen3-ASR

Ses → yazı, **Qwen3-ASR** ile yapılır (whisper kullanılmaz).

| Alan | Değer |
|---|---|
| Model | **Qwen3-ASR-1.7B** (Qwen3-1.7B + projector + 300M AuT encoder) |
| Lisans | Apache-2.0 |
| Dil | 30 dil + 22 Çince lehçe; **Türkçe (tr) destekli** |
| Yetenek | Dil algılama (LID), **akışlı + çevrimdışı**, gürültü/BGM/söylenen ses dayanıklı |
| Boyut | fp16 ~4,7 GB · Q8 ~2,5 GB · Q4 ~1,3 GB |
| Nerede | **CPU** — saf C (`antirez/qwen-asr`) veya `qwen-asr` / vLLM |
| Yedek | **Qwen3-ASR-0.6B** (CPU tatlı noktası) |

- SOTA açık kaynak ASR; Whisper-large-v3'ü birçok benchmarkta geçer.
- **Akışlı çıkarım** ile kısmi metin erken üretilir → algılanan gecikme düşer.
- **Hız uyarısı:** CPU'da 1.7B gerçek zamanın ~4 katı (11 sn ses ~2,6 sn). Uzun cümlede `<1 sn`
  sınırda; **Qwen3-ASR-0.6B** (~8x) veya akışlı pencere daraltma ile telafi edilir. Faz 2'de ölçülür.
- Silero VAD ile konuşma bölütlenir (boş bölge filtresi).

## 5. LLM: Huihui-Qwen3.5 9B (LITE ile aynı) + MTP (daima açık)

| Alan | Değer |
|---|---|
| Model | **Huihui-Qwen3.5 9B Q5_K_M** (GGUF) |
| MTP | `mtp_inject.py` ile `blk.<N>.nextn.*` |
| Çalıştırma | `llama-server` + `--spec-type draft-mtp` |
| mmproj | İsteğe bağlı; ses-odaklı → **varsayılan yüklenmez** |

- **Yeniden indirme yok:** dosyalar MamidLabs kökünde mevcut.
- GPU'da **yerleşik**; turlar arasında boşaltılmaz.
- **MTP kayıpsız** (kabul edilen tokenlar hedef modelle doğrulanır); MamidLabs ölçümü ~2x hız.
- **KV prefix cache**: her turda yalnızca yeni tokenlar işlenir.

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
| GPU (8 GB) | Qwen 3.5 9B + MTP + KV cache (kartın sınırında) |
| CPU çekirdekleri | Qwen3-ASR (dinleme) **veya** TTS (konuşma) — sırayla |

## 8. Önerilen dosya yapısı

| Yol | İçerik |
|---|---|
| `mamidchats-desktop.ps1` | WinForms arayüzü, olay döngüsü |
| `agent/llm-run.ps1` | `llama-server`, MTP, VRAM kapısı |
| `agent/asr-tools.py` | Qwen3-ASR çıkarımı (akışlı) |
| `agent/tts-tools.py` | Chatterbox / Piper / SAPI |
| `agent/pipeline.ps1` | ASR → LLM (akış) → cümle → TTS |
| `agent/audio-capture.ps1` | winmm kayıt |

## 9. Riskler ve açık sorular

1. **Qwen3-ASR CPU hızı.** 1.7B `<1 sn` sınırda; 0.6B yedeği veya akış optimizasyonu gerekebilir.
2. **Endpoint sezgisi.** VAD agresif/yavaş dengesi; bas-konuş sıfırlar.
3. **Barge-in.** Yankı riski → kulaklık/yankı bastırma.
4. **TTS GPU payı.** Chatterbox GPU'ya alınırsa LLM Q4'e inmeli; ölçüm gerek.
5. **CPU çekişmesi.** ASR ve TTS aynı anda çalışmaz ama yüklü makinede ölçülmeli.
