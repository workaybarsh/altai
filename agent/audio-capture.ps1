# audio-capture.ps1 - microphone recording for Altai.
#
# Primary path: ffmpeg dshow -> 16 kHz / mono / 16-bit PCM WAV (what whisper wants).
# Fallback:     winmm mciSendString (no ffmpeg; device default format, converted later).
#
# The MCI device default on this machine is 11 kHz / 8-bit, which is too poor for ASR;
# ffmpeg gives us a proper 16 kHz stream in one step.
#
# Usage (dot-source):
#   . "$PSScriptRoot\audio-capture.ps1"
#   Get-AltaiAudioDevices
#   Start-AltaiRecording -Device "Mikrofon (Realtek(R) Audio)"
#   $wav = Stop-AltaiRecording -Destination "logs\ui\rec.wav"
#
# Note: text kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).

if (-not ('AltaiWinMM' -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class AltaiWinMM
{
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern int mciSendString(string command, StringBuilder buffer, int bufferSize, IntPtr hwndCallback);
}
"@
}

$script:AltaiRecAlias = 'altai_rec'
$script:AltaiRecFile = $null
$script:AltaiRecStarted = $null
$script:AltaiFfProcess = $null
$script:AltaiUseFfmpeg = $null

function Get-AltaiFfmpeg {
    $repoFfmpeg = Join-Path (Split-Path $PSScriptRoot -Parent) 'tools\ffmpeg\ffmpeg.exe'
    if (Test-Path -LiteralPath $repoFfmpeg) { return $repoFfmpeg }
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Get-AltaiAudioDevices {
    <# Lists DirectShow audio capture devices (needs ffmpeg). #>
    $ffmpeg = Get-AltaiFfmpeg
    if (-not $ffmpeg) { return @() }
    $out = & $ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1
    $names = @()
    foreach ($line in $out) {
        if ($line -match '"(.+?)"\s+\(audio\)') { $names += $Matches[1] }
    }
    return $names
}

function Get-AltaiDefaultDevice {
    <# Saved choice -> first device -> $null. #>
    $pref = Join-Path $env:LOCALAPPDATA 'altai\mic.txt'
    if (Test-Path -LiteralPath $pref) {
        $name = (Get-Content -LiteralPath $pref -Raw).Trim()
        if ($name) { return $name }
    }
    $devices = Get-AltaiAudioDevices
    if ($devices.Count -gt 0) { return $devices[0] }
    return $null
}

function Set-AltaiDefaultDevice([string]$Name) {
    $dir = Join-Path $env:LOCALAPPDATA 'altai'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Set-Content -LiteralPath (Join-Path $dir 'mic.txt') -Value $Name -Encoding utf8
}

function Invoke-AltaiMci([string]$Command, [switch]$Quiet) {
    $sb = New-Object System.Text.StringBuilder 512
    $rc = [AltaiWinMM]::mciSendString($Command, $sb, 512, [IntPtr]::Zero)
    if ($rc -ne 0) {
        if ($Quiet) { return $null }
        throw "mciSendString failed (code $rc): $Command"
    }
    return $sb.ToString()
}

function Start-AltaiRecording {
    <#
        Starts recording to a temp WAV. Uses ffmpeg dshow (16 kHz mono) when available,
        otherwise MCI with the device default format.
        -Device: DirectShow device name (default: saved choice or the first device).
        -MaxSeconds: safety stop (ffmpeg -t), 0 = no limit.
    #>
    param([string]$Device, [int]$MaxSeconds = 0)

    if ($script:AltaiRecFile) { Stop-AltaiRecording | Out-Null }
    $wav = Join-Path $env:TEMP ("altai-rec-{0}.wav" -f (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    $ffmpeg = Get-AltaiFfmpeg

    if ($ffmpeg) {
        if (-not $Device) { $Device = Get-AltaiDefaultDevice }
        if (-not $Device) { throw 'No DirectShow audio device found (ffmpeg -list_devices).' }

        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $ffmpeg
        $psi.Arguments = ('-hide_banner -loglevel error -f dshow -i "audio={0}" -ac 1 -ar 16000 ' +
            '-c:a pcm_s16le -y "{1}"') -f $Device, $wav
        if ($MaxSeconds -gt 0) { $psi.Arguments = $psi.Arguments.Insert(0, "-t $MaxSeconds ") }
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardInput = $true
        $psi.RedirectStandardError = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        Start-Sleep -Milliseconds 400
        if ($proc.HasExited) {
            $err = $proc.StandardError.ReadToEnd()
            throw "ffmpeg could not start recording ($Device): $err"
        }
        $script:AltaiFfProcess = $proc
        $script:AltaiUseFfmpeg = $true
    } else {
        Invoke-AltaiMci "close $script:AltaiRecAlias" -Quiet | Out-Null
        Invoke-AltaiMci "open new type waveaudio alias $script:AltaiRecAlias" | Out-Null
        try {
            Invoke-AltaiMci ("set {0} time format ms bitspersample 16 channels 1 samplespersec 16000" -f $script:AltaiRecAlias) | Out-Null
        } catch {
            # keep the driver default; the ASR conversion step normalises it
        }
        Invoke-AltaiMci ("record {0}" -f $script:AltaiRecAlias) | Out-Null
        $script:AltaiUseFfmpeg = $false
    }

    $script:AltaiRecFile = $wav
    $script:AltaiRecStarted = Get-Date
    return $wav
}

function Stop-AltaiRecording {
    <#
        Stops recording, finalises the WAV (ffmpeg 'q' so the header is written) and returns
        the path. -Destination moves the file there.
    #>
    param([string]$Destination)

    if (-not $script:AltaiRecFile) { throw 'No active recording.' }
    $tmp = $script:AltaiRecFile

    if ($script:AltaiUseFfmpeg -and $script:AltaiFfProcess) {
        $proc = $script:AltaiFfProcess
        try {
            $proc.StandardInput.WriteLine('q')
            $proc.StandardInput.Flush()
        } catch { }
        if (-not $proc.WaitForExit(4000)) { try { $proc.Kill() } catch { } }
        $script:AltaiFfProcess = $null
    } else {
        Invoke-AltaiMci ("stop {0}" -f $script:AltaiRecAlias) | Out-Null
        Invoke-AltaiMci ("save {0} `"{1}`"" -f $script:AltaiRecAlias, $tmp) | Out-Null
        Invoke-AltaiMci ("close {0}" -f $script:AltaiRecAlias) -Quiet | Out-Null
    }

    $script:AltaiRecFile = $null
    $script:AltaiRecStarted = $null
    if (-not (Test-Path -LiteralPath $tmp)) { throw "Recording was not written: $tmp" }

    Start-Sleep -Milliseconds 200
    if (-not $Destination) { return $tmp }
    $dir = Split-Path -Parent $Destination
    if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Move-Item -LiteralPath $tmp -Destination $Destination -Force
    return $Destination
}

function Get-AltaiRecordingSeconds {
    if (-not $script:AltaiRecStarted) { return 0 }
    return [math]::Round(((Get-Date) - $script:AltaiRecStarted).TotalSeconds, 1)
}

function Test-AltaiMicrophone {
    <# Quick check: can we open a recording device at all? #>
    try {
        $devices = Get-AltaiAudioDevices
        if ($devices.Count -gt 0) { return $true }
    } catch { }
    try {
        Invoke-AltaiMci "close $script:AltaiRecAlias" -Quiet | Out-Null
        Invoke-AltaiMci "open new type waveaudio alias $script:AltaiRecAlias" | Out-Null
        Invoke-AltaiMci ("close {0}" -f $script:AltaiRecAlias) -Quiet | Out-Null
        return $true
    } catch {
        return $false
    }
}
