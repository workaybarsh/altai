#!/usr/bin/env pwsh
# altai-desktop.ps1 - minimal desktop UI for Altai (WinForms).
#
# Two steps:
#   1) "Load models"  -> starts llama-server (GPU, MTP), whisper-server (CPU) and the TTS
#                        server (Chatterbox by default, GPU) and waits until all three answer.
#   2) "Click to speak" -> records the microphone, releases -> ASR -> LLM -> TTS and plays
#                        the answer. Click again to stop recording.
#
# Requirements: pwsh 7, models\ and tools\ (see README), tts-venv for chatterbox.
#
# Examples:
#   pwsh -File altai-desktop.ps1
#   pwsh -File altai-desktop.ps1 -Backend chatterbox -NoThink
#   pwsh -File altai-desktop.ps1 -SelfTest -Wav logs\tts\piper-tr.wav   # no UI, headless check
#
# Note: text kept ASCII (Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI).

param(
    [string]$Lang = 'tr',
    [string]$Backend = 'chatterbox',
    [string]$Python,
    [string]$FwServerUrl = 'http://127.0.0.1:8083',
    [string]$AsrServerUrl = '',
    [string]$TtsServerUrl = 'http://127.0.0.1:8082',
    [string]$LlmServerUrl = 'http://127.0.0.1:8080',
    [switch]$NoThink,
    [switch]$KeepServices,
    [switch]$SelfTest,
    [string]$Wav
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$logRoot = Join-Path $root 'logs\ui'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

. (Join-Path $root 'agent\audio-capture.ps1')

$state = [hashtable]::Synchronized(@{
    Busy    = $false
    Ready   = $false
    Recording = $false
    Stopping = $false
    Msg     = 'Click "Load models" to put the models in VRAM.'
    Llm     = $false
    Asr     = $false
    Tts     = $false
    You     = ''
    Reply   = ''
    Latency = ''
    Error   = ''
    Vram    = ''
})

# ---------------------------------------------------------------- service control

$loadBlock = {
    param($root, $state, $backend, $python, $lang)

    function Test-ApiPort([int]$port) {
        try {
            $client = New-Object Net.Sockets.TcpClient
            $iar = $client.BeginConnect('127.0.0.1', $port, $null, $null)
            $ok = $iar.AsyncWaitHandle.WaitOne(300)
            $connected = ($ok -and $client.Connected)
            $client.Close()
            return $connected
        } catch {
            return $false
        }
    }

    function Test-TtsHealth {
        try {
            $h = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8082/health' -TimeoutSec 3
            if ($h.fatal) { throw "TTS fatal: $($h.fatal)" }
            return [bool]$h.ok
        } catch {
            return $false
        }
    }

    try {
        $state.Busy = $true
        $state.Error = ''
        $logs = Join-Path $root 'logs\ui'
        New-Item -ItemType Directory -Force -Path $logs | Out-Null

        if (-not (Test-ApiPort 8080)) {
            $state.Msg = 'Starting llama-server (GPU, MTP)...'
            $llama = Join-Path $root 'tools\llama\llama-server.exe'
            $model = 'models\Huihui-Qwen3.5-9B-abliterated.i1-Q5_K_M.gguf'
            if (-not (Test-Path -LiteralPath $llama)) { throw "llama-server not found: $llama" }
            if (-not (Test-Path -LiteralPath (Join-Path $root $model))) { throw "Model not found: $model" }
            Start-Process -FilePath $llama -WorkingDirectory $root -WindowStyle Hidden `
                -ArgumentList @('-m', $model, '-c', '4096', '-ngl', '99', '--host', '127.0.0.1',
                    '--port', '8080', '--spec-type', 'draft-mtp', '--reasoning', 'on',
                    '--reasoning-budget', '256') `
                -RedirectStandardOutput (Join-Path $logs 'llama.out.log') `
                -RedirectStandardError (Join-Path $logs 'llama.err.log') | Out-Null
        }

        if (-not (Test-ApiPort 8083)) {
            $state.Msg = 'Starting faster-whisper server (GPU)...'
            $fw = Join-Path $root 'scripts\fw-server.ps1'
            Start-Process -FilePath 'pwsh' -WindowStyle Hidden `
                -ArgumentList @('-NoProfile', '-File', $fw, '-Port', '8083') | Out-Null
        }

        if (-not (Test-ApiPort 8082)) {
            if ($backend -eq 'chatterbox') {
                $state.Msg = 'Starting TTS server (Chatterbox). First run downloads the model...'
            } else {
                $state.Msg = "Starting TTS server ($backend)..."
            }
            $ttsScript = Join-Path $root 'scripts\tts-server.ps1'
            $ttsArgs = @('-NoProfile', '-File', $ttsScript, '-Backend', $backend, '-Lang', $lang)
            if ($python) { $ttsArgs += @('-Python', $python) }
            Start-Process -FilePath 'pwsh' -WindowStyle Hidden -ArgumentList $ttsArgs | Out-Null
        }

        $deadline = (Get-Date).AddMinutes(15)
        while ((Get-Date) -lt $deadline) {
            if ($state.Stopping) { throw 'Cancelled (app is closing).' }
            $state.Llm = Test-ApiPort 8080
            $state.Asr = Test-ApiPort 8083
            $state.Tts = (Test-ApiPort 8082) -and (Test-TtsHealth)
            if ($state.Llm -and $state.Asr -and $state.Tts) { break }
            $state.Msg = "Waiting for services (LLM:$([int]$state.Llm) ASR:$([int]$state.Asr) TTS:$([int]$state.Tts))..."
            Start-Sleep -Milliseconds 800
        }
        if (-not ($state.Llm -and $state.Asr -and $state.Tts)) {
            throw 'Services did not come up. See logs\ui and logs\tts-server.err.log.'
        }
        $state.Ready = $true
        $state.Msg = 'Models loaded. Click "Click to speak", speak, then click again.'
    } catch {
        $state.Error = $_.Exception.Message
        $state.Msg = 'Load failed: ' + $_.Exception.Message
    } finally {
        $state.Busy = $false
    }
}

$turnBlock = {
    param($root, $wav, $state, $lang, $noThink, $asrUrl, $ttsUrl)

    try {
        $state.Busy = $true
        $state.Error = ''
        $state.Msg = 'Thinking...'
        $state.You = ''
        $state.Reply = ''
        $state.Latency = ''

        $outDir = Join-Path $root ('logs\ui\turn-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
        $script = Join-Path $root 'agent\pipeline-stream.ps1'
        $argv = @('-NoProfile', '-File', $script, '-Wav', $wav,
            '-AsrServerUrl', $asrUrl, '-TtsServerUrl', $ttsUrl,
            '-Lang', $lang, '-OutDir', $outDir, '-Play')
        if ($noThink) { $argv += '-NoThink' }

        $log = Join-Path $outDir 'turn.log'
        & pwsh @argv *> $log

        $lines = Get-Content -LiteralPath $log -Encoding UTF8
        $text = ($lines | Where-Object { $_ -match '^\[TEXT\]' } | Select-Object -First 1)
        $reply = ($lines | Where-Object { $_ -match '^\[LLM\]' -and $_ -notmatch 'first chunk' } | Select-Object -First 1)
        $lat = ($lines | Where-Object { $_ -match 'FIRST AUDIO' } | Select-Object -First 1)
        $state.You = ($text -replace '^\[TEXT\]\s*', '').Trim()
        $state.Reply = ($reply -replace '^\[LLM\]\s*', '').Trim()
        if (-not $state.Reply) {
            $err = ($lines | Where-Object { $_ -match 'TTS|error|Exception' } | Select-Object -Last 1)
            $state.Reply = "(no answer) $err"
        }
        $state.Latency = if ($lat) { ($lat -replace '^\[STREAM\]\s*', '').Trim() } else { '' }
        $state.Msg = 'Ready. Click "Click to speak".'
    } catch {
        $state.Error = $_.Exception.Message
        $state.Msg = 'Turn failed: ' + $_.Exception.Message
    } finally {
        $state.Busy = $false
    }
}

function Start-AltaiServices {
    $job = Start-ThreadJob -ArgumentList $loadBlock, $root, $state, $Backend, $Python, $Lang -ScriptBlock {
        param($blk, $r, $s, $b, $p, $l)
        & $blk $r $s $b $p $l
    }
    return $job
}

function Invoke-AltaiTurn([string]$wavPath) {
    $job = Start-ThreadJob -ArgumentList $turnBlock, $root, $wavPath, $state, $Lang, $NoThink.IsPresent, $AsrServerUrl, $TtsServerUrl -ScriptBlock {
        param($blk, $r, $w, $s, $l, $nt, $a, $t)
        & $blk $r $w $s $l $nt $a $t
    }
    return $job
}

function Stop-AltaiServices {
    $state.Stopping = $true
    Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    foreach ($s in 'tts-server.ps1', 'whisper-server.ps1') {
        $p = Join-Path $root "scripts\$s"
        if (Test-Path -LiteralPath $p) { & pwsh -NoProfile -File $p -Stop 2>$null | Out-Null }
    }

    # wait until the ports are really closed (max ~10 s) so VRAM is actually released
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline) {
        $open = $false
        foreach ($port in 8080, 8081, 8082) {
            try {
                $c = New-Object Net.Sockets.TcpClient
                $iar = $c.BeginConnect('127.0.0.1', $port, $null, $null)
                if ($iar.AsyncWaitHandle.WaitOne(150) -and $c.Connected) { $open = $true }
                $c.Close()
            } catch { }
        }
        if (-not $open) { break }
        Start-Sleep -Milliseconds 400
    }

    # last resort: leftover serving processes
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*tts-tools.py*--serve*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-Process -Name 'whisper-server' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

    $state.Ready = $false
    $state.Llm = $false
    $state.Asr = $false
    $state.Tts = $false
    $state.Msg = 'Services stopped. VRAM released.'
}

function Get-AltaiVram {
    try {
        $line = (& nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1)
        if (-not $line) { return '' }
        $parts = $line -split ','
        return ('VRAM {0:N1}/{1:N1} GB' -f ([double]$parts[0].Trim() / 1024), ([double]$parts[1].Trim() / 1024))
    } catch {
        return ''
    }
}

# ---------------------------------------------------------------- headless self-test

if ($SelfTest) {
    if (-not $Wav) { throw 'SelfTest needs -Wav <file>.' }
    Write-Host '[selftest] starting services...'
    & $loadBlock $root $state $Backend $Python $Lang
    if (-not $state.Ready) { throw "Services not ready: $($state.Error)" }
    Write-Host '[selftest] running one turn...'
    & $turnBlock $root (Resolve-Path -LiteralPath $Wav).Path $state $Lang $NoThink.IsPresent $AsrServerUrl $TtsServerUrl
    Write-Host "TRANSCRIPT: $($state.You)"
    Write-Host "REPLY: $($state.Reply)"
    Write-Host "LATENCY: $($state.Latency)"
    if ($state.Error) { Write-Host "ERROR: $($state.Error)" }
    if (-not $KeepServices) { Stop-AltaiServices }
    exit $(if ($state.Reply) { 0 } else { 1 })
}

# ---------------------------------------------------------------- UI

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Altai - local voice assistant'
$form.Size = New-Object System.Drawing.Size(820, 640)
$form.MinimumSize = New-Object System.Drawing.Size(640, 480)
$form.StartPosition = 'CenterScreen'
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 26, 32)
$form.ForeColor = [System.Drawing.Color]::FromArgb(232, 234, 240)

