$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Engine = Join-Path $Root "engine"
$OutRes = Join-Path $Root "apps\desktop\resources\engine"

Write-Host "Building frozen engine with PyInstaller..."
Push-Location $Engine
try {
  uv sync --extra dev
  uv run pyinstaller --noconfirm --clean packaging\engine.spec
  $dist = Join-Path $Engine "dist\audiorestorer-engine"
  if (-not (Test-Path $dist)) { throw "PyInstaller output missing: $dist" }
  New-Item -ItemType Directory -Force -Path (Split-Path $OutRes) | Out-Null
  if (Test-Path $OutRes) { Remove-Item -Recurse -Force $OutRes }
  Copy-Item -Recurse $dist $OutRes
  Write-Host "Copied engine -> $OutRes"
} finally {
  Pop-Location
}
