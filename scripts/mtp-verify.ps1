<#
    MTP status and injection tool (Altai)

    What it does:
      - Checks whether a GGUF carries an MTP/nextn header (agent/mtp-status.py)
      - With -Inject, adds the MTP header from the base HF repository if it is
        missing (agent/mtp_inject.py)

    Usage:
      pwsh -File scripts/mtp-verify.ps1 -Gguf "models\...i1-Q5_K_M.gguf"
      pwsh -File scripts/mtp-verify.ps1 -Gguf "models\...i1-Q5_K_M.gguf" -Inject

    Note: texts are kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).
    Python code is not passed via -c (PS 5.1 breaks embedded quotes); separate .py files are called.
#>
param(
    [Parameter(Mandatory = $true)][string]$Gguf,
    [string]$Repo = 'huihui-ai/Huihui-Qwen3.5-9B-abliterated',
    [switch]$Inject
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$durumPy = Join-Path $root 'agent\mtp-status.py'
$injectPy = Join-Path $root 'agent\mtp_inject.py'

if (-not (Test-Path -LiteralPath $Gguf)) { throw "GGUF not found: $Gguf" }
if (-not (Test-Path -LiteralPath $durumPy)) { throw "mtp-status.py not found: $durumPy" }
if (-not (Test-Path -LiteralPath $injectPy)) { throw "mtp_inject.py not found: $injectPy" }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw 'Python not found (python or py must be on PATH).' }

$GgufFull = (Resolve-Path -LiteralPath $Gguf).Path

function Get-MtpStatus($path) {
    $raw = & $python $durumPy $path
    if ($LASTEXITCODE -ne 0) { throw "mtp-status.py failed (exit code: $LASTEXITCODE)" }
    return ($raw | ConvertFrom-Json)
}

Write-Host "GGUF : $GgufFull"
$st = Get-MtpStatus $GgufFull
Write-Host ("Size: {0} MB | GGUF v{1} | Architecture: {2}" -f $st.size_mb, $st.gguf_version, $st.arch)
Write-Host ("block_count: {0} | nextn_predict_layers: {1}" -f $st.block_count, $st.nextn_predict_layers)
Write-Host ("Tensors: {0} (nextn: {1})" -f $st.tensor_count, $st.nextn_tensor_count)
Write-Host ("Has MTP: {0}" -f $st.has_mtp)

if ($st.has_mtp) {
    Write-Host 'RESULT: MTP ready. --spec-type draft-mtp can be added safely.' -ForegroundColor Green
    exit 0
}

Write-Host 'RESULT: NO MTP. If --spec-type draft-mtp is passed, llama.cpp will not start.' -ForegroundColor Yellow

if (-not $Inject) {
    Write-Host 'Run again with -Inject to inject.' -ForegroundColor Yellow
    exit 2
}

Write-Host "Injecting MTP header; source: $Repo"
& $python $injectPy $GgufFull $Repo
if ($LASTEXITCODE -ne 0) { throw "Injection failed (exit code: $LASTEXITCODE)" }

$st2 = Get-MtpStatus $GgufFull
if (-not $st2.has_mtp) { throw 'MTP still not visible after injection.' }
Write-Host ("RESULT: MTP added. block_count: {0} | nextn_predict_layers: {1} | nextn tensors: {2}" -f $st2.block_count, $st2.nextn_predict_layers, $st2.nextn_tensor_count) -ForegroundColor Green
exit 0
