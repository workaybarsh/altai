# MTP (Multi-Token Prediction) — Doğrulama ve Enjeksiyon Planı

> Bu belge, "**MTP daima açık**" kesin kuralının **gerçekten çalışması** için gereken
> doğrulama ve geri ekleme adımlarını tanımlar.

## 1. Neden bu belge

Quantize edilmiş GGUF dosyalarında **MTP (nextn) başlığı bulunmaz**: HF → GGUF dönüştürücüsü
MTP katmanlarını dışarıda bırakır. Bu yüzden `--spec-type draft-mtp` bayrağı modele verilirse
llama.cpp **açılmaz**. MTP'yi kullanmak için başlığın GGUF'a **geri enjekte edilmesi** gerekir.

## 2. Doğrulanmış bulgular (2026-10-16)

| Kontrol | Sonuç | Kanıt |
|---|---|---|
| Hedef GGUF: `mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF` → `i1-Q5_K_M.gguf` | **MTP YOK** | Başlıkta `nextn` = 0 eşleşme; `nextn_predict_layers` yok |
| Kaynak repo: `huihui-ai/Huihui-Qwen3.5-9B-abliterated` | **15 MTP tensoru var** | `mtp.*` tensorları shard 2/3/4'te mevcut |
| Kaynak tensorlar ↔ `mtp_inject.py` MAP | **Birebir uyuşuyor** | Aşağıdaki 15 isim |

Yani: **hedef model MTP'yi içermiyor, kaynak MTP'yi sağlıyor → enjeksiyon gerekli ve mümkün.**

### 2.1 Kaynak MTP tensorları (15 adet)

```
mtp.fc.weight
mtp.layers.0.input_layernorm.weight
mtp.layers.0.post_attention_layernorm.weight
mtp.layers.0.self_attn.q_proj.weight
mtp.layers.0.self_attn.k_proj.weight
mtp.layers.0.self_attn.v_proj.weight
mtp.layers.0.self_attn.o_proj.weight
mtp.layers.0.self_attn.q_norm.weight
mtp.layers.0.self_attn.k_norm.weight
mtp.layers.0.mlp.gate_proj.weight
mtp.layers.0.mlp.down_proj.weight
mtp.layers.0.mlp.up_proj.weight
mtp.pre_fc_norm_embedding.weight
mtp.pre_fc_norm_hidden.weight
mtp.norm.weight
```

## 3. Çözüm: `mtp_inject.py` (MamidLabs'ta kanıtlı araç)

MamidLabs'ta aynı sorun çözülmüş durumda. Aynı işçi yeniden kullanılır.

**Ne yapar:**
1. Kaynak HF deposunun safetensors başlığını HTTP menzilli indirme ile okur.
2. Yalnızca **15 MTP tensorunu** çeker (tüm modeli değil).
3. Mevcut GGUF'un sonuna `blk.<N>.nextn.*` adıyla ekler.
4. Üst veriye `qwen35.nextn_predict_layers = 1` ekler ve `qwen35.block_count`'u +1 yapar.
5. 1-B (F32) norm tensorlerine **+1** uygular (llama.cpp GGUF normalizasyon kuralı).
6. Ana model ağırlıklarına **dokunmaz** → kayıpsız.

**Özellikleri:** mimari kontrolü (`qwen35` olmalı), idempotent (`has_mtp` ile zaten varsa atlar),
atomik yazım (tmp + `os.replace`), ağ dalgalanmasına karşı 4 deneme.

## 4. Uygulama adımları (somut)

```powershell
# 1) Hedef GGUF indirilir (boyut doğrulamalı)
#    models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf

# 2) MTP başlığı enjekte edilir (kaynak = taban abliterated repo)
python mtp_inject.py `
  "models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf" `
  "huihui-ai/Huihui-Qwen3.5-9B-abliterated"

# 3) Doğrulanır: has_mtp == True
# 4) Sunucu MTP ile başlatılır (aşağıdaki bayraklarla)
```

Programlama arayüzünden:

```python
from mtp_inject import ensure_mtp, has_mtp
ensure_mtp(target_gguf, {'repo': 'huihui-ai/Huihui-Qwen3.5-9B-abliterated'})
assert has_mtp(target_gguf)
```

## 5. Kanıt / kabul testleri (geçmeden iş bitmiş sayılmaz)

- [ ] **T1 — Enjeksiyon:** `has_mtp(gguf) == True` (öncesi `False`).
- [ ] **T2 — Üst veri:** `general.architecture == qwen35`; `nextn_predict_layers == 1`;
      `block_count` eski değer + 1.
- [ ] **T3 — Sunucu açılışı:** `llama-server ... --spec-type draft-mtp` hatasız başlar
      (MTP'siz verilince açılmaz — bu da negatif kontrol).
- [ ] **T4 — MTP etkin:** sunucu günlüğünde MTP/draft-spec yolu etkin görünür.
- [ ] **T5 — Hız kazancı:** aynı istemle MTP **açık vs kapalı** throughput ölçülür; açık ≥ kapalı
      (beklenen ~2x mertebesi, 8 GB'ta daha az).
- [ ] **T6 — Kayıpsızlık:** MTP açık/kapalı aynı istemde anlamlı çıktı farkı yok (kayıpsız).
- [ ] **T7 — Yeniden başlatma:** uygulama kapanıp açılınca enjeksiyon **tekrarlanmaz** (idempotent).

## 6. llama-server bayrakları (hedef)

```
llama-server
  -m models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf
  --spec-type draft-mtp          # MTP varsa; yoksa ÜÇÜNCÜ de eklenmez
  -c 32768
  -ngl 99
  ...
```

- Bayrak **yalnızca GGUF gerçekten MTP taşıyorsa** eklenir (`Test-GgufHasMtp` / `gguf_has_mtp`).
- llama.cpp yapısı sabitlenir (MamidLabs ile aynı: **b10998**). Bayrak adı yapı sürümüne bağlıdır
  (llama.cpp geçmişte `--spec-type` argümanını yeniden adlandırdı); bu yüzden **sürüm sabit** tutulur.

## 7. VRAM notu

MTP başlığı **ek bir transformer bloğu** demektir (~yüzlerce MB) + draft bağlamı. Hedef kart 8 GB'ta
`i1-Q5_K_M` (~6,6 GB) + MTP + KV zaten sınırda; **enjeksiyon sonrası VRAM yeniden ölçülmelidir**.
Sıkışırsa:

1. `i1-Q4_K_M` (~5,6 GB) — quant düşür,
2. KV cache'i `q4_0`'a al,
3. `-c` bağlamı düşür.

## 8. Riskler ve yedekler

| Risk | Yedek |
|---|---|
| Enjeksiyon sonrası GGUF bozulur | Orijinal dosyayı yeniden indir; enjeksiyonu tekrarla |
| `qwen35` mimarisi tanınmaz / `block_count` yok | Kaynak `huihui-ai` GGUF'una dön |
| imatrix quant ile nextn beklenmedik davranır | Orijinal `huihui-ai` **static** Q5_K_M kullan |
| MTP 8 GB'ta sığmaz | `settings.mtp = false` + `i1-Q4_K_M` |
| llama.cpp bayrak adı değişir | Yapıyı **b10998**'e sabitle |

## 9. Sonuç

- **MTP bu projede opsiyonel değil, zorunlu.** Hedef quant GGUF'ta MTP yok → `mtp_inject.py` şart.
- Kaynak tensorlar **doğrulandı**; mekanizma MamidLabs'ta **kanıtlı**.
- Geçiş kriteri: **T1–T7 testleri geçmeli.**
