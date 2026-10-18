<#
    whisper-server.ps1 - whisper.cpp sunucusunu baslat/durdur (aybars_speaks)

    Amac: modeli BELLEKTE tutmak. `whisper-cli` her cagride modeli yeniden yukler
    (~0,5 sn q5_0 / ~1,4 sn f16); bu betikle tek yukleme olur ve her istek saf cikarimdir.
    `asr-tools.py --server-url http://127.0.0.1:8081` bu sunucuya baglanir.

    Kullanim:
      pwsh -File scripts\whisper-server.ps1 -Model models\ggml-large-v3-turbo-q5_0.bin
      pwsh -File scripts\whisper-server.ps1 -Stop
      pwsh -File scripts\whisper-server.ps1 -Model ... -Port 8081 -Threads 12

    Not: Metinler ASCII tutuldu (Windows PowerShell 5.1 BOM'suz .ps1'i ANSI okur).
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
    if ($stopped) { Write-Host 'whisper-server durduruldu.' } else { Write-Host 'Calisan whisper-server yok.' }
    exit 0
}

if (-not (Test-Path -LiteralPath $exe)) { throw "whisper-server bulunamadi: $exe" }
$modelPath = Join-Path $root $Model
if (-not (Test-Path -LiteralPath $modelPath)) { throw "model bulunamadi: $modelPath" }

if ($Threads -le 0) { $Threads = [int]$env:NUMBER_OF_PROCESSORS }
if ($Threads -le 0) { $Threads = 4 }

$outLog = Join-Path $logRoot 'whisper-server.out.log'
$errLog = Join-Path $logRoot 'whisper-server.err.log'
# DIKKAT: repo yolu non-ASCII ('Varsayilan') icerebilir; Start-Process argumanina MUTLAK yol
# vermek bu karakteri bozar -> whisper argv'de yanlis yol gorup coker. Cozum: calisma dizinini
# repo yapip modeli GORELI yolla ver.
$modelRel = $Model -replace '/', '\'
$argstr = "-m `"$modelRel`" -t $Threads -l $Language -ng --host $Bind --port $Port -nt"

Write-Host "whisper-server baslatiliyor (model=$Model, threads=$Threads, $Bind`:$Port, CPU)"
$proc = Start-Process -FilePath $exe -ArgumentList $argstr -WorkingDirectory $root `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
    -PassThru -WindowStyle Hidden
$proc.Id | Set-Content -LiteralPath $pidFile
Write-Host "pid: $($proc.Id) (log: $errLog)"

# hazir olana kadar bekle (en fazla ~40 sn)
$deadline = (Get-Date).AddSeconds(40)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { $ready = $true; break }
    Start-Sleep -Milliseconds 500
}

if ($ready) {
    Write-Host "whisper-server HAZIR: http://$Bind`:$Port/inference" -ForegroundColor Green
    Write-Host "Kullanim: python agent/asr-tools.py --wav <dosya> --server-url http://$Bind`:$Port"
    exit 0
}
Write-Host "whisper-server hazir olmadi (cikti kodu: $($proc.ExitCode)). Log: $errLog" -ForegroundColor Yellow
if (Test-Path -LiteralPath $errLog) { Get-Content -LiteralPath $errLog -Tail 10 }
exit 1
