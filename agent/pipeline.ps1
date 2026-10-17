#!/usr/bin/env pwsh
# pipeline.ps1 - ASR -> LLM -> TTS boru hatti (aybars_says)  [ISKELET]
#
# Akis:  WAV/Text -> whisper.cpp (asr-tools.py) -> llama-server (HTTP) -> cumlelere bol
#        -> TTS (tts-tools.py; TR icin chatterbox duzeltmeleri OTOMATIK) -> WAV'lar
#
# Ornek:
#   pwsh -File agent\pipeline.ps1 -Text "Merhaba, nasilsin?" -Lang tr
#   pwsh -File agent\pipeline.ps1 -Wav kayit.wav -Model models\ggml-large-v3-turbo.bin
#
# Not: Bilesen (whisper / llama-server) yoksa DURUSTCE hata verir, uydurmaz.
#      TTS backend'leri (chatterbox/voxcpm) icin -Python olarak tts-venv python'u verin.
param(
  [string]$Wav,
  [string]$Text,
  [string]$TextFile,
  [string]$Server = "http://127.0.0.1:8080",
  [string]$Model,
  [string]$Lang = "tr",
  [string]$Backend = "chatterbox",
  [string]$Device = "cuda",
  [string]$Python = "python",
  [string]$OutDir = "logs\pipeline",
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

# --- 1) ASR: metne cevir ---
if ($TextFile) { $Text = [System.IO.File]::ReadAllText($TextFile).Trim() }
if (-not $Text) {
    if (-not $Wav) { throw "Ne -Text ne -Wav verildi." }
    if (-not $Model) { throw "ASR icin -Model (whisper .bin) gerekli." }
    $asrOut = & $Python $asr --wav $Wav --model $Model --lang $Lang | ConvertFrom-Json
    if (-not $asrOut.ok) { throw "ASR basarisiz: $($asrOut.error)" }
    $Text = $asrOut.results[0].text
}
Write-Host "[ASR] $Text"

# --- 2) LLM: yanit (llama-server, OpenAI uyumlu) ---
$payload = @{
    messages    = @(
        @{ role = "system"; content = "Sen kisa ve dogal Turkce cevap veren bir sesli asistansin." },
        @{ role = "user"; content = $Text }
    )
    max_tokens  = $MaxTokens
    temperature = 0.7
    # Dusunme VARSAYILAN ACIK (NoThink ile kapatilir). Not: max_tokens dusunmeyi de kapsar.
    chat_template_kwargs = @{ enable_thinking = (-not $NoThink) }
} | ConvertTo-Json -Depth 6
try {
    $resp = Invoke-RestMethod -Method Post -Uri "$Server/v1/chat/completions" `
        -ContentType "application/json; charset=utf-8" `
        -Body ([Text.Encoding]::UTF8.GetBytes($payload))
} catch {
    throw "LLM sunucusuna ulasilamadi ($Server). 'llama-server' calisiyor mu? Detay: $($_.Exception.Message)"
}
$answer = $resp.choices[0].message.content
if (-not $answer) {
    if ($resp.choices[0].finish_reason -eq "length" -and $resp.choices[0].message.reasoning_content) {
        throw "LLM cevabi token limitinde kesildi (dusunme acik; -MaxTokens artir ya da -NoThink kullan)."
    }
    throw "LLM bos cevap dondurdu."
}
Write-Host "[LLM] $answer"

# --- 3) Cumlelere bol ---
$sentences = [regex]::Split($answer, '(?<=[\.\!\?])\s+') | Where-Object { $_.Trim().Length -gt 0 }

# --- 4) TTS: her cumle -> WAV (UTF-8 text-file ile; konsol kodlamasi bozmasin) ---
$wavs = @()
$i = 0
foreach ($s in $sentences) {
    $i++
    $txtFile = Join-Path $outRoot "tts_$i.txt"
    $wavFile = Join-Path $outRoot "tts_$i.wav"
    [System.IO.File]::WriteAllText($txtFile, $s.Trim(), (New-Object System.Text.UTF8Encoding($false)))
    $jsonFile = Join-Path $outRoot "tts_$i.json"
    $errFile = Join-Path $outRoot "tts_$i.err.txt"
    $ttsArgs = @($tts, "--backend", $Backend, "--lang", $Lang, "--text-file", $txtFile,
                 "--out", $wavFile, "--device", $Device, "--json-out", $jsonFile)
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # native stderr (tqdm/uyari) hata sayilmasin
    & $Python @ttsArgs 2> $errFile
    $ttsCode = $LASTEXITCODE
    $ErrorActionPreference = $oldEap
    if ($ttsCode -ne 0 -or -not (Test-Path $jsonFile)) {
        Write-Warning "TTS ($Backend) basarisiz (cikis $ttsCode); hata: $errFile"
        continue
    }
    $ttsOut = Get-Content -Raw $jsonFile | ConvertFrom-Json
    if (-not $ttsOut.ok) { Write-Warning "TTS ($Backend) basarisiz: $($ttsOut.error)"; continue }
    $wavs += $wavFile
    Write-Host "[TTS] $wavFile"
}

# --- 5) Cal (opsiyonel) ---
if ($Play) { foreach ($w in $wavs) { (New-Object System.Media.SoundPlayer $w).PlaySync() } }
Write-Host "TAMAM. Uretilen WAV: $($wavs.Count)"