$top = New-Object System.Windows.Forms.Panel
$top.Dock = 'Top'
$top.Height = 74
$top.Padding = New-Object System.Windows.Forms.Padding(12, 10, 12, 6)
$form.Controls.Add($top)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.AutoSize = $true
$statusLabel.Font = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Regular)
$statusLabel.Text = 'LLM: -   ASR: -   TTS: -'
$top.Controls.Add($statusLabel)

$msgLabel = New-Object System.Windows.Forms.Label
$msgLabel.AutoSize = $false
$msgLabel.Location = New-Object System.Drawing.Point(12, 34)
$msgLabel.Size = New-Object System.Drawing.Size(500, 34)
$msgLabel.Font = New-Object System.Drawing.Font('Segoe UI', 9)
$msgLabel.ForeColor = [System.Drawing.Color]::FromArgb(160, 168, 184)
$msgLabel.Text = $state.Msg
$top.Controls.Add($msgLabel)

$loadBtn = New-Object System.Windows.Forms.Button
$loadBtn.Text = 'Load models'
$loadBtn.Size = New-Object System.Drawing.Size(130, 44)
$loadBtn.Location = New-Object System.Drawing.Point(530, 12)
$loadBtn.Anchor = 'Top,Right'
$loadBtn.FlatStyle = 'Flat'
$loadBtn.BackColor = [System.Drawing.Color]::FromArgb(58, 92, 160)
$loadBtn.ForeColor = [System.Drawing.Color]::White
$top.Controls.Add($loadBtn)

