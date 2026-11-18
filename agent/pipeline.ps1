#!/usr/bin/env pwsh
# pipeline.ps1 - ASR -> LLM -> TTS pipeline (Altai)
#
# Flow:  WAV/Text -> whisper.cpp (asr-tools.py) -> llama-server (HTTP) -> sentence split
#        -> TTS (tts-tools.py; for TR the chatterbox fixes are AUTOMATIC) -> WAVs
#
# TTS BATCH MODE: for chatterbox the sentences are produced in a SINGLE call (--batch-file + --out-prefix),
#   so the model is loaded ONCE (no ~13 s per sentence + torch import ~8 s repeated).
#   Expected gain: ~57 s -> ~15 s for 2 sentences. Other backends fall back to per-sentence mode.
#
# TTS PERSISTENT SERVER (-TtsServerUrl): the model stays resident in memory (scripts\tts-server.ps1);
#   each turn only generation remains (loading repeats are gone completely). Preferred path.
#
# Example:
#   pwsh -File agent\pipeline.ps1 -Text "Merhaba, nasilsin?" -Lang tr
#   pwsh -File agent\pipeline.ps1 -Wav recording.wav -Model models\ggml-large-v3-turbo-q5_0.bin -AsrThreads 12
#   pwsh -File agent\pipeline.ps1 -Wav recording.wav -AsrServerUrl http://127.0.0.1:8081 `
#        -TtsServerUrl http://127.0.0.1:8082
#
# Note: if a component (whisper / llama-server) is missing it fails HONESTLY, it does not invent one.
#       For the TTS backends (chatterbox/voxcpm) pass the tts-venv python as -Python.
param(
  [string]$Wav,
  [string]$Text,
  [string]$TextFile,
  [string]$Server = "http://127.0.0.1:8080",
  [string]$Model,
  [string]$Whisper,
  [string]$AsrServerUrl,
  [int]$AsrThreads = 0,
  [string]$Lang = "tr",
  [string]$Backend = "chatterbox",
  [string]$TtsServerUrl,
  [string]$Device = "cuda",
  [string]$Python = "python",
  [string]$OutDir = "logs\pipeline",
  [string]$VoicePrompt,
  [int]$MaxTokens = 1024,
  [switch]$NoThink,
  [switch]$Play
)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$asr = Join-Path $repo "agent\asr-tools.py"
$tts = Join-Path $repo "agent\tts-tools.py"
$outRoot = Join-Path $repo $OutDir
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null

