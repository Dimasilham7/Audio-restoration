$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root "apps\desktop\release\AudioRestorer-AI-0.1.0-portable.exe"
$SpacedDir = Join-Path $Root "eval\output\USB Test Folder"
$Dst = Join-Path $SpacedDir "AudioRestorer AI portable.exe"
$Report = Join-Path $Root "eval\reports\portable_spaced_path.md"

if (-not (Test-Path $Src)) { throw "Portable exe missing: $Src" }
New-Item -ItemType Directory -Force -Path $SpacedDir | Out-Null
Copy-Item -Force $Src $Dst

# Clean PATH: no user Python/uv/ffmpeg — only System32 + Windows
$cleanPath = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
$wherePy = (cmd /c "set PATH=$cleanPath&& where python 2>nul")
$whereUv = (cmd /c "set PATH=$cleanPath&& where uv 2>nul")
$whereFf = (cmd /c "set PATH=$cleanPath&& where ffmpeg 2>nul")

$lines = @(
  "# Portable from spaced path",
  "",
  "- Source: ``$Src``",
  "- Launch path: ``$Dst``",
  "- Clean PATH python: $(if ($wherePy) { $wherePy } else { 'not found (good)' })",
  "- Clean PATH uv: $(if ($whereUv) { $whereUv } else { 'not found (good)' })",
  "- Clean PATH ffmpeg: $(if ($whereFf) { $whereFf } else { 'not found (good)' })",
  ""
)

# Also verify win-unpacked engine from spaced folder (automatable process test)
$UnpackedSrc = Join-Path $Root "apps\desktop\release\win-unpacked"
$SpacedApp = Join-Path $SpacedDir "AudioRestorer App"
if (Test-Path $SpacedApp) { Remove-Item -Recurse -Force $SpacedApp }
Copy-Item -Recurse $UnpackedSrc $SpacedApp
$Engine = Join-Path $SpacedApp "resources\engine\audiorestorer-engine.exe"
$Bin = Join-Path $SpacedApp "resources\bin"
$Sample = Get-ChildItem (Join-Path $Root "eval\datasets\pixel-20261122\*.mp4") | Sort-Object Length | Select-Object -First 1
$Out = Join-Path $SpacedDir "spaced_path_smoke.restored.mp4"

$env:AUDIORESTORER_BIN_DIR = $Bin
$env:PATH = "$Bin;$cleanPath"
$env:AUDIORESTORER_DFN_EXE = (Join-Path $Bin "deep-filter.exe")

Write-Host "Frozen engine from spaced win-unpacked copy..."
& $Engine analyze $Sample.FullName
$analyzeOk = ($LASTEXITCODE -eq 0)
& $Engine process $Sample.FullName -o $Out
$processOk = ($LASTEXITCODE -eq 0) -and (Test-Path $Out)

$lines += "- Spaced win-unpacked analyze: $(if ($analyzeOk) { 'PASS' } else { 'FAIL' })"
$lines += "- Spaced win-unpacked process: $(if ($processOk) { 'PASS' } else { 'FAIL' })"
$lines += "- Output: ``$Out``"

# Launch portable.exe briefly with clean PATH (GUI) — verify process starts
Write-Host "Launching portable.exe from spaced path (10s)..."
$p = Start-Process -FilePath $Dst -PassThru -WindowStyle Minimized
Start-Sleep -Seconds 10
$alive = -not $p.HasExited
$lines += "- Portable.exe process started: $(if ($alive -or ($p.ExitCode -eq $null)) { 'PASS' } else { "FAIL exit=$($p.ExitCode)" })"
$lines += "- Portable PID: $($p.Id) HasExited=$($p.HasExited)"
try {
  if (-not $p.HasExited) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    # kill child tree
    Start-Process taskkill -ArgumentList "/PID",$p.Id,"/T","/F" -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue
  }
} catch {}

$lines += ""
$ok = $analyzeOk -and $processOk
$lines += "Result: $(if ($ok) { 'PASS' } else { 'FAIL' })"
$lines -join "`n" | Set-Content $Report -Encoding UTF8
Write-Host ($lines -join "`n")
if (-not $ok) { exit 1 }
