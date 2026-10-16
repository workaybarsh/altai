<#
    Faz 2 ASR olcum kosum takimi (aybars_says)

    whisper.cpp hattini bir WAV klasoru uzerinde kosturur, gecikme/RTF toplar ve
    `logs\faz2-asr-sonuc.json` yazar. Asil is `agent/asr-tools.py` icindedir; bu
    betik yalnizca Python'u bulup cagiran ince bir sarmalayicidir.

    Kullanim:
      pwsh -File scripts/asr-olcum.ps1 -WavDir "tests\assets" -Model "models\ggml-large-v3-turbo.bin"
      pwsh -File scripts/asr-olcum.ps1 -WavDir "tests\assets" -Model "..." -Repeat 10 -Threads 6

    Not: Metinler ASCII tutuldu (Windows PowerShell 5.1 BOM'suz .ps1'i ANSI okur).
#>
param(
    [Parameter(Mandatory = $true)][string]$Model,
    [Parameter(Mandatory = $true)][string]$WavDir,
    [string]$Whisper = '',
    [string]$Language = 'tr',
    [int]$Threads = 0,
    [int]$Repeat = 10,
    [string]$Out = 'logs\faz2-asr-sonuc.json'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $root 'agent\asr-tools.py'

if (-not (Test-Path -LiteralPath $tool)) { throw "asr-tools.py bulunamadi: $tool" }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw 'Python bulunamadi (python ya da py PATH uzerinde olmali).' }

$args = @($tool, '--dir', $WavDir, '--model', $Model, '--lang', $Language, '--repeat', $Repeat, '--out', $Out)
if ($Whisper) { $args += @('--whisper', $Whisper) }
if ($Threads -gt 0) { $args += @('--threads', $Threads) }

Write-Host "ASR olcumu: $WavDir (repeat=$Repeat, lang=$Language)"
& $python @args
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host "Olcum tamamlanmadi (cikis kodu: $code). Yukaridaki JSON'a bak." -ForegroundColor Yellow
    exit $code
}

$json = Get-Content -LiteralPath (Join-Path $root $Out) -Raw | ConvertFrom-Json
Write-Host ''
Write-Host ("{0,-32} {1,10} {2,10} {3,10}" -f 'DOSYA', 'SES(s)', 'ASR(s)', 'RTF')
foreach ($r in $json.results) {
    Write-Host ("{0,-32} {1,10} {2,10} {3,10}" -f (Split-Path -Leaf $r.file), $r.audio_seconds, $r.median_asr, $r.rtf)
}
Write-Host ''
Write-Host ("Medyan ASR: {0} sn | p95: {1} sn | Ortalama RTF: {2}" -f $json.stats.median_asr, $json.stats.p95_asr, $json.stats.mean_rtf) -ForegroundColor Green
Write-Host "Ayrinti: $Out"
exit 0