$stopBtn = New-Object System.Windows.Forms.Button
$stopBtn.Text = 'Stop'
$stopBtn.Size = New-Object System.Drawing.Size(90, 44)
$stopBtn.Location = New-Object System.Drawing.Point(668, 12)
$stopBtn.Anchor = 'Top,Right'
$stopBtn.FlatStyle = 'Flat'
$stopBtn.BackColor = [System.Drawing.Color]::FromArgb(70, 74, 88)
$stopBtn.ForeColor = [System.Drawing.Color]::White
$top.Controls.Add($stopBtn)

$log = New-Object System.Windows.Forms.RichTextBox
$log.Dock = 'Fill'
$log.ReadOnly = $true
$log.BackColor = [System.Drawing.Color]::FromArgb(18, 20, 26)
$log.ForeColor = [System.Drawing.Color]::FromArgb(225, 228, 236)
$log.BorderStyle = 'None'
$log.Font = New-Object System.Drawing.Font('Consolas', 10)
$log.HideSelection = $false
$log.Text = "Altai`r`n`r`n1) Click 'Load models' (llama.cpp on the GPU, whisper on the CPU, Chatterbox TTS).`r`n2) Click 'Click to speak', say something, click again.`r`n`r`n"
$form.Controls.Add($log)

$bottom = New-Object System.Windows.Forms.Panel
$bottom.Dock = 'Bottom'
$bottom.Height = 132
$bottom.Padding = New-Object System.Windows.Forms.Padding(12, 8, 12, 10)
$form.Controls.Add($bottom)

