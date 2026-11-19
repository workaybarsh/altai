#!/usr/bin/env pwsh
# measure-turn.ps1 - timing timeline for one or more conversational turns.
#
# Measures, per turn:
#   t0  user stops speaking (start of processing; the WAV simulates the utterance)
#   t1  first audio (assistant starts speaking)          -> TTFA = t1 - t0
#   t2  audio ends (playback finished)
#   t3  next turn's first audio (when the next reply starts) -> gap = t3 - t2
#
# Requires the three services to be running (llama-server 8080, ASR 8081, TTS 8082).
#
# Example:
#   pwsh -File scripts\measure-turn.ps1 -Wav logs\tts\rec.wav -Turns 2

param(
    [Parameter(Mandatory = $true)][string]$Wav,
    [string]$Lang = 'tr',
    [switch]$NoThink,
    [int]$Turns = 2,
    [string]$AsrServerUrl = '',
    [string]$FwServerUrl = 'http://127.0.0.1:8083',
    [string]$TtsServerUrl = 'http://127.0.0.1:8082',
    [int]$MaxTokens = 0,
    [string]$OutDir = 'logs\measure'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$pipeline = Join-Path $root 'agent\pipeline-stream.ps1'
$wavPath = (Resolve-Path -LiteralPath $Wav).Path
$runDir = Join-Path $root ($OutDir + '\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$relRun = $runDir.Substring($root.Length + 1)

function Get-Port([string]$Url) {
    return [int]([uri]$Url).Port
}

foreach ($u in @($FwServerUrl, $AsrServerUrl, $TtsServerUrl)) {
    if (-not $u) { continue }
    $p = Get-Port $u
    $ok = Test-NetConnection -ComputerName 127.0.0.1 -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue
    if (-not $ok) { throw "Service not reachable: $u (port $p). Start the servers first." }
}

$results = @()
$prevAudioEnd = $null

for ($i = 1; $i -le $Turns; $i++) {
    $t0 = Get-Date
    $log = Join-Path $runDir ("turn{0}.log" -f $i)
    $argv = @('-NoProfile', '-File', $pipeline, '-Wav', $wavPath,
        '-Lang', $Lang, '-OutDir', (Join-Path $relRun ("turn{0}" -f $i)), '-Play')
    if ($FwServerUrl) { $argv += @('-FwServerUrl', $FwServerUrl) }
    if ($AsrServerUrl) { $argv += @('-AsrServerUrl', $AsrServerUrl) }
    $argv += @('-TtsServerUrl', $TtsServerUrl)
    if ($MaxTokens -gt 0) { $argv += @('-MaxTokens', $MaxTokens) }
    if ($NoThink) { $argv += '-NoThink' }

    $eventsFile = Join-Path $runDir ("events{0}.jsonl" -f $i)
    if (Test-Path -LiteralPath $eventsFile) { Remove-Item -LiteralPath $eventsFile -Force }
    $env:ALTAI_EVENTS = $eventsFile

    & pwsh @argv *> $log
    $tEnd = Get-Date
    Remove-Item Env:\ALTAI_EVENTS -ErrorAction SilentlyContinue

    $lines = Get-Content -LiteralPath $log -Encoding UTF8
    $stream = ($lines | Where-Object { $_ -match '^\[STREAM\]' } | Select-Object -Last 1)
    $text = ($lines | Where-Object { $_ -match '^\[TEXT\]' } | Select-Object -First 1)
    $reply = ($lines | Where-Object { $_ -match '^\[LLM\]' -and $_ -notmatch 'first chunk' } | Select-Object -First 1)

    $ttfa = $null
    if ($stream -and $stream -match 'FIRST AUDIO\s+([0-9.]+)\s*s') { $ttfa = [double]$Matches[1] }

    # wall-clock events written by llm-stream.py (exact playback start per sentence)
    $ev = @()
    if (Test-Path -LiteralPath $eventsFile) {
        $ev = Get-Content -LiteralPath $eventsFile -Encoding UTF8 |
            ForEach-Object { if ($_.Trim()) { $_ | ConvertFrom-Json } }
    }
    $speaks = @($ev | Where-Object { $_.event -eq 'speak' })

    $audioSeconds = 0.0
    $t0posix = ([DateTimeOffset]$t0).ToUnixTimeMilliseconds() / 1000.0
    $firstPosix = $null
    $audioEndPosix = $null
    if ($speaks.Count -gt 0) {
        foreach ($s in $speaks) { $audioSeconds += [double]$s.audio }
        $firstPosix = [double]$speaks[0].ts
        $audioEndPosix = ($speaks | ForEach-Object { [double]$_.ts + [double]$_.audio } |
            Measure-Object -Maximum).Maximum
    } else {
        foreach ($l in $lines) {
            foreach ($m in [regex]::Matches($l, '([0-9]+(?:\.[0-9]+)?)s audio')) {
                $audioSeconds += [double]$m.Groups[1].Value
            }
        }
        if ($audioSeconds -gt 0) {
            $firstPosix = $t0posix + ($ttfa + 0.0)
            $audioEndPosix = $t0posix + ($tEnd - $t0).TotalSeconds
        }
    }

    $firstAudioAt = if ($null -ne $firstPosix) { [DateTimeOffset]::FromUnixTimeMilliseconds([long]($firstPosix * 1000)).LocalDateTime } else { $null }
    $row = [pscustomobject]@{
        Turn          = $i
        SpeechEnd     = $t0.ToString('HH:mm:ss.fff')
        FirstAudio    = if ($firstAudioAt) { $firstAudioAt.ToString('HH:mm:ss.fff') } else { '-' }
        TTFA_s        = if ($null -ne $firstPosix) { [math]::Round($firstPosix - $t0posix, 3) } else { $null }
        EngineTTFA_s  = if ($null -ne $ttfa) { [math]::Round($ttfa, 3) } else { $null }
        Audio_s       = [math]::Round($audioSeconds, 2)
        PlaybackEnd   = if ($null -ne $audioEndPosix) { [DateTimeOffset]::FromUnixTimeMilliseconds([long]($audioEndPosix * 1000)).LocalDateTime.ToString('HH:mm:ss.fff') } else { '-' }
        Playback_s    = if ($null -ne $firstPosix -and $null -ne $audioEndPosix) { [math]::Round($audioEndPosix - $firstPosix, 2) } else { $null }
        Gap_s         = if ($null -ne $prevAudioEnd -and $null -ne $firstPosix) { [math]::Round($firstPosix - $prevAudioEnd, 3) } else { $null }
        Transcript    = ($text -replace '^\[TEXT\]\s*', '')
        Reply         = ($reply -replace '^\[LLM\]\s*', '')
    }
    $results += $row
    Write-Host ("[turn " + $i + "] TTFA " + $(if ($null -ne $row.TTFA_s) { $row.TTFA_s } else { '-' }) +
        " s | audio " + $row.Audio_s + " s | playback " + $(if ($null -ne $row.Playback_s) { $row.Playback_s } else { '-' }) +
        " s | next-turn gap " + $(if ($null -ne $row.Gap_s) { $row.Gap_s } else { '-' }) + " s")
    Write-Host ("         you: " + $row.Transcript)
    Write-Host ("         altai: " + $row.Reply)

    $prevAudioEnd = $audioEndPosix
}

$json = Join-Path $runDir 'timeline.json'
$results | ConvertTo-Json -Depth 5 | Out-File -LiteralPath $json -Encoding utf8
Write-Host ""
Write-Host "timeline: $json"
$results | Format-Table Turn, TTFA_s, Audio_s, Playback_s, Gap_s -AutoSize
