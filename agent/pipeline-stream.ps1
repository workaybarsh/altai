<#
    pipeline-stream.ps1 - STREAMING turn: ASR -> (LLM stream -> sentence by sentence TTS) -> playback

    Difference: `pipeline.ps1` waits for the WHOLE LLM answer and then does TTS in batch.
    In this script each sentence is sent to TTS as soon as it forms while the LLM tokens
    stream in, and the generated audio is played immediately (pipeline principle #7).
    Goal: bring down "first audio" latency (the main bottleneck).

    Requirement: a persistent TTS server (`scripts\tts-server.ps1`, port 8082) and
    `llama-server` (port 8080). Model loading is not repeated.

    Usage:
      pwsh -File agent\pipeline-stream.ps1 -Text "Merhaba, nasilsin?" `
           -TtsServerUrl http://127.0.0.1:8082
      pwsh -File agent\pipeline-stream.ps1 -Wav recording.wav -AsrServerUrl http://127.0.0.1:8081 `
           -TtsServerUrl http://127.0.0.1:8082 -Play

    Note: texts are kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).
#>
param(
  [string]$Wav,
  [string]$Text,
  [string]$TextFile,
  [string]$Server = "http://127.0.0.1:8080",
  [string]$Model,
  [string]$Whisper,
  [string]$AsrServerUrl,
  [string]$FwServerUrl,
  [int]$AsrThreads = 0,
[string]$Ffmpeg,
  [string]$Lang = "tr",
  [string]$TtsServerUrl,
  [string]$Python = "python",
  [string]$OutDir = "logs\pipeline-stream",
  [int]$MaxTokens = 1024,
  [switch]$NoThink,
  [switch]$Play
)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$asr = Join-Path $repo "agent\asr-tools.py"
$stream = Join-Path $repo "agent\llm-stream.py"
$outRoot = Join-Path $repo $OutDir
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null

if (-not $TtsServerUrl) {
    throw "The streaming pipeline needs a persistent TTS server: -TtsServerUrl (e.g. http://127.0.0.1:8082)."
}

# --- 1) ASR (optional; skipped when -Text is given) ---
if ($TextFile) { $Text = [System.IO.File]::ReadAllText($TextFile).Trim() }
if (-not $Text) {
    if (-not $Wav) { throw "Neither -Text nor -Wav was provided." }
    if (-not $Model -and -not $AsrServerUrl -and -not $FwServerUrl) { throw "ASR needs -Model (whisper .bin) or -AsrServerUrl or -FwServerUrl." }
    # Read the JSON from a FILE (UTF-8) - piping stdout corrupts the encoding in PS 5.1 (pitfall #14).
    $asrJson = Join-Path $outRoot "asr.json"
    $asrErr = Join-Path $outRoot "asr.err.txt"
    $asrArgs = @($asr, "--wav", $Wav, "--lang", $Lang, "--out", $asrJson)
    if ($FwServerUrl) { $asrArgs += @("--fw-server", $FwServerUrl) }
    elseif ($AsrServerUrl) { $asrArgs += @("--server-url", $AsrServerUrl) }
    else { $asrArgs += @("--model", $Model) }
    if ($Whisper) { $asrArgs += @("--whisper", $Whisper) }
    if ($Ffmpeg) { $asrArgs += @("--ffmpeg", $Ffmpeg) }
    if ($AsrThreads -gt 0) { $asrArgs += @("--threads", $AsrThreads) }
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Python @asrArgs 1> $null 2> $asrErr
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldEap
    if ($code -ne 0 -or -not (Test-Path $asrJson)) { throw "ASR failed (exit $code); error: $asrErr" }
    $asrOut = Get-Content -Raw -Encoding UTF8 $asrJson | ConvertFrom-Json
    if (-not $asrOut.ok) { throw "ASR failed: $($asrOut.error)" }
    $r0 = $asrOut.results[0]
    Write-Host ("[ASR] {0} s audio -> {1} s (RTF {2}, threads {3})" -f `
        $r0.audio_seconds, $r0.asr_seconds, $r0.rtf, $asrOut.threads)
    $Text = $r0.text
}
Write-Host "[TEXT] $Text"

# --- 2-3) STREAMING LLM -> sentence by sentence TTS (llm-stream.py) ---
$jsonFile = Join-Path $outRoot "stream.json"
$errFile = Join-Path $outRoot "stream.err.txt"
$prefix = "s_"
$streamArgs = @($stream, "--text", $Text, "--server", $Server, "--tts-server", $TtsServerUrl,
                "--lang", $Lang, "--out-dir", $outRoot, "--prefix", $prefix,
                "--max-tokens", $MaxTokens, "--json-out", $jsonFile)
if ($NoThink) { $streamArgs += "--no-think" }
if ($Play) { $streamArgs += "--play" }

$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"   # native stderr (progress/log) is not an error
& $Python @streamArgs 1> $null 2> $errFile
$code = $LASTEXITCODE
$ErrorActionPreference = $oldEap

if ($code -ne 0 -or -not (Test-Path $jsonFile)) {
    if (Test-Path $errFile) { Get-Content $errFile -Tail 15 | ForEach-Object { Write-Host "  $_" } }
    throw "Streaming turn failed (exit $code). Log: $errFile"
}
# Read the JSON as UTF-8 (pitfall #14: the PS 5.1 default is ANSI -> the 'i' in the path is
# corrupted, Test-Path wrongly returns False and the WAVs look 'missing').
$s = Get-Content -Raw -Encoding UTF8 $jsonFile | ConvertFrom-Json
Get-Content $errFile | Where-Object { $_ -match '^\s*\[' } | ForEach-Object { Write-Host $_ }
Write-Host "[STREAM] first chunk $($s.first_token_seconds) s ($($s.first_token_kind)) | first sentence $($s.first_sentence_seconds) s | FIRST AUDIO $($s.first_audio_seconds) s | LLM done $($s.llm_seconds) s | total $($s.total_seconds) s"
Write-Host "[LLM] $($s.answer)"

$wavs = @()
foreach ($r in $s.sentences) {
    $w = $r.out
    if (-not $w -or -not (Test-Path -LiteralPath $w)) {
        # Fallback: fall back to the file name. Server naming is "<prefix><sentence>_<server-index>.wav"
        # (one sentence per request -> the server index is always 1) -> look the pattern up with a glob.
        $alt = Get-ChildItem -LiteralPath $outRoot -Filter ("{0}{1}_*.wav" -f $prefix, $r.index) `
            -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($alt) { $w = $alt.FullName }
    }
    if ($w -and (Test-Path -LiteralPath $w)) { $wavs += $w } else { Write-Warning "sentence $($r.index) has no WAV" }
}
foreach ($w in $wavs) { Write-Host "[TTS] $w" }
if (-not $s.ok) { throw "Streaming turn produced no sentences: $($s.error)" }
Write-Host "DONE. WAVs generated: $($wavs.Count)"
