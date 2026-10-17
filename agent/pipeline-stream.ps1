<#
    pipeline-stream.ps1 - AKISLI tur: ASR -> (LLM akisi -> cumle cumle TTS) -> oynat

    Fark: `pipeline.ps1` LLM yanitinin TAMAMINI bekleyip sonra TTS'i toplu yapar.
    Bu betikte LLM tokenlari akarken ilk cumle olusur olusmaz TTS'e gonderilir ve
    uretilen ses hemen calinir (boru hatti ilkesi #7). Amac: "ilk ses" gecikmesini
    dusurmek (asil dar bogaz).

    Gereksinim: kalici TTS sunucusu (`scripts\tts-server.ps1`, port 8082) ve
    `llama-server` (port 8080). Model yuklemesi tekrarlanmaz.

    Kullanim:
      pwsh -File agent\pipeline-stream.ps1 -Text "Merhaba, nasilsin?" `
           -TtsServerUrl http://127.0.0.1:8082
      pwsh -File agent\pipeline-stream.ps1 -Wav kayit.wav -AsrServerUrl http://127.0.0.1:8081 `
           -TtsServerUrl http://127.0.0.1:8082 -Play

    Not: Metinler ASCII tutuldu (Windows PowerShell 5.1 BOM'suz .ps1'i ANSI okur).
#>
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
    throw "Akisli hat icin kalici TTS sunucusu sart: -TtsServerUrl (or. http://127.0.0.1:8082)."
}

# --- 1) ASR (opsiyonel; -Text verilirse atlanir) ---
if ($TextFile) { $Text = [System.IO.File]::ReadAllText($TextFile).Trim() }
if (-not $Text) {
    if (-not $Wav) { throw "Ne -Text ne -Wav verildi." }
    if (-not $Model -and -not $AsrServerUrl) { throw "ASR icin -Model (whisper .bin) ya da -AsrServerUrl gerekli." }
    # JSON'u DOSYADAN oku (UTF-8) - stdout boru hatti PS 5.1'de kodlamayi bozar (tuzak #14).
    $asrJson = Join-Path $outRoot "asr.json"
    $asrErr = Join-Path $outRoot "asr.err.txt"
    $asrArgs = @($asr, "--wav", $Wav, "--lang", $Lang, "--out", $asrJson)
    if ($AsrServerUrl) { $asrArgs += @("--server-url", $AsrServerUrl) } else { $asrArgs += @("--model", $Model) }
    if ($Whisper) { $asrArgs += @("--whisper", $Whisper) }
    if ($AsrThreads -gt 0) { $asrArgs += @("--threads", $AsrThreads) }
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Python @asrArgs 1> $null 2> $asrErr
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldEap
    if ($code -ne 0 -or -not (Test-Path $asrJson)) { throw "ASR basarisiz (cikis $code); hata: $asrErr" }
    $asrOut = Get-Content -Raw -Encoding UTF8 $asrJson | ConvertFrom-Json
    if (-not $asrOut.ok) { throw "ASR basarisiz: $($asrOut.error)" }
    $r0 = $asrOut.results[0]
    Write-Host ("[ASR] {0} sn ses -> {1} sn (RTF {2}, threads {3})" -f `
        $r0.audio_seconds, $r0.asr_seconds, $r0.rtf, $asrOut.threads)
    $Text = $r0.text
}
Write-Host "[METIN] $Text"

# --- 2-3) AKISLI LLM -> cumle cumle TTS (llm-stream.py) ---
$jsonFile = Join-Path $outRoot "stream.json"
$errFile = Join-Path $outRoot "stream.err.txt"
$prefix = "s_"
$streamArgs = @($stream, "--text", $Text, "--server", $Server, "--tts-server", $TtsServerUrl,
                "--lang", $Lang, "--out-dir", $outRoot, "--prefix", $prefix,
                "--max-tokens", $MaxTokens, "--json-out", $jsonFile)
if ($NoThink) { $streamArgs += "--no-think" }
if ($Play) { $streamArgs += "--play" }

$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"   # native stderr (ilerleme/gunluk) hata sayilmasin
& $Python @streamArgs 1> $null 2> $errFile
$code = $LASTEXITCODE
$ErrorActionPreference = $oldEap

if ($code -ne 0 -or -not (Test-Path $jsonFile)) {
    if (Test-Path $errFile) { Get-Content $errFile -Tail 15 | ForEach-Object { Write-Host "  $_" } }
    throw "Akisli tur basarisiz (cikis $code). Gunluk: $errFile"
}
# JSON'u UTF-8 olarak oku (tuzak #14: PS 5.1 varsayilani ANSI -> yoldaki 'i' bozulur,
# Test-Path yanlis False verir ve WAV'lar 'kayip' gorunur).
$s = Get-Content -Raw -Encoding UTF8 $jsonFile | ConvertFrom-Json
Get-Content $errFile | Where-Object { $_ -match '^\s*\[' } | ForEach-Object { Write-Host $_ }
Write-Host "[AKIS] ilk parca $($s.first_token_seconds) sn ($($s.first_token_kind)) | ilk cumle $($s.first_sentence_seconds) sn | ILK SES $($s.first_audio_seconds) sn | LLM bitis $($s.llm_seconds) sn | toplam $($s.total_seconds) sn"
Write-Host "[LLM] $($s.answer)"

$wavs = @()
foreach ($r in $s.sentences) {
    $w = $r.out
    if (-not $w -or -not (Test-Path -LiteralPath $w)) {
        # Savunma: dosya adina dus. Sunucu adlandirmasi "<prefix><cumle>_<sunucu-index>.wav"
        # (her istekte tek cumle -> sunucu index'i daima 1) -> kalibi glob'la ara.
        $alt = Get-ChildItem -LiteralPath $outRoot -Filter ("{0}{1}_*.wav" -f $prefix, $r.index) `
            -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($alt) { $w = $alt.FullName }
    }
    if ($w -and (Test-Path -LiteralPath $w)) { $wavs += $w } else { Write-Warning "cumle $($r.index) WAV yok" }
}
foreach ($w in $wavs) { Write-Host "[TTS] $w" }
if (-not $s.ok) { throw "Akisli tur cumle uretemedi: $($s.error)" }
Write-Host "TAMAM. Uretilen WAV: $($wavs.Count)"
