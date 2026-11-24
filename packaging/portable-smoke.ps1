$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Unpacked = Join-Path $Root "apps\desktop\release\win-unpacked"
$Exe = Join-Path $Unpacked "resources\engine\audiorestorer-engine.exe"
$Bin = Join-Path $Unpacked "resources\bin"
$Sample = Get-ChildItem (Join-Path $Root "eval\datasets\pixel-20261122\*.mp4") | Sort-Object Length | Select-Object -First 1

if (-not (Test-Path $Exe)) { throw "Missing unpacked engine: $Exe" }
if (-not $Sample) { throw "Missing sample video" }

$env:AUDIORESTORER_BIN_DIR = $Bin
$env:PATH = "$Bin;$env:PATH"
$Out = Join-Path $Root "eval\output\acceptance\portable_smoke.restored.mp4"
New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null

Write-Host "Portable layout smoke via bundled engine..."
& $Exe analyze $Sample.FullName
if ($LASTEXITCODE -ne 0) { throw "analyze failed" }
& $Exe process $Sample.FullName -o $Out
if ($LASTEXITCODE -ne 0) { throw "process failed" }
Write-Host "PASS portable smoke -> $Out"