# --- 1) ASR: convert to text ---
if ($TextFile) { $Text = [System.IO.File]::ReadAllText($TextFile).Trim() }
if (-not $Text) {
    if (-not $Wav) { throw "Neither -Text nor -Wav was given." }
    if (-not $Model -and -not $AsrServerUrl) { throw "ASR needs -Model (whisper .bin) or -AsrServerUrl." }
    # Read the JSON from a FILE (UTF-8). Piping native stdout in PS 5.1 breaks the
    # encoding (pitfall #14): Turkish characters are decoded incorrectly.
    $asrJson = Join-Path $outRoot "asr.json"
    $asrErr = Join-Path $outRoot "asr.err.txt"
    $asrArgs = @($asr, "--wav", $Wav, "--lang", $Lang, "--out", $asrJson)
    if ($AsrServerUrl) { $asrArgs += @("--server-url", $AsrServerUrl) }
    else { $asrArgs += @("--model", $Model) }
    if ($Whisper) { $asrArgs += @("--whisper", $Whisper) }
    if ($AsrThreads -gt 0) { $asrArgs += @("--threads", $AsrThreads) }
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # do not treat native stderr (warnings/tqdm) as an error
    & $Python @asrArgs 1> $null 2> $asrErr
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldEap
    if ($code -ne 0 -or -not (Test-Path $asrJson)) {
        throw "ASR failed (exit $code); error: $asrErr"
    }
    $asrOut = Get-Content -Raw -Encoding UTF8 $asrJson | ConvertFrom-Json
    if (-not $asrOut.ok) { throw "ASR failed: $($asrOut.error)" }
    $r0 = $asrOut.results[0]
    Write-Host ("[ASR] {0} s audio -> {1} s (RTF {2}, threads {3})" -f `
        $r0.audio_seconds, $r0.asr_seconds, $r0.rtf, $asrOut.threads)
    $Text = $r0.text
}
Write-Host "[TEXT] $Text"

# --- 2) LLM: response (llama-server, OpenAI compatible) ---
$payload = @{
    messages    = @(
        @{ role = "system"; content = "Sen kisa ve dogal Turkce cevap veren bir sesli asistansin." },
        @{ role = "user"; content = $Text }
    )
    max_tokens  = $MaxTokens
    temperature = 0.7
    # Thinking is ON BY DEFAULT (disabled with -NoThink). Note: max_tokens also covers thinking.
    chat_template_kwargs = @{ enable_thinking = (-not $NoThink) }
} | ConvertTo-Json -Depth 6
try {
    $resp = Invoke-RestMethod -Method Post -Uri "$Server/v1/chat/completions" `
        -ContentType "application/json; charset=utf-8" `
        -Body ([Text.Encoding]::UTF8.GetBytes($payload))
} catch {
    throw "Could not reach the LLM server ($Server). Is 'llama-server' running? Detail: $($_.Exception.Message)"
}
$answer = $resp.choices[0].message.content
if (-not $answer) {
    if ($resp.choices[0].finish_reason -eq "length" -and $resp.choices[0].message.reasoning_content) {
        throw "LLM response was cut at the token limit (thinking is on; raise -MaxTokens or use -NoThink)."
    }
    throw "LLM returned an empty response."
}
Write-Host "[LLM] $answer"

# --- 3) Split into sentences ---
# Drop emoji/symbol-only fragments (TTS crashes on them); keep sentences containing letters/digits
$sentences = @([regex]::Split($answer, '(?<=[\.\!\?])\s+') |
    Where-Object { $_.Trim().Length -gt 0 -and ($_ -match '\p{L}|\p{N}') } |
    ForEach-Object { $_.Trim() })

# --- 4) TTS: convert the sentences to WAV ---
# chatterbox => BATCH MODE (model loaded once). Others / batch failure => per-sentence fallback.
$wavs = @()
function Invoke-TtsSingle([string]$Sentence, [int]$Index) {
    $txtFile = Join-Path $outRoot "tts_$Index.txt"
    $wavFile = Join-Path $outRoot "tts_$Index.wav"
    $jsonFile = Join-Path $outRoot "tts_$Index.json"
    $errFile = Join-Path $outRoot "tts_$Index.err.txt"
    # via a UTF-8 (no BOM) text file; keep the console encoding from corrupting the text
    [System.IO.File]::WriteAllText($txtFile, $Sentence, (New-Object System.Text.UTF8Encoding($false)))
    $ttsArgs = @($tts, "--backend", $Backend, "--lang", $Lang, "--text-file", $txtFile,
                 "--out", $wavFile, "--device", $Device, "--json-out", $jsonFile)
    if ($VoicePrompt) { $ttsArgs += @("--voice-prompt", $VoicePrompt) }
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # do not treat native stderr (tqdm/warnings) as an error
    & $Python @ttsArgs 1> $null 2> $errFile   # swallow stdout: JSON is read from the file
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldEap
    if ($code -ne 0 -or -not (Test-Path $jsonFile)) {
        Write-Warning "TTS ($Backend) failed (exit $code); error: $errFile"
        return $null
    }
    $out = Get-Content -Raw -Encoding UTF8 $jsonFile | ConvertFrom-Json
    if (-not $out.ok) { Write-Warning "TTS ($Backend) failed: $($out.error)"; return $null }
    return $wavFile
}

if ($sentences.Count -gt 0) {
    $batchOk = $false
    $batch = $null

    if ($Backend -eq "chatterbox" -and $TtsServerUrl) {
        # --- PERSISTENT SERVER: model already in memory -> generation only ---
        # A rare socket reset (WinError 10054) can happen on Windows loopback -> 2 attempts.
        # NO fallback to the local CLI: because the server keeps the model in VRAM, a second Chatterbox
        # would OOM; an honest error is returned instead of silent corruption.
        $body = @{ texts = @([string[]]$sentences); lang = $Lang; out_dir = $outRoot; prefix = "tts_" }
        if ($VoicePrompt) { $body.voice_prompt = $VoicePrompt }
        $attempt = 0
        while ($true) {
            $attempt++
            try {
                $batch = Invoke-RestMethod -Method Post -Uri "$TtsServerUrl/tts" -TimeoutSec 600 `
                    -ContentType "application/json; charset=utf-8" `
                    -Body ([Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 6)))
                break
            } catch {
                if ($attempt -ge 2) {
                    throw "Could not reach the TTS server ($TtsServerUrl, $attempt attempts). Is 'scripts\tts-server.ps1' running? Detail: $($_.Exception.Message)"
                }
                Write-Warning "TTS server connection dropped; retrying ($attempt)."
                Start-Sleep -Milliseconds 500
            }
        }
        if ($batch.ok) {
            Write-Host ("[TTS] SERVER: {0} sentences, generation {1} s, RTF {2}" -f `
                $batch.count, $batch.total_tts_seconds, $batch.rtf)
        } else {
            throw "TTS server returned an error: $($batch.error)"
        }
    }
    elseif ($Backend -eq "chatterbox") {
        # --- BATCH MODE (single process): model loaded once per call ---
        $batchFile = Join-Path $outRoot "tts_batch.txt"
        $jsonFile = Join-Path $outRoot "tts_batch.json"
        $errFile = Join-Path $outRoot "tts_batch.err.txt"
        # one sentence per line; UTF-8 (no BOM)
        [System.IO.File]::WriteAllLines($batchFile, [string[]]$sentences, (New-Object System.Text.UTF8Encoding($false)))
        $ttsArgs = @($tts, "--backend", $Backend, "--lang", $Lang,
                     "--batch-file", $batchFile, "--out-prefix", (Join-Path $outRoot "tts_"),
                     "--device", $Device, "--json-out", $jsonFile)
        if ($VoicePrompt) { $ttsArgs += @("--voice-prompt", $VoicePrompt) }
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $Python @ttsArgs 1> $null 2> $errFile   # swallow stdout: JSON is read from the file
        $code = $LASTEXITCODE
        $ErrorActionPreference = $oldEap
        if ($code -eq 0 -and (Test-Path $jsonFile)) {
            $batch = Get-Content -Raw -Encoding UTF8 $jsonFile | ConvertFrom-Json
            if ($batch.ok) {
                Write-Host ("[TTS] BATCH: {0} sentences, model load {1} s, generation {2} s, RTF {3}" -f `
                    $batch.count, $batch.load_seconds, $batch.total_tts_seconds, $batch.rtf)
            } else {
                Write-Warning "TTS batch mode failed: $($batch.error)"
            }
        } else {
            Write-Warning "TTS batch mode failed (exit $code); error: $errFile"
        }
    }

    # collect batch/server results (shared)
    if ($batch -and $batch.ok) {
        foreach ($r in $batch.results) {
            $w = $r.out
            # Defence: `out` in the JSON may be stale/missing (e.g. guard retry) ->
            # fall back to the file name from the contract (prefix "tts_", 1-based index).
            if (-not $w -or -not (Test-Path -LiteralPath $w)) {
                $alt = Join-Path $outRoot ("tts_{0}.wav" -f $r.index)
                if (Test-Path -LiteralPath $alt) { $w = $alt }
            }
            if ($r.ok -and $w -and (Test-Path -LiteralPath $w)) { $wavs += $w }
            else { Write-Warning "TTS sentence $($r.index) failed: $($r.error)" }
        }
        $batchOk = $true
    }
    if (-not $batchOk) {
        if ($Backend -eq "chatterbox") { Write-Warning "Batch TTS did not work; falling back to per-sentence (slow) mode." }
        $i = 0
        foreach ($s in $sentences) {
            $i++
            $w = Invoke-TtsSingle $s.Trim() $i
            if ($w) { $wavs += $w }
        }
    }
    foreach ($w in $wavs) { Write-Host "[TTS] $w" }
}

# --- 5) Play (optional) ---
if ($Play) { foreach ($w in $wavs) { (New-Object System.Media.SoundPlayer $w).PlaySync() } }
Write-Host "DONE. WAVs produced: $($wavs.Count)"
