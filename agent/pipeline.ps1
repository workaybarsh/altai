#!/usr/bin/env pwsh
# pipeline.ps1 - ASR -> LLM -> TTS boru hatti (aybars_says)
#
# Akis:  WAV/Text -> whisper.cpp (asr-tools.py) -> llama-server (HTTP) -> cumlelere bol
#        -> TTS (tts-tools.py; TR icin chatterbox duzeltmeleri OTOMATIK) -> WAV'lar
#
# TTS TOPLU MOD: chatterbox icin cumleler TEK cagrida uretilir (--batch-file + --out-prefix),
#   boylece model BIR KEZ yuklenir (her cumlede ~13 sn + torch import ~8 sn tekrar etmez).
#   Beklenen kazanc: 2 cumlede ~57 sn -> ~15 sn. Baska backend'lerde cumle-cumle moda dusulur.
#
# TTS KALICI SUNUCU (-TtsServerUrl): model surekli bellekte kalir (scripts\tts-server.ps1);
#   her turda yalniz uretim kalir (yukleme tekrari tamamen biter). Oncelikli onerilen yol.
#
# Ornek:
#   pwsh -File agent\pipeline.ps1 -Text "Merhaba, nasilsin?" -Lang tr
#   pwsh -File agent\pipeline.ps1 -Wav kayit.wav -Model models\ggml-large-v3-turbo-q5_0.bin -AsrThreads 12
#   pwsh -File agent\pipeline.ps1 -Wav kayit.wav -AsrServerUrl http://127.0.0.1:8081 `
#        -TtsServerUrl http://127.0.0.1:8082
#
# Not: Bilesen (whisper / llama-server) yoksa DURUSTCE hata verir, uydurmaz.
#      TTS backend'leri (chatterbox/voxcpm) icin -Python olarak tts-venv python'u verin.
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

