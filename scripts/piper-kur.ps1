<#
    piper-kur.ps1 - Piper (CPU, hizli TR TTS) kurar: ikili + tr_TR-dfki-medium sesi.

    NEDEN %LOCALAPPDATA%: piper'in espeak-ng/onnxruntime katmani **non-ASCII yollari okuyamiyor**
    (repo yolu "Varsayilan" -> 'i' noktali degil). Bu yuzden ikili ve ses DOSYASI ASCII bir dizine
    kurulur: %LOCALAPPDATA%\aybars\piper (varsayilan: piper.exe + voice.onnx).
    Ayni sinir whisper-cli.exe'de de var (non-ASCII MUTLAK yolda 0xC0000409 ile coker).

    Kullanim:
      pwsh -File scripts\piper-kur.ps1
      pwsh -File scripts\piper-kur.ps1 -Force        # yeniden indir
      pwsh -File scripts\piper-kur.ps1 -Dir D:\piper # baska ASCII dizin

    Sonra:
      pwsh -File scripts\tts-server.ps1 -Backend piper -Port 8082

    Not: Metinler ASCII tutuldu (Windows PowerShell 5.1 BOM'suz .ps1'i ANSI okur).
#>
param(
    [string]$Dir = '',
    [string]$Voice = 'tr_TR-dfki-medium',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if (-not $Dir) { $Dir = Join-Path $env:LOCALAPPDATA 'aybars\piper' }
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

$exe = Join-Path $Dir 'piper.exe'
$model = Join-Path $Dir 'voice.onnx'

function Get-File([string]$Url, [string]$Out) {
    if ((Test-Path -LiteralPath $Out) -and -not $Force) {
        Write-Host "  atlandi (var): $Out"
        return
    }
    Write-Host "  indiriliyor: $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Out -TimeoutSec 600
}

Write-Host "=== Piper kurulumu -> $Dir ==="

# 1) ikili
if (-not (Test-Path -LiteralPath $exe) -or $Force) {
    $zip = Join-Path $Dir 'piper.zip'
    Get-File 'https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip' $zip
    Write-Host '  aciliyor...'
    Expand-Archive -Path $zip -DestinationPath $Dir -Force
    Remove-Item -LiteralPath $zip -Force
} else {
    Write-Host "  atlandi (var): $exe"
}

# 2) ses (DFKI medium, TR)
$base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/$Voice"
Get-File "$base.onnx" $model
Get-File "$base.onnx.json" "$model.json"

if (-not (Test-Path -LiteralPath $exe)) { throw "piper.exe bulunamadi: $exe" }
if (-not (Test-Path -LiteralPath $model)) { throw "ses dosyasi bulunamadi: $model" }

Write-Host ''
Write-Host "HAZIR. piper=$exe ses=$model" -ForegroundColor Green
Write-Host "Sunucu: pwsh -File scripts\tts-server.ps1 -Backend piper -Port 8082"
exit 0
