<#
    Faz 2 ASR olcum kosum takimi (Altai)

    whisper.cpp hattini bir WAV klasoru uzerinde kosturur, gecikme/RTF toplar ve
    `logs\faz2-asr-sonuc.json` yazar. Asil is `agent/asr-tools.py` icindedir; bu
    betik yalnizca Python'u bulup cagiran ince bir sarmalayicidir.

    Kullanim:
      pwsh -File scripts/asr-olcum.ps1 -WavDir "tests\assets" -Model "models\ggml-large-v3-turbo-q5_0.bin"
      pwsh -File scripts/asr-olcum.ps1 -WavDir "tests\assets" -Model "..." -Repeat 10 -Threads 12
      pwsh -File scripts/asr-olcum.ps1 -WavDir "tests\assets" -ServerUrl http://127.0.0.1:8081

    Not: Metinler ASCII tutuldu (Windows PowerShell 5.1 BOM'suz .ps1'i ANSI okur).
#>
param(
    [string]$Model = '',
    [Parameter(Mandatory = $true)][string]$WavDir,
    [string]$Whisper = '',
    [string]$ServerUrl = '',
    [string]$Language = 'tr',
    [int]$Threads = 0,
    [int]$Repeat = 10,
    [string]$Out = 'logs\faz2-asr-sonuc.json'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $root 'agent\asr-tools.py'

if (-not (Test-Path -LiteralPath $tool)) { throw "asr-tools.py bulunamadi: $tool" }
if (-not $ServerUrl -and -not $Model) { throw '-Model ya da -ServerUrl gerekli.' }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { throw 'Python bulunamadi (python ya da py PATH uzerinde olmali).' }

$args = @($tool, '--dir', $WavDir, '--lang', $Language, '--repeat', $Repeat, '--out', $Out)
if ($ServerUrl) { $args += @('--server-url', $ServerUrl) } else { $args += @('--model', $Model) }
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
Write-Host ("{0,-32} {1,9} {2,9} {3,8} {4,10}" -f 'DOSYA', 'SES(s)', 'ASR(s)', 'RTF', 'CIKARIM(s)')
foreach ($r in $json.results) {
    Write-Host ("{0,-32} {1,9} {2,9} {3,8} {4,10}" -f (Split-Path -Leaf $r.file), $r.audio_seconds, $r.median_asr, $r.rtf, $r.median_infer)
}
Write-Host ''
Write-Host ("threads: {0} | Medyan ASR: {1} sn | p95: {2} sn | Ortalama RTF: {3} | Cikarim (yuklemesiz): {4} sn" -f $json.threads, $json.stats.median_asr, $json.stats.p95_asr, $json.stats.mean_rtf, $json.stats.median_infer) -ForegroundColor Green
Write-Host "Ayrinti: $Out"
exit 0