# --- 1) ASR: metne cevir ---
if ($TextFile) { $Text = [System.IO.File]::ReadAllText($TextFile).Trim() }
if (-not $Text) {
    if (-not $Wav) { throw "Ne -Text ne -Wav verildi." }
    if (-not $Model -and -not $AsrServerUrl) { throw "ASR icin -Model (whisper .bin) ya da -AsrServerUrl gerekli." }
    $asrArgs = @($asr, "--wav", $Wav, "--lang", $Lang)
    if ($AsrServerUrl) { $asrArgs += @("--server-url", $AsrServerUrl) }
    else { $asrArgs += @("--model", $Model) }
    if ($Whisper) { $asrArgs += @("--whisper", $Whisper) }
    if ($AsrThreads -gt 0) { $asrArgs += @("--threads", $AsrThreads) }
    $asrOut = & $Python @asrArgs | ConvertFrom-Json
    if (-not $asrOut.ok) { throw "ASR basarisiz: $($asrOut.error)" }
    $r0 = $asrOut.results[0]
    Write-Host ("[ASR] {0} sn ses -> {1} sn (RTF {2}, threads {3})" -f `
        $r0.audio_seconds, $r0.asr_seconds, $r0.rtf, $asrOut.threads)
    $Text = $r0.text
}
Write-Host "[METIN] $Text"

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
# Emoji/sembol-only parcalari at (TTS bunlarda coker); harf/rakam iceren cumleler kalsin
$sentences = @([regex]::Split($answer, '(?<=[\.\!\?])\s+') |
    Where-Object { $_.Trim().Length -gt 0 -and ($_ -match '\p{L}|\p{N}') } |
    ForEach-Object { $_.Trim() })

# --- 4) TTS: cumleleri WAV'a cevir ---
# chatterbox => TOPLU MOD (model bir kez yuklenir). Digerleri / toplu hata => cumle-cumle yedek.
$wavs = @()
function Invoke-TtsSingle([string]$Sentence, [int]$Index) {
    $txtFile = Join-Path $outRoot "tts_$Index.txt"
    $wavFile = Join-Path $outRoot "tts_$Index.wav"
    $jsonFile = Join-Path $outRoot "tts_$Index.json"
    $errFile = Join-Path $outRoot "tts_$Index.err.txt"
    # UTF-8 (BOM'suz) text-file ile; konsol kodlamasi metni bozmasin
    [System.IO.File]::WriteAllText($txtFile, $Sentence, (New-Object System.Text.UTF8Encoding($false)))
    $ttsArgs = @($tts, "--backend", $Backend, "--lang", $Lang, "--text-file", $txtFile,
                 "--out", $wavFile, "--device", $Device, "--json-out", $jsonFile)
    if ($VoicePrompt) { $ttsArgs += @("--voice-prompt", $VoicePrompt) }
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # native stderr (tqdm/uyari) hata sayilmasin
    & $Python @ttsArgs 1> $null 2> $errFile   # stdout'u yut: JSON dosyadan okunuyor
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldEap
    if ($code -ne 0 -or -not (Test-Path $jsonFile)) {
        Write-Warning "TTS ($Backend) basarisiz (cikis $code); hata: $errFile"
        return $null
    }
    $out = Get-Content -Raw $jsonFile | ConvertFrom-Json
    if (-not $out.ok) { Write-Warning "TTS ($Backend) basarisiz: $($out.error)"; return $null }
    return $wavFile
}

if ($sentences.Count -gt 0) {
    $batchOk = $false
    $batch = $null

    if ($Backend -eq "chatterbox" -and $TtsServerUrl) {
        # --- KALICI SUNUCU: model zaten bellekte -> yalniz uretim ---
        $body = @{ texts = @([string[]]$sentences); lang = $Lang; out_dir = $outRoot; prefix = "tts_" }
        if ($VoicePrompt) { $body.voice_prompt = $VoicePrompt }
        try {
            $batch = Invoke-RestMethod -Method Post -Uri "$TtsServerUrl/tts" -TimeoutSec 600 `
                -ContentType "application/json; charset=utf-8" `
                -Body ([Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 6)))
            if ($batch.ok) {
                Write-Host ("[TTS] SUNUCU: {0} cumle, uretim {1} sn, RTF {2}" -f `
                    $batch.count, $batch.total_tts_seconds, $batch.rtf)
            } else {
                Write-Warning "TTS sunucusu basarisiz: $($batch.error)"
            }
        } catch {
            Write-Warning "TTS sunucusuna ulasilamadi ($TtsServerUrl). 'scripts\tts-server.ps1' calisiyor mu? Detay: $($_.Exception.Message)"
        }
    }
    elseif ($Backend -eq "chatterbox") {
        # --- TOPLU MOD (tek surec): model cagri basina bir kez yuklenir ---
        $batchFile = Join-Path $outRoot "tts_batch.txt"
        $jsonFile = Join-Path $outRoot "tts_batch.json"
        $errFile = Join-Path $outRoot "tts_batch.err.txt"
        # her satir bir cumle; UTF-8 (BOM'suz)
        [System.IO.File]::WriteAllLines($batchFile, [string[]]$sentences, (New-Object System.Text.UTF8Encoding($false)))
        $ttsArgs = @($tts, "--backend", $Backend, "--lang", $Lang,
                     "--batch-file", $batchFile, "--out-prefix", (Join-Path $outRoot "tts_"),
                     "--device", $Device, "--json-out", $jsonFile)
        if ($VoicePrompt) { $ttsArgs += @("--voice-prompt", $VoicePrompt) }
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $Python @ttsArgs 1> $null 2> $errFile   # stdout'u yut: JSON dosyadan okunuyor
        $code = $LASTEXITCODE
        $ErrorActionPreference = $oldEap
        if ($code -eq 0 -and (Test-Path $jsonFile)) {
            $batch = Get-Content -Raw $jsonFile | ConvertFrom-Json
            if ($batch.ok) {
                Write-Host ("[TTS] TOPLU: {0} cumle, model yukleme {1} sn, uretim {2} sn, RTF {3}" -f `
                    $batch.count, $batch.load_seconds, $batch.total_tts_seconds, $batch.rtf)
            } else {
                Write-Warning "TTS toplu mod basarisiz: $($batch.error)"
            }
        } else {
            Write-Warning "TTS toplu mod basarisiz (cikis $code); hata: $errFile"
        }
    }

    # toplu/sunucu sonuclarini topla (ortak)
    if ($batch -and $batch.ok) {
        foreach ($r in $batch.results) {
            $w = $r.out
            # Savunma: JSON'daki `out` bayat/eksik olabilir (or. guard retry'i) ->
            # sozlesmedeki dosya adina dus (prefix "tts_", index 1-tabanli).
            if (-not $w -or -not (Test-Path -LiteralPath $w)) {
                $alt = Join-Path $outRoot ("tts_{0}.wav" -f $r.index)
                if (Test-Path -LiteralPath $alt) { $w = $alt }
            }
            if ($r.ok -and $w -and (Test-Path -LiteralPath $w)) { $wavs += $w }
            else { Write-Warning "TTS cumle $($r.index) basarisiz: $($r.error)" }
        }
        $batchOk = $true
    }
    if (-not $batchOk) {
        if ($Backend -eq "chatterbox") { Write-Warning "Toplu TTS olmadi; cumle-cumle (yavas) moda dusuluyor." }
        $i = 0
        foreach ($s in $sentences) {
            $i++
            $w = Invoke-TtsSingle $s.Trim() $i
            if ($w) { $wavs += $w }
        }
    }
    foreach ($w in $wavs) { Write-Host "[TTS] $w" }
}

# --- 5) Cal (opsiyonel) ---
if ($Play) { foreach ($w in $wavs) { (New-Object System.Media.SoundPlayer $w).PlaySync() } }
Write-Host "TAMAM. Uretilen WAV: $($wavs.Count)"
