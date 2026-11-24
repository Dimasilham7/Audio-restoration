$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"

Write-Host "==> Fetch binaries"
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "fetch-binaries.ps1")

Write-Host "==> Build frozen engine"
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build-engine.ps1")

Write-Host "==> Electron build + package"
Push-Location (Join-Path $Root "apps\desktop")
try {
  pnpm exec electron-vite build
  pnpm exec electron-builder --config electron-builder.yml --win
} finally {
  Pop-Location
}

Write-Host "==> Artifacts"
Get-ChildItem (Join-Path $Root "apps\desktop\release\*.exe") | Format-Table Name, Length
