<#
    install-piper.ps1 - installs Piper (CPU, fast TR TTS): binary + tr_TR-dfki-medium voice.

    WHY %LOCALAPPDATA%: piper's espeak-ng/onnxruntime layer **cannot read non-ASCII paths**
    (the repo path is "Varsayilan" -> dotless 'i'). That is why the binary and the voice FILE are
    installed into an ASCII directory: %LOCALAPPDATA%\altai\piper (default: piper.exe + voice.onnx).
    The same limit exists in whisper-cli.exe (it crashes with 0xC0000409 on a non-ASCII ABSOLUTE path).

    Usage:
      pwsh -File scripts\install-piper.ps1
      pwsh -File scripts\install-piper.ps1 -Force        # download again
      pwsh -File scripts\install-piper.ps1 -Dir D:\piper # another ASCII directory

    Then:
      pwsh -File scripts\tts-server.ps1 -Backend piper -Port 8082

    Note: text kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).
#>
param(
    [string]$Dir = '',
    [string]$Voice = 'tr_TR-dfki-medium',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if (-not $Dir) { $Dir = Join-Path $env:LOCALAPPDATA 'altai\piper' }
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

$exe = Join-Path $Dir 'piper.exe'
$model = Join-Path $Dir 'voice.onnx'

function Get-File([string]$Url, [string]$Out) {
    if ((Test-Path -LiteralPath $Out) -and -not $Force) {
        Write-Host "  skipped (exists): $Out"
        return
    }
    Write-Host "  downloading: $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Out -TimeoutSec 600
}

Write-Host "=== Piper install -> $Dir ==="

# 1) binary
if (-not (Test-Path -LiteralPath $exe) -or $Force) {
    $zip = Join-Path $Dir 'piper.zip'
    Get-File 'https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip' $zip
    Write-Host '  extracting...'
    Expand-Archive -Path $zip -DestinationPath $Dir -Force
    Remove-Item -LiteralPath $zip -Force
    # The release zip unpacks into a top-level 'piper' folder; flatten it so the
    # binary ends up next to the voice file (tts-server.ps1 expects $Dir\piper.exe).
    $nested = Join-Path $Dir 'piper'
    if (Test-Path -LiteralPath $nested) {
        Get-ChildItem -LiteralPath $nested -Force | Move-Item -Destination $Dir -Force
        Remove-Item -LiteralPath $nested -Recurse -Force
    }
} else {
    Write-Host "  skipped (exists): $exe"
}

# 2) voice (DFKI medium, TR)
$base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/$Voice"
Get-File "$base.onnx" $model
Get-File "$base.onnx.json" "$model.json"

if (-not (Test-Path -LiteralPath $exe)) { throw "piper.exe not found: $exe" }
if (-not (Test-Path -LiteralPath $model)) { throw "voice file not found: $model" }

Write-Host ''
Write-Host "READY. piper=$exe voice=$model" -ForegroundColor Green
Write-Host "Server: pwsh -File scripts\tts-server.ps1 -Backend piper -Port 8082"
exit 0
