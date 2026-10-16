<#
    MTP durum ve enjeksiyon araci (aybars_says)

    Ne yapar:
      - Bir GGUF'un MTP/nextn basligi tasiyip tasimadigini denetler (has_mtp)
      - Mimari, block_count, nextn_predict_layers, tensor sayilarini raporlar
      - -Inject verilirse, eksikse MTP basligini taban HF deposundan enjekte eder

    Kullanim:
      pwsh -File scripts/mtp-dogrula.ps1 -Gguf "models\...i1-Q5_K_M.gguf"
      pwsh -File scripts/mtp-dogrula.ps1 -Gguf "models\...i1-Q5_K_M.gguf" -Inject

    Not: Metinler ASCII tutuldu (Windows PowerShell 5.1 BOM'suz .ps1'i ANSI okur).
#>
param(
    [Parameter(Mandatory = $true)][string]$Gguf,
    [string]$Repo = 'huihui-ai/Huihui-Qwen3.5-9B-abliterated',
    [switch]$Inject
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$agentDir = Join-Path $root 'agent'
$tool = Join-Path $agentDir 'mtp_inject.py'

if (-not (Test-Path -LiteralPath $Gguf)) { throw "GGUF bulunamadi: $Gguf" }
if (-not (Test-Path -LiteralPath $tool)) { throw "mtp_inject.py bulunamadi: $tool" }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw 'Python bulunamadi (python ya da py PATH uzerinde olmali).' }

$GgufFull = (Resolve-Path -LiteralPath $Gguf).Path

$statusCode = @'
import sys, os, json
sys.path.insert(0, sys.argv[1])
import mtp_inject as m
p = sys.argv[2]
ver, meta, tensors, _ds = m.read_header(p)
d = {k: v for k, _t, v in meta}
out = {
    "size_mb": round(os.path.getsize(p) / 1048576, 1),
    "gguf_version": ver,
    "arch": d.get("general.architecture"),
    "block_count": d.get("qwen35.block_count"),
    "nextn_predict_layers": d.get("qwen35.nextn_predict_layers"),
    "tensor_count": len(tensors),
    "nextn_tensor_count": sum(1 for t in tensors if ".nextn." in t[0]),
    "has_mtp": m.has_mtp(p),
}
print(json.dumps(out))
'@

function Get-Durum($path) {
    $json = & $python -c $statusCode $agentDir $path
    return ($json | ConvertFrom-Json)
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

$injectCode = @'
import sys
sys.path.insert(0, sys.argv[1])
from mtp_inject import ensure_mtp
ensure_mtp(sys.argv[2], {"repo": sys.argv[3]})
'@

Write-Host "MTP basligi enjekte ediliyor; kaynak: $Repo"
& $python -c $injectCode $agentDir $GgufFull $Repo
if ($LASTEXITCODE -ne 0) { throw "Enjeksiyon basarisiz (cikis kodu: $LASTEXITCODE)" }

$st2 = Get-Durum $GgufFull
if (-not $st2.has_mtp) { throw 'Enjeksiyon sonrasi MTP hala gorunmuyor.' }
Write-Host ("SONUC: MTP eklendi. block_count: {0} | nextn_predict_layers: {1} | nextn tensor: {2}" -f $st2.block_count, $st2.nextn_predict_layers, $st2.nextn_tensor_count) -ForegroundColor Green
exit 0
