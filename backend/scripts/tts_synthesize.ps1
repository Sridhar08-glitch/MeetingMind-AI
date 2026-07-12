<#
    tts_synthesize.ps1 — offline multi-voice speech synthesis for MeetingMind demo media.

    Reads a UTF-8 JSON spec:  { "out": "<wav path>", "lines": [ {"voice": "...", "rate": 0, "text": "..."} ] }
    and writes a single WAV containing every line spoken in sequence, switching the
    local Windows SAPI voice/rate per line. 100% local — no cloud, no paid API.

    Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -File tts_synthesize.ps1 -Spec <json path>
#>
param([Parameter(Mandatory = $true)][string]$Spec)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$data = Get-Content -Raw -Encoding UTF8 -LiteralPath $Spec | ConvertFrom-Json

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.SetOutputToWaveFile($data.out)
    foreach ($line in $data.lines) {
        try { $synth.SelectVoice([string]$line.voice) } catch { }  # fall back to default voice
        try { $synth.Rate = [int]$line.rate } catch { $synth.Rate = 0 }
        $text = [string]$line.text
        if ($text.Trim().Length -gt 0) { $synth.Speak($text) }
    }
}
finally {
    $synth.Dispose()
}
Write-Output "OK"
