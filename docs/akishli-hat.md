# Akışlı hat (streaming) — ilk sesi erken çıkarma

> Amaç: `pipeline.ps1`'in toplu akışında **ilk ses** ancak LLM yanıtı bittikten *ve* tüm cümleler
> sentezlendikten sonra çıkıyor. Akışlı hatta ise LLM tokenları akarken **ilk cümle** oluşur
> oluşmaz TTS'e gider ve ses, yanıtın kalanı yazılırken **çalmaya başlar** (boru hattı ilkesi #7).

## 1. Sorun (toplu akış)

```
ASR (~10 sn) → LLM tamamlanana kadar bekle (~3-5 sn) → cümlelere böl → TTS toplu (tüm cümleler, ~9-12 sn) → çal
                                                                                                          ▲
                                                                                          ilk ses BURADA = tur sonu
```

Yani **ilk ses gecikmesi ≈ tur süresi** (~20-30 sn). Kullanıcı bu süre boyunca sessizlik duyar.

## 2. Akışlı hat

```
ASR → [LLM SSE akışı] ──ilk cümle──> TTS (tek cümle) ──> hemen ÇAL (arka plan)
           │                                                          ▲
           └── kalan cümleler bu sırada üretilirken ───────────────────┘  ilk ses ≈ ASR + ilk cümle + TTS(1 cümle)
```

İlk ses, yanıtın **tamamı** beklenmeden çıkar; LLM'in kalanı yazılırken ve sonraki cümleler
sentezlenirken ses çalar (örtüşme).

## 3. Bileşenler

| Dosya | Rol |
|---|---|
| `agent/llm-stream.py` | Motor: llama-server SSE akışı → kademeli cümle bölme → TTS sunucusuna cümle cümle istek → arka planda oynatma (`winsound`). Zaman damgalı JSON üretir. Bağımlılık yok (stdlib). |
| `agent/pipeline-stream.ps1` | İnce sarmalayıcı: ASR (opsiyonel; `-Text` ile atlanır) + akışlı tur + özet + `-Play`. |
| `scripts/tts-server.ps1` | **Zorunlu**: akışlı hat kalıcı TTS sunucusuna bağlanır (`-TtsServerUrl`); cümle başına istek atar. |
| `tests/test_llm_stream.py` | Cevrimdışı testler: cümle bölme, `reasoning_content` ayrımı, uçtan uca (sahte LLM SSE + sahte TTS). |

Kullanım:

```powershell
pwsh -File agent\pipeline-stream.ps1 -Text "Merhaba, nasilsin?" -TtsServerUrl http://127.0.0.1:8082 -Play
pwsh -File agent\pipeline-stream.ps1 -Wav kayit.wav -AsrServerUrl http://127.0.0.1:8081 `
     -TtsServerUrl http://127.0.0.1:8082 -Play
