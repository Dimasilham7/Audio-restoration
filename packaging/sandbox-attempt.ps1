$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Report = Join-Path $Root "eval\reports\sandbox_attempt.md"
$lines = @("# Windows Sandbox attempt", "", "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", "")

# Check feature
try {
  $feat = Get-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -ErrorAction Stop
  $lines += "- Feature state: **$($feat.State)**"
} catch {
  $lines += "- Feature query failed (likely needs elevation): $($_.Exception.Message)"
}

$wsb = Join-Path $env:TEMP "AudioRestorerSandbox.wsb"
$setup = Join-Path $Root "apps\desktop\release\AudioRestorer-AI-0.1.0-win-x64.exe"
$portable = Join-Path $Root "apps\desktop\release\AudioRestorer-AI-0.1.0-portable.exe"

$lines += "- Setup exists: $(Test-Path $setup)"
$lines += "- Portable exists: $(Test-Path $portable)"

@"
<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$($Root)\apps\desktop\release</HostFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>cmd /c echo AudioRestorer sandbox mapped release folder</Command>
  </LogonCommand>
</Configuration>
"@ | Set-Content $wsb -Encoding UTF8

$lines += "- Wrote WSB: $wsb"

if (Get-Command WindowsSandbox.exe -ErrorAction SilentlyContinue) {
  $lines += "- WindowsSandbox.exe: found"
  try {
    Start-Process "WindowsSandbox.exe" -ArgumentList $wsb -ErrorAction Stop
    $lines += "- Launch: attempted (manual verify inside sandbox per packaging/SANDBOX_TEST.md)"
  } catch {
    $lines += "- Launch failed: $($_.Exception.Message)"
  }
} else {
  $lines += "- WindowsSandbox.exe: **not available** (enable Windows Sandbox as admin, or use portable smoke)"
  $lines += "- Fallback: ran/use ``packaging/portable-smoke.ps1`` for offline bundled-engine proof"
}

$lines += ""
$lines += "## Checklist"
$lines += (Get-Content (Join-Path $Root "packaging\SANDBOX_TEST.md") -Raw)

New-Item -ItemType Directory -Force -Path (Split-Path $Report) | Out-Null
$lines -join "`n" | Set-Content $Report -Encoding UTF8
Write-Host "Wrote $Report"
Get-Content $Report | Select-Object -First 40