$talkBtn = New-Object System.Windows.Forms.Button
$talkBtn.Text = 'Click to speak'
$talkBtn.Dock = 'Fill'
$talkBtn.FlatStyle = 'Flat'
$talkBtn.Font = New-Object System.Drawing.Font('Segoe UI', 16, [System.Drawing.FontStyle]::Bold)
$talkBtn.BackColor = [System.Drawing.Color]::FromArgb(40, 120, 90)
$talkBtn.ForeColor = [System.Drawing.Color]::White
$talkBtn.Enabled = $false
$bottom.Controls.Add($talkBtn)

$thinkBox = New-Object System.Windows.Forms.CheckBox
$thinkBox.Text = 'Think (reasoning)'
$thinkBox.Checked = -not $NoThink.IsPresent
$thinkBox.AutoSize = $true
$thinkBox.Dock = 'Bottom'
$thinkBox.ForeColor = [System.Drawing.Color]::FromArgb(170, 176, 190)
$thinkBox.Padding = New-Object System.Windows.Forms.Padding(4, 6, 0, 0)
$bottom.Controls.Add($thinkBox)

function Append-Log([string]$who, [string]$text) {
    if (-not $text) { return }
    $color = if ($who -eq 'You') { [System.Drawing.Color]::FromArgb(140, 190, 255) } else { [System.Drawing.Color]::FromArgb(160, 230, 180) }
    $log.SelectionStart = $log.TextLength
    $log.SelectionColor = $color
    $log.AppendText("${who}: ")
    $log.SelectionColor = $log.ForeColor
    $log.AppendText("$text`r`n`r`n")
    $log.ScrollToCaret()
}