```

## 4. Tasarım ayrıntıları

- **`reasoning_content` yok sayılır.** Düşünme açıkken (`enable_thinking`) model önce düşünme
  tokenları üretir; bunlar cümle bölmeye **girmez** (yoksa düşünme metni sesli okunurdu).
  `answer` yalnızca `content` parçalarından oluşur.
- **Kademeli cümle bölme** (`SentenceBuffer`):
  - kesin son: `.!?…` + boşluk/satır sonu;
  - `force_chars` (varsayılan 180) aşılırsa son boşluktan **zorla** böl (uzun cümleyi bekletme);
  - `soft_chars` (varsayılan 120) aşılırsa `, ; :` varsa oradan erken böl (ilk sesi öne çeker);
  - `min_chars` altındaki parça bir sonrakiyle birleştirilir.
- **Sembol-only cümleler gönderilmez** (`is_speakable`): harf/rakam yoksa TTS'e hiç gitmez
  (Chatterbox bu girdide çöküyordu — bkz. `tts-kiyaslama.md` §11).
- **Oynatma arka planda** (thread + kuyruk): ses çalarken akış okunmaya ve sonraki cümleler
  sentezlenmeye devam eder (geri basınç olmaz).
- **Zaman damgaları** (`--json-out`): `first_token_seconds`, `first_sentence_seconds`,
  `first_audio_seconds`, `llm_seconds`, `total_seconds` + cümle başına `llm_at` / `tts_seconds` /
  `ready_at` / `retried`.

## 5. Ölçüm yöntemi

- Kalıcı sunucular açık (`tts-server` 8082 + `llama-server` 8080, MTP); model yüklemesi tek.
- Aynı metin girdisi (`-Text`) → ASR devre dışı, yalnız **LLM + TTS** kıyaslanır.
- Karşılaştırma: (A) `pipeline.ps1` toplu, (B) `pipeline-stream.ps1` akışlı.
- "İlk ses": toplu modda tur sonu (toplu TTS bekler), akışlı modda `first_audio_seconds`.

<!-- OLCUM-SONUC -->
### 5.1 Ölçüm sonucu (2026-10-18 · Ryzen 5 3600 · RTX 5060 Ti 16 GB · profil B)

Aynı istem, `-Text` (ASR kapalı, yalnız LLM + TTS); üç kalıcı sunucu açık, model yüklemesi yok:

| Koşu | İlk token | İlk cümle | **İlk ses** | Tur sonu |
|---|---|---|---|---|
| **A) Toplu** (`pipeline.ps1`) | — | — | **18,8 sn** (= tur sonu) | 18,8 sn |
| **B) Akışlı** #1 | 0,26 sn | 0,53 sn | **7,60 sn** | 18,69 sn |
| **B) Akışlı** #2 | 0,28 sn | 0,49 sn | 18,06 sn ⚠️ *(guard retry)* | 28,16 sn |
| **B) Akışlı** #3 | 0,26 sn | 0,68 sn | **7,05 sn** | 23,07 sn |
| **C) Akışlı, düşünme açık** | 0,29 sn | 3,98 sn | **9,52 sn** | 21,48 sn |

Uçtan uca (gerçek ASR ile, `-Wav`; whisper turbo CPU):

| Koşu | ASR | İlk token | İlk ses (motorda) | Tur sonu |
|---|---|---|---|---|
| **E) Akışlı** | 5,24 sn ses → **9,91 sn** (RTF 1,89) | 0,37 sn | 13,40 sn ⚠️ *(guard retry)* | 23,82 sn |

**Okunuşu:**
- Guard **tetiklenmediğinde** akışlı hat ilk sesi **~2,5×** öne çekiyor (7,0–7,6 sn ↔ 18,8 sn);
  en büyük kazanç, asıl darboğaz olan "yanıtın tamamını bekle" adımının kalkmasıdır.
- Düşünme açıkken ilk **cümle** geç gelir (3,98 sn) çünkü model önce düşünür; ilk **parça**
  yine 0,29 sn'de gelir ama `reasoning_content` cümle bölmeye girmez (doğru davranış).
- ⚠️ **Kısa cümle + guard retry** ilk sesi 13–18 sn'ye itebiliyor (B#2, E): guard sesin süre
  sınırını aştığını görüp cümleyi ikinci kez üretiyor ve **iki üretim de uzun** kalıyor
  (`"Harika!"` → 4,48 sn). Uç enerjisi analizi (`logs\tail-energy.py`): kuyruk **sessizlik değil,
  fazladan konuşma** (zarf: `… 1794 229 5153 3055 … 2000 7645`) → sessizlik kırpma çözmez.
- **Dayanıklılık (ölçüm sırasında gerçek olay):** iki koşuda `ConnectionResetError`
  (`WinError 10054`, Windows loopback) alındı; motor **şeffaf şekilde yeniden denedi** ve tur
  tamamlandı. Yol/aynı hat sonrası `out` alanı 3/3 WAV'ı doğru buldu (aşağıdaki tuzak düzeltmesi).


## 6. Bilinen sınırlar / sonraki adımlar

- Cümle başına bir TTS isteği → cümle sayısı kadar istek; uzun yanıtta toplam TTS süresi toplu
  moda göre biraz artabilir (ama **ilk ses** çok erken gelir).
- Cümle sınırı **tahmini**dir (noktalama/uzunluk sezgisi); markdown/emoji içeren yanıtlarda
  TTS'e gitmeden önce temizlik gerekebilir (şimdilik yalnız sembol-only atlanır).
- İlk ses hâlâ **ASR** ile sınırlı (CPU'da ~10 sn). Gerçek `<1 sn` için ASR'de ya model/küçültme
  ya da GPU gerekir (açık karar — `kararlar.md` #19).
- ⚠️ **Kısa cümle + guard retry:** guard ses sınırı aşılırsa cümleyi ikinci kez üretir; kısa
  cümlelerde iki üretim de uzun kalabiliyor → ilk ses 13–18 sn'ye çıkıyor. Seçenekler: kısa
  cümlede (ör. <20 harf) retry'ı kapatmak/sınırı tabanlamak, en kısayı 3 üretimden seçmek veya
  çok kısa ünlemler için hazır (önceden üretilmiş) ses kullanmak. **Ölçülecek iş.**
- **Dayanıklılık:** Windows loopback'te nadir `WinError 10054` reset'i olabiliyor → cümle TTS'i
  **2 kez** denenir (sentez idempotent); LLM akışı ortada koparsa **eldeki cümlelerle devam edilir**
  ve durum `stream_error` alanında bildirilir. Tek cümlenin TTS'i patlarsa tur düşmez
  (`failed_sentences`).
- Ses çalma `winsound` (Windows); uygulama katmanı kendi ses motorunu kullanabilir.
