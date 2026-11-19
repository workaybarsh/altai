#!/usr/bin/env pwsh
# asr-ab.ps1 - compare two faster-whisper models on the same audio (text + speed).
#
# Example:
#   pwsh -File scripts\asr-ab.ps1 -Wav logs\tts\sample.wav `
#        -ModelB altintasutku/whisper-large-v3-turkish-ct2-int8

param(
    [Parameter(Mandatory = $true)][string]$Wav,
    [string]$ModelA = 'large-v3-turbo',
    [string]$ModelB = 'altintasutku/whisper-large-v3-turkish-ct2-int8',
    [string]$Device = 'cuda',
    [string]$Compute = 'int8_float16',
    [string]$Lang = 'tr',
    [int]$Repeat = 2,
    [string]$Python = '',
    [string]$Out = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (-not $Python) { $Python = Join-Path $env:USERPROFILE 'fw-venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw "faster-whisper python not found: $Python" }
if (-not $Out) { $Out = Join-Path $root 'logs\asr-ab.json' }
New-Item -ItemType Directory -Force -Path (Split-Path $Out -Parent) | Out-Null

$abArgs = @((Join-Path $root 'agent\asr-ab.py'), '--wav', (Resolve-Path -LiteralPath $Wav).Path,
    '--model-a', $ModelA, '--model-b', $ModelB, '--device', $Device, '--compute', $Compute,
    '--lang', $Lang, '--repeat', $Repeat)

& $Python @abArgs *> $Out
$code = $LASTEXITCODE
Get-Content -Raw -Encoding UTF8 $Out
exit $code
