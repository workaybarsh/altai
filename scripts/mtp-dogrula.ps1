<#
    MTP durum ve enjeksiyon araci (aybars_says)

    Ne yapar:
      - Bir GGUF'un MTP/nextn basligi tasiyip tasimadigini denetler (agent/mtp-durum.py)
      - -Inject verilirse, eksikse MTP basligini taban HF deposundan ekler
        (agent/mtp_inject.py)

    Kullanim:
      pwsh -File scripts/mtp-dogrula.ps1 -Gguf "models\...i1-Q5_K_M.gguf"
      pwsh -File scripts/mtp-dogrula.ps1 -Gguf "models\...i1-Q5_K_M.gguf" -Inject

    Not: Metinler ASCII tutuldu (Windows PowerShell 5.1 BOM'suz .ps1'i ANSI okur).
    Python kodu -c ile gecirilmez (PS 5.1 gomulu tirnaklari bozar); ayri .py dosyalari cagirilir.
#>
param(
    [Parameter(Mandatory = $true)][string]$Gguf,
    [string]$Repo = 'huihui-ai/Huihui-Qwen3.5-9B-abliterated',
    [switch]$Inject
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$durumPy = Join-Path $root 'agent\mtp-durum.py'
$injectPy = Join-Path $root 'agent\mtp_inject.py'

if (-not (Test-Path -LiteralPath $Gguf)) { throw "GGUF bulunamadi: $Gguf" }
if (-not (Test-Path -LiteralPath $durumPy)) { throw "mtp-durum.py bulunamadi: $durumPy" }
if (-not (Test-Path -LiteralPath $injectPy)) { throw "mtp_inject.py bulunamadi: $injectPy" }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw 'Python bulunamadi (python ya da py PATH uzerinde olmali).' }

$GgufFull = (Resolve-Path -LiteralPath $Gguf).Path

function Get-Durum($path) {
    $raw = & $python $durumPy $path
    if ($LASTEXITCODE -ne 0) { throw "mtp-durum.py hata verdi (cikis kodu: $LASTEXITCODE)" }
    return ($raw | ConvertFrom-Json)
}

Write-Host "GGUF : $GgufFull"
$st = Get-Durum $GgufFull
Write-Host ("Boyut: {0} MB | GGUF v{1} | Mimari: {2}" -f $st.size_mb, $st.gguf_version, $st.arch)
Write-Host ("block_count: {0} | nextn_predict_layers: {1}" -f $st.block_count, $st.nextn_predict_layers)
Write-Host ("Tensor: {0} (nextn: {1})" -f $st.tensor_count, $st.nextn_tensor_count)
Write-Host ("MTP var mi: {0}" -f $st.has_mtp)

if ($st.has_mtp) {
    Write-Host 'SONUC: MTP hazir. --spec-type draft-mtp guvenle eklenebilir.' -ForegroundColor Green
    exit 0
}

Write-Host 'SONUC: MTP YOK. --spec-type draft-mtp verilirse llama.cpp acilmaz.' -ForegroundColor Yellow

if (-not $Inject) {
    Write-Host 'Enjekte etmek icin tekrar calistir: -Inject' -ForegroundColor Yellow
    exit 2
}

Write-Host "MTP basligi enjekte ediliyor; kaynak: $Repo"
& $python $injectPy $GgufFull $Repo
if ($LASTEXITCODE -ne 0) { throw "Enjeksiyon basarisiz (cikis kodu: $LASTEXITCODE)" }

$st2 = Get-Durum $GgufFull
if (-not $st2.has_mtp) { throw 'Enjeksiyon sonrasi MTP hala gorunmuyor.' }
Write-Host ("SONUC: MTP eklendi. block_count: {0} | nextn_predict_layers: {1} | nextn tensor: {2}" -f $st2.block_count, $st2.nextn_predict_layers, $st2.nextn_tensor_count) -ForegroundColor Green
exit 0
