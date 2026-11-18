<#
    tts-server.ps1 - start/stop the persistent TTS (Chatterbox) HTTP server (Altai)

    Purpose: keep the TTS model IN MEMORY. `tts-tools.py` loads torch+model on every call
    (~20 s); with this server there is a single load, and each turn only generation remains (~4-7 s).
    `agent/pipeline.ps1 -TtsServerUrl http://127.0.0.1:8082` connects to this server.

    Usage:
      pwsh -File scripts\tts-server.ps1
      pwsh -File scripts\tts-server.ps1 -Port 8082 -Device cuda -Lang tr
      pwsh -File scripts\tts-server.ps1 -Stop

    Note: text kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).
#>
param(
    [string]$Python = '',
    [string]$Backend = 'chatterbox',
    [string]$Lang = 'tr',
    [string]$Device = 'cuda',
    [string]$T3Model = 'v3',
    [string]$VoicePrompt = '',
    [string]$Piper = '',
    [string]$PiperModel = '',
    [string]$Bind = '127.0.0.1',
    [int]$Port = 8082,
    [int]$Seed = -1,
    [switch]$NoSoftg,
    [switch]$TrRaw,
    [string]$LogDir = 'logs',
    [int]$TimeoutSec = 180,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $root 'agent\tts-tools.py'
$logRoot = Join-Path $root $LogDir
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$pidFile = Join-Path $logRoot 'tts-server.pid'

if ($Stop) {
    $stopped = $false
    if (Test-Path -LiteralPath $pidFile) {
        $savedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc) { Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue; $stopped = $true }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*tts-tools.py*--serve*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $stopped = $true }
    if ($stopped) { Write-Host 'tts-server stopped.' } else { Write-Host 'No tts-server is running.' }
    exit 0
}

if (-not (Test-Path -LiteralPath $tool)) { throw "tts-tools.py not found: $tool" }
if (-not $Python) { $Python = Join-Path $env:USERPROFILE 'tts-venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python not found: $Python (tts-venv)" }

$outLog = Join-Path $logRoot 'tts-server.out.log'
$errLog = Join-Path $logRoot 'tts-server.err.log'
# WARNING: the repo path may contain non-ASCII characters; passing an absolute path argument to
# Start-Process corrupts it -> make the working directory the repo and pass the script RELATIVE.
$args = @('agent\tts-tools.py', '--serve', '--backend', $Backend, '--lang', $Lang,
          '--device', $Device, '--t3-model', $T3Model, '--host', $Bind, '--port', $Port)
if ($VoicePrompt) { $args += @('--voice-prompt', $VoicePrompt) }
if ($Seed -ge 0) { $args += @('--seed', "$Seed") }
if ($NoSoftg) { $args += @('--chatterbox-no-softg') }
if ($TrRaw) { $args += @('--chatterbox-tr-raw') }

# piper: IMPORTANT - the binary and the voice file must be on an ASCII path (espeak-ng/onnxruntime
# crash on a non-ASCII path). Default: %LOCALAPPDATA%\altai\piper (ASCII).
if ($Backend -eq 'piper') {
    if (-not $Piper) { $Piper = Join-Path $env:LOCALAPPDATA 'altai\piper\piper.exe' }
    if (-not $PiperModel) { $PiperModel = Join-Path $env:LOCALAPPDATA 'altai\piper\voice.onnx' }
}
if ($Piper) { $args += @('--piper', $Piper) }
if ($PiperModel) { $args += @('--piper-model', $PiperModel) }

Write-Host "starting tts-server (backend=$Backend, lang=$Lang, device=$Device, $Bind`:$Port)"
if ($Backend -eq 'piper') {
    Write-Host "piper: binary=$Piper voice=$PiperModel (no loading; ~0.3 s per request)"
} else {
    Write-Host "loading model (torch+Chatterbox can take ~20 s)..."
}
$proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $root `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru -WindowStyle Hidden
$proc.Id | Set-Content -LiteralPath $pidFile
Write-Host "pid: $($proc.Id) (log: $errLog)"

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    try {
        $h = Invoke-RestMethod -Uri "http://$Bind`:$Port/health" -TimeoutSec 3 -ErrorAction Stop
        if ($h.ok -and $h.loaded) { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 1000
}

if ($ready) {
    Write-Host "tts-server READY: http://$Bind`:$Port/tts (load $($h.load_seconds) s)" -ForegroundColor Green
    Write-Host "Usage: pwsh -File agent\pipeline.ps1 -TtsServerUrl http://$Bind`:$Port ..."
    exit 0
}
Write-Host "tts-server did not become ready (exit: $($proc.ExitCode)). Log: $errLog" -ForegroundColor Yellow
if (Test-Path -LiteralPath $errLog) { Get-Content -LiteralPath $errLog -Tail 10 }
exit 1
