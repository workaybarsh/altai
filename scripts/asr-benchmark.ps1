<#
    Phase 2 ASR measurement harness (Altai)

    Runs the whisper.cpp pipeline over a folder of WAV files, collects latency/RTF and
    writes `logs\phase2-asr-results.json`. The real work lives in `agent/asr-tools.py`; this
    script is only a thin wrapper that finds and calls Python.

    Usage:
      pwsh -File scripts/asr-benchmark.ps1 -WavDir "tests\assets" -Model "models\ggml-large-v3-turbo-q5_0.bin"
      pwsh -File scripts/asr-benchmark.ps1 -WavDir "tests\assets" -Model "..." -Repeat 10 -Threads 12
      pwsh -File scripts/asr-benchmark.ps1 -WavDir "tests\assets" -ServerUrl http://127.0.0.1:8081

    Note: texts are kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).
#>
param(
    [string]$Model = '',
    [Parameter(Mandatory = $true)][string]$WavDir,
    [string]$Whisper = '',
    [string]$ServerUrl = '',
    [string]$Language = 'tr',
    [int]$Threads = 0,
    [int]$Repeat = 10,
    [string]$Out = 'logs\phase2-asr-results.json'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $root 'agent\asr-tools.py'

if (-not (Test-Path -LiteralPath $tool)) { throw "asr-tools.py not found: $tool" }
if (-not $ServerUrl -and -not $Model) { throw '-Model or -ServerUrl is required.' }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw 'Python not found (python or py must be on PATH).' }

$args = @($tool, '--dir', $WavDir, '--lang', $Language, '--repeat', $Repeat, '--out', $Out)
if ($ServerUrl) { $args += @('--server-url', $ServerUrl) } else { $args += @('--model', $Model) }
if ($Whisper) { $args += @('--whisper', $Whisper) }
if ($Threads -gt 0) { $args += @('--threads', $Threads) }

Write-Host "ASR measurement: $WavDir (repeat=$Repeat, lang=$Language)"
& $python @args
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host "Measurement did not complete (exit code: $code). See the JSON above." -ForegroundColor Yellow
    exit $code
}

$json = Get-Content -LiteralPath (Join-Path $root $Out) -Raw | ConvertFrom-Json
Write-Host ''
Write-Host ("{0,-32} {1,9} {2,9} {3,8} {4,10}" -f 'FILE', 'AUDIO(s)', 'ASR(s)', 'RTF', 'INFER(s)')
foreach ($r in $json.results) {
    Write-Host ("{0,-32} {1,9} {2,9} {3,8} {4,10}" -f (Split-Path -Leaf $r.file), $r.audio_seconds, $r.median_asr, $r.rtf, $r.median_infer)
}
Write-Host ''
Write-Host ("threads: {0} | Median ASR: {1} s | p95: {2} s | Mean RTF: {3} | Inference (without load): {4} s" -f $json.threads, $json.stats.median_asr, $json.stats.p95_asr, $json.stats.mean_rtf, $json.stats.median_infer) -ForegroundColor Green
Write-Host "Details: $Out"
exit 0