$loadBtn.Add_Click({
    if ($state.Busy) { return }
    $log.AppendText("Loading...`r`n")
    Start-AltaiServices | Out-Null
})

$stopBtn.Add_Click({
    if ($state.Busy) { return }
    Stop-AltaiServices
    $talkBtn.Enabled = $false
    $log.AppendText("Services stopped.`r`n")
})

$talkBtn.Add_Click({
    if ($state.Busy) { return }
    if (-not $state.Ready) { return }

    if (-not $state.Recording) {
        try {
            Start-AltaiRecording | Out-Null
            $state.Recording = $true
            $talkBtn.Text = 'Listening... click to stop'
            $talkBtn.BackColor = [System.Drawing.Color]::FromArgb(160, 70, 60)
            $state.Msg = 'Recording... click again when you finish speaking.'
        } catch {
            [System.Windows.Forms.MessageBox]::Show("Microphone could not be opened: $($_.Exception.Message)", 'Altai')
        }
        return
    }

    $state.Recording = $false
    $talkBtn.Text = 'Click to speak'
    $talkBtn.BackColor = [System.Drawing.Color]::FromArgb(40, 120, 90)
    try {
        $dest = Join-Path $logRoot ('rec-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.wav')
        $wavPath = Stop-AltaiRecording -Destination $dest
    } catch {
        [System.Windows.Forms.MessageBox]::Show("Recording failed: $($_.Exception.Message)", 'Altai')
        return
    }
    $log.AppendText("(recorded $([math]::Round((Get-Item -LiteralPath $wavPath).Length / 1KB)) KB)`r`n")
    Invoke-AltaiTurn $wavPath | Out-Null
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 350
$script:ticks = 0
$timer.Add_Tick({
    $script:ticks++
    $statusLabel.Text = ('LLM: {0}   ASR: {1}   TTS: {2}   {3}' -f `
        $(if ($state.Llm) { 'up' } else { '-' }), `
        $(if ($state.Asr) { 'up' } else { '-' }), `
        $(if ($state.Tts) { 'up' } else { '-' }), $state.Vram)
    if ($script:ticks % 6 -eq 0) { $state.Vram = Get-AltaiVram }
    $msgLabel.Text = if ($state.Recording) { "Recording... $((Get-AltaiRecordingSeconds)) s" } else { $state.Msg }

    $talkBtn.Enabled = ($state.Ready -and -not $state.Busy)
    if ($state.Busy -and -not $state.Recording) { $talkBtn.Text = 'Working...' }
    elseif (-not $state.Recording -and -not $state.Busy) { $talkBtn.Text = 'Click to speak' }

    if ($state.You) { Append-Log 'You' $state.You; $state.You = '' }
    if ($state.Reply) { Append-Log 'Altai' $state.Reply; $state.Reply = '' }
    if ($state.Latency) { $log.AppendText("($($state.Latency))`r`n`r`n"); $state.Latency = '' }
})
$timer.Start()

$form.Add_FormClosing({
    $state.Stopping = $true
    $timer.Stop()
    if ($state.Recording) { try { Stop-AltaiRecording | Out-Null } catch { } }
    if (-not $KeepServices) { Stop-AltaiServices }
})

try {
    [void]$form.ShowDialog()
} finally {
    if (-not $KeepServices) {
        Stop-AltaiServices
        $state.Vram = Get-AltaiVram
    }
}
