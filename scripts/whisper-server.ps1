<#
    whisper-server.ps1 - start/stop the whisper.cpp server (Altai)

    Purpose: keep the model IN MEMORY. `whisper-cli` reloads the model on every call
    (~0.5 s q5_0 / ~1.4 s f16); with this script there is a single load and every request is pure inference.
    `asr-tools.py --server-url http://127.0.0.1:8081` connects to this server.

    Usage:
      pwsh -File scripts\whisper-server.ps1 -Model models\ggml-large-v3-turbo-q5_0.bin
      pwsh -File scripts\whisper-server.ps1 -Stop
      pwsh -File scripts\whisper-server.ps1 -Model ... -Port 8081 -Threads 12

    Note: text kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).
#>
param(
    [string]$Model = 'models\ggml-large-v3-turbo-q5_0.bin',
    [string]$Whisper = '',
    [int]$Threads = 0,
    [string]$Bind = '127.0.0.1',
    [int]$Port = 8081,
    [string]$Language = 'tr',
    [string]$LogDir = 'logs',
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$exe = if ($Whisper) { $Whisper } else { Join-Path $root 'tools\whisper\Release\whisper-server.exe' }
$logRoot = Join-Path $root $LogDir
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$pidFile = Join-Path $logRoot 'whisper-server.pid'

if ($Stop) {
    $stopped = $false
    if (Test-Path -LiteralPath $pidFile) {
        $savedPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc) { Stop-Process -Id $savedPid -Force; $stopped = $true }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
    Get-Process whisper-server -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; $stopped = $true
    }
    if ($stopped) { Write-Host 'whisper-server stopped.' } else { Write-Host 'No whisper-server is running.' }
    exit 0
}

if (-not (Test-Path -LiteralPath $exe)) { throw "whisper-server not found: $exe" }
$modelPath = Join-Path $root $Model
if (-not (Test-Path -LiteralPath $modelPath)) { throw "model not found: $modelPath" }

if ($Threads -le 0) { $Threads = [int]$env:NUMBER_OF_PROCESSORS }
if ($Threads -le 0) { $Threads = 4 }

$outLog = Join-Path $logRoot 'whisper-server.out.log'
$errLog = Join-Path $logRoot 'whisper-server.err.log'
# WARNING: the repo path may contain non-ASCII ('Varsayilan'); passing an ABSOLUTE path as a
# Start-Process argument corrupts that character -> whisper sees a wrong path in argv and crashes.
# Fix: make the working directory the repo and pass the model as a RELATIVE path.
$modelRel = $Model -replace '/', '\'
$argstr = "-m `"$modelRel`" -t $Threads -l $Language -ng --host $Bind --port $Port -nt"

Write-Host "starting whisper-server (model=$Model, threads=$Threads, $Bind`:$Port, CPU)"
$proc = Start-Process -FilePath $exe -ArgumentList $argstr -WorkingDirectory $root `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
    -PassThru -WindowStyle Hidden
$proc.Id | Set-Content -LiteralPath $pidFile
Write-Host "pid: $($proc.Id) (log: $errLog)"

# wait until ready (at most ~40 s)
$deadline = (Get-Date).AddSeconds(40)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { $ready = $true; break }
    Start-Sleep -Milliseconds 500
}

if ($ready) {
    Write-Host "whisper-server READY: http://$Bind`:$Port/inference" -ForegroundColor Green
    Write-Host "Usage: python agent/asr-tools.py --wav <file> --server-url http://$Bind`:$Port"
    exit 0
}
Write-Host "whisper-server did not become ready (exit code: $($proc.ExitCode)). Log: $errLog" -ForegroundColor Yellow
if (Test-Path -LiteralPath $errLog) { Get-Content -LiteralPath $errLog -Tail 10 }
exit 1
