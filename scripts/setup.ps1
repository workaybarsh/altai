#!/usr/bin/env pwsh
# setup.ps1 - one-shot environment setup for Altai (Windows).
#
# Creates the two virtual environments, downloads the llama.cpp CUDA 13.5 binaries, the
# whisper model and the 9B GGUF, injects the MTP header, and checks the microphone tool
# (ffmpeg). Safe to re-run: every step is skipped when its output already exists.
#
# Usage:
#   pwsh -File scripts\setup.ps1
#   pwsh -File scripts\setup.ps1 -SkipModels        # venvs + binaries only
#   pwsh -File scripts\setup.ps1 -GpuArch cuda-13.5 # default
#
# Note: text kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).

param(
    [switch]$SkipModels,
    [switch]$Force,
    [string]$Model = 'models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf',
    [string]$WhisperModel = 'models\ggml-large-v3-turbo-q5_0.bin',
    [string]$LlamaTag = 'b12521'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
New-Item -ItemType Directory -Force -Path models, tools, logs | Out-Null

function Step($text) { Write-Host ''; Write-Host "== $text" -ForegroundColor Cyan }
function Have($path) { return (Test-Path -LiteralPath $path) -and -not $Force }

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw 'Python 3.12 is required (python not found on PATH).' }

# ------------------------------------------------------------------ venvs
$ttsVenv = Join-Path $env:USERPROFILE 'tts-venv'
$fwVenv = Join-Path $env:USERPROFILE 'fw-venv'

Step "Chatterbox venv ($ttsVenv)"
if (-not (Test-Path (Join-Path $ttsVenv 'Scripts\python.exe'))) {
    & $py -m venv $ttsVenv
}
$ttsPy = Join-Path $ttsVenv 'Scripts\python.exe'
& $ttsPy -m pip install --quiet --upgrade pip
& $ttsPy -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
& $ttsPy -m pip install chatterbox-tts soundfile

Step "faster-whisper venv ($fwVenv)"
if (-not (Test-Path (Join-Path $fwVenv 'Scripts\python.exe'))) {
    & $py -m venv $fwVenv
}
$fwPy = Join-Path $fwVenv 'Scripts\python.exe'
& $fwPy -m pip install --quiet --upgrade pip
& $fwPy -m pip install faster-whisper
& $fwPy -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12

# ------------------------------------------------------------------ llama.cpp
Step 'llama.cpp (CUDA 13.5)'
if (-not (Have 'tools\llama\llama-server.exe')) {
    $base = "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaTag"
    $zip = Join-Path $env:TEMP 'llama.zip'
    $cudart = Join-Path $env:TEMP 'cudart.zip'
    Invoke-WebRequest "$base/llama-$LlamaTag-bin-win-cuda-13.5-x64.zip" -OutFile $zip -TimeoutSec 3600
    Invoke-WebRequest "$base/cudart-llama-bin-win-cuda-13.5-x64.zip" -OutFile $cudart -TimeoutSec 3600
    Remove-Item -Recurse -Force tools\llama -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path tools\llama | Out-Null
    Expand-Archive $zip -DestinationPath (Join-Path $env:TEMP 'llama-x') -Force
    Expand-Archive $cudart -DestinationPath (Join-Path $env:TEMP 'cudart-x') -Force
    Get-ChildItem (Join-Path $env:TEMP 'llama-x'), (Join-Path $env:TEMP 'cudart-x') -Recurse -File |
        ForEach-Object { Copy-Item $_.FullName -Destination tools\llama -Force }
    Remove-Item -Recurse -Force $zip, $cudart, (Join-Path $env:TEMP 'llama-x'), (Join-Path $env:TEMP 'cudart-x')
}

# ------------------------------------------------------------------ ffmpeg
Step 'ffmpeg (mic capture + 16 kHz conversion)'
if (-not (Have 'tools\ffmpeg\ffmpeg.exe')) {
    $ff = Join-Path $env:TEMP 'ffmpeg.zip'
    Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip' -OutFile $ff -TimeoutSec 3600
    Expand-Archive $ff -DestinationPath (Join-Path $env:TEMP 'ffmpeg-x') -Force
    $exe = Get-ChildItem (Join-Path $env:TEMP 'ffmpeg-x') -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path tools\ffmpeg | Out-Null
    Copy-Item $exe.FullName tools\ffmpeg\ffmpeg.exe -Force
    Copy-Item (Join-Path $exe.DirectoryName 'ffprobe.exe') tools\ffmpeg\ffprobe.exe -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $ff, (Join-Path $env:TEMP 'ffmpeg-x')
}

# ------------------------------------------------------------------ models
if (-not $SkipModels) {
    Step 'whisper model (large-v3-turbo q5_0, CPU fallback path)'
    if (-not (Have $WhisperModel)) {
        Invoke-WebRequest 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin' -OutFile $WhisperModel -TimeoutSec 3600
    }

    Step 'LLM (9B i1-Q5_K_M)'
    if (-not (Have $Model)) {
        Invoke-WebRequest 'https://huggingface.co/mradermacher/Huihui-Qwen3.5-9B-abliterated-i1-GGUF/resolve/main/Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf' -OutFile $Model -TimeoutSec 7200
    }

    Step 'MTP header'
    & $py agent\mtp-status.py $Model
    & pwsh -NoProfile -File scripts\mtp-verify.ps1 -Gguf $Model -Inject
}

Step 'done'
Write-Host 'Start the app:  pwsh -File altai-desktop.ps1'
Write-Host 'Model check:    python agent\mtp-status.py "' -NoNewline
Write-Host $Model -NoNewline
Write-Host '"'
