$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root "apps\desktop\resources\engine\audiorestorer-engine.exe"
$Bin = Join-Path $Root "apps\desktop\resources\bin"
$Dataset = Join-Path $Root "eval\datasets\pixel-20261122"
$OutDir = Join-Path $Root "eval\output\frozen3"
$Report = Join-Path $Root "eval\reports\frozen_3clips.md"

if (-not (Test-Path $Exe)) { throw "Frozen engine missing: $Exe" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$env:AUDIORESTORER_BIN_DIR = $Bin
$env:PATH = "$Bin;$env:PATH"
$dfn = Join-Path $Root ".models\deepfilternet\deep-filter.exe"
if (Test-Path $dfn) { $env:AUDIORESTORER_DFN_EXE = $dfn }
elseif (Test-Path (Join-Path $Bin "deep-filter.exe")) { $env:AUDIORESTORER_DFN_EXE = (Join-Path $Bin "deep-filter.exe") }

# 3 clips: small / mid / larger among dataset
$all = Get-ChildItem (Join-Path $Dataset "*.mp4") | Sort-Object Length
if ($all.Count -lt 3) { throw "Need >=3 Pixel clips in $Dataset" }
$clips = @($all[0], $all[[Math]::Floor(($all.Count-1)/2)], $all[-1])

$lines = @("# Frozen engine — 3 Pixel clips", "", "Exe: ``$Exe``", "")
$fail = 0
foreach ($c in $clips) {
  $out = Join-Path $OutDir ($c.BaseName + ".restored.mp4")
  Write-Host "PROCESS $($c.Name) ($([math]::Round($c.Length/1MB,1)) MB) -> $out"
  & $Exe process $c.FullName -o $out
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) {
    $lines += "- FAIL ``$($c.Name)`` exit=$LASTEXITCODE"
    $fail++
  } else {
    $lines += "- PASS ``$($c.Name)`` -> ``$out`` ($([math]::Round((Get-Item $out).Length/1MB,2)) MB)"
  }
}

$lines += ""
$lines += "Result: $(if ($fail -eq 0) { 'ALL PASS' } else { "$fail FAILED" })"
$lines -join "`n" | Set-Content $Report -Encoding UTF8
Write-Host ($lines -join "`n")
if ($fail -ne 0) { exit 1 }
