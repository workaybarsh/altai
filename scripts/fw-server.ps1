<#
    fw-server.ps1 - start/stop the persistent faster-whisper STT server (GPU by default).

    Why: whisper.cpp on the CPU needs ~10 s for a 7 s Turkish utterance; the same model on the
    GPU through CTranslate2 needs ~0.27 s (RTF 0.04). The model stays resident in VRAM.

    Usage:
      pwsh -File scripts\fw-server.ps1
      pwsh -File scripts\fw-server.ps1 -Stop
      pwsh -File scripts\fw-server.ps1 -Compute float16 -Port 8083

    Then:
      python agent/asr-tools.py --wav recording.wav --fw-server http://127.0.0.1:8083

    Note: text kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).
#>
param(
    [string]$Python = '',
    [string]$Model = 'large-v3-turbo',
    [string]$Device = 'cuda',
    [string]$Compute = 'int8_float16',
    [string]$Bind = '127.0.0.1',
    [int]$Port = 8083,
    [switch]$Stop,
    [string]$LogDir = 'logs'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$tool = Join-Path $repo 'agent\fw-server.py'
$logRoot = Join-Path $repo $LogDir
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$pidFile = Join-Path $logRoot 'fw-server.pid'

if ($Stop) {
    $stopped = $false
    if (Test-Path -LiteralPath $pidFile) {
        $savedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc) { Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue; $stopped = $true }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*fw-server.py*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $stopped = $true }
    if ($stopped) { Write-Host 'fw-server stopped.' } else { Write-Host 'No fw-server is running.' }
    exit 0
}

if (-not (Test-Path -LiteralPath $tool)) { throw "fw-server.py not found: $tool" }

# Refuse to start a second server (each model costs VRAM). The process check also catches a
# server that is still loading and therefore not listening yet.
$existing = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*fw-server.py*' }
if ($existing) {
    Write-Host "fw-server already running (pid $($existing[0].ProcessId)); not starting another."
    exit 0
}
if (-not $Python) { $Python = Join-Path $env:USERPROFILE 'fw-venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python not found: $Python (fw-venv; pass -Python)" }

$outLog = Join-Path $logRoot 'fw-server.out.log'
$errLog = Join-Path $logRoot 'fw-server.err.log'
$fwArgs = @('-u', 'agent\fw-server.py', '--model', $Model, '--device', $Device, '--compute', $Compute,
          '--host', $Bind, '--port', $Port)

Write-Host "starting fw-server (model=$Model, device=$Device, compute=$Compute, ${Bind}:$Port)"
$proc = Start-Process -FilePath $Python -ArgumentList $fwArgs -WorkingDirectory $repo -WindowStyle Hidden `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
$proc.Id | Set-Content -LiteralPath $pidFile -Encoding ascii

$deadline = (Get-Date).AddMinutes(5)
$ready = $null
while ((Get-Date) -lt $deadline) {
    try {
        $ready = Invoke-RestMethod -Method Get -Uri "http://${Bind}:$Port/health" -TimeoutSec 2
        if ($ready.ok) { break }
    } catch { }
    if ($proc.HasExited) { throw "fw-server exited early; see $errLog" }
    Start-Sleep -Milliseconds 700
}
if (-not $ready -or -not $ready.ok) { throw "fw-server did not become ready; see $errLog" }

Write-Host "fw-server READY: http://${Bind}:$Port/transcribe (model loaded)" -ForegroundColor Green
Write-Host "Usage: python agent\asr-tools.py --wav <file> --fw-server http://${Bind}:$Port"
