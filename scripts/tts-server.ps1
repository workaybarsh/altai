<#
    tts-server.ps1 - kalici TTS (Chatterbox) HTTP sunucusunu baslat/durdur (aybars_says)

    Amac: TTS modelini BELLEKTE tutmak. `tts-tools.py` her cagride torch+model yukler
    (~20 sn); bu sunucuyla tek yukleme olur, her tur yalniz uretim kalir (~4-7 sn).
    `agent/pipeline.ps1 -TtsServerUrl http://127.0.0.1:8082` bu sunucuya baglanir.

    Kullanim:
      pwsh -File scripts\tts-server.ps1
      pwsh -File scripts\tts-server.ps1 -Port 8082 -Device cuda -Lang tr
      pwsh -File scripts\tts-server.ps1 -Stop

    Not: Metinler ASCII tutuldu (Windows PowerShell 5.1 BOM'suz .ps1'i ANSI okur).
#>
param(
    [string]$Python = '',
    [string]$Backend = 'chatterbox',
    [string]$Lang = 'tr',
    [string]$Device = 'cuda',
    [string]$T3Model = 'v3',
    [string]$VoicePrompt = '',
    [string]$Bind = '127.0.0.1',
    [int]$Port = 8082,
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
    if ($stopped) { Write-Host 'tts-server durduruldu.' } else { Write-Host 'Calisan tts-server yok.' }
    exit 0
}

if (-not (Test-Path -LiteralPath $tool)) { throw "tts-tools.py bulunamadi: $tool" }
if (-not $Python) { $Python = Join-Path $env:USERPROFILE 'tts-venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python bulunamadi: $Python (tts-venv)" }

$outLog = Join-Path $logRoot 'tts-server.out.log'
$errLog = Join-Path $logRoot 'tts-server.err.log'
# DIKKAT: repo yolu non-ASCII icerebilir; Start-Process'e mutlak yol argumani vermek bozar
# -> calisma dizinini repo yapip betigi GORELI yolla ver.
$args = @('agent\tts-tools.py', '--serve', '--backend', $Backend, '--lang', $Lang,
          '--device', $Device, '--t3-model', $T3Model, '--host', $Bind, '--port', $Port)
if ($VoicePrompt) { $args += @('--voice-prompt', $VoicePrompt) }

Write-Host "tts-server baslatiliyor (backend=$Backend, lang=$Lang, device=$Device, $Bind`:$Port)"
Write-Host "model yukleniyor (torch+Chatterbox ~20 sn surebilir)..."
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
    Write-Host "tts-server HAZIR: http://$Bind`:$Port/tts (yukleme $($h.load_seconds) sn)" -ForegroundColor Green
    Write-Host "Kullanim: pwsh -File agent\pipeline.ps1 -TtsServerUrl http://$Bind`:$Port ..."
    exit 0
}
Write-Host "tts-server hazir olmadi (cikis: $($proc.ExitCode)). Log: $errLog" -ForegroundColor Yellow
if (Test-Path -LiteralPath $errLog) { Get-Content -LiteralPath $errLog -Tail 10 }
exit 1
