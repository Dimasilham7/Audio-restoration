$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root "apps\desktop\resources\engine\audiorestorer-engine.exe"
$Bin = Join-Path $Root "apps\desktop\resources\bin"
$Sample = Get-ChildItem (Join-Path $Root "eval\datasets\pixel-20261122\*.mp4") | Sort-Object Length | Select-Object -First 1

if (-not (Test-Path $Exe)) { throw "Frozen engine missing. Run build-engine.ps1 first." }
if (-not $Sample) { throw "No sample video in eval/datasets/pixel-20261122" }

$env:AUDIORESTORER_BIN_DIR = $Bin
$env:PATH = "$Bin;$env:PATH"
$Out = Join-Path $Root "eval\output\smoke_frozen.restored.mp4"

Write-Host "Smoke analyze: $($Sample.Name)"
& $Exe analyze $Sample.FullName
if ($LASTEXITCODE -ne 0) { throw "analyze failed" }

Write-Host "Smoke process -> $Out"
& $Exe process $Sample.FullName -o $Out
if ($LASTEXITCODE -ne 0) { throw "process failed" }
Write-Host "OK: $Out"
