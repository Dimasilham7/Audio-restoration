$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Bin = Join-Path $Root "apps\desktop\resources\bin"
$Lic = Join-Path $Root "apps\desktop\resources\licenses"
New-Item -ItemType Directory -Force -Path $Bin, $Lic | Out-Null

# DeepFilterNet Windows CLI (already may exist in .models)
$DfnSrc = Join-Path $Root ".models\deepfilternet\deep-filter.exe"
$DfnDst = Join-Path $Bin "deep-filter.exe"
if (-not (Test-Path $DfnDst)) {
  if (Test-Path $DfnSrc) {
    Copy-Item $DfnSrc $DfnDst
  } else {
    Write-Host "Downloading DeepFilterNet CLI..."
    $url = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-pc-windows-msvc.exe"
    Invoke-WebRequest -Uri $url -OutFile $DfnDst -UseBasicParsing
  }
}

# FFmpeg essentials — copy from local install if present, else download gyan essentials zip
$FfDst = Join-Path $Bin "ffmpeg.exe"
$FpDst = Join-Path $Bin "ffprobe.exe"
$LocalFf = "D:\tools\ffmpeg\ffmpeg-9.0.1-essentials_build\bin"
if (-not (Test-Path $FfDst)) {
  if (Test-Path (Join-Path $LocalFf "ffmpeg.exe")) {
    Copy-Item (Join-Path $LocalFf "ffmpeg.exe") $FfDst
    Copy-Item (Join-Path $LocalFf "ffprobe.exe") $FpDst
  } else {
    Write-Host "Downloading FFmpeg essentials..."
    $zip = Join-Path $env:TEMP "ffmpeg-essentials.zip"
    $url = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.1.1-essentials_build.zip"
    try {
      Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    } catch {
      # fallback known mirror pattern — user can place binaries manually
      throw "Could not download FFmpeg. Place ffmpeg.exe and ffprobe.exe in $Bin"
    }
    $extract = Join-Path $env:TEMP "ffmpeg-essentials"
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive $zip $extract
    $ff = Get-ChildItem $extract -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    $fp = Get-ChildItem $extract -Recurse -Filter ffprobe.exe | Select-Object -First 1
    if (-not $ff -or -not $fp) { throw "ffmpeg/ffprobe not found in archive" }
    Copy-Item $ff.FullName $FfDst
    Copy-Item $fp.FullName $FpDst
  }
}

# License notices
@"
FFmpeg is licensed under the GNU General Public License (GPL) version 2 or later
for this essentials build. Source code is available from https://ffmpeg.org and
the build provider (gyan.dev). AudioRestorer AI redistributes FFmpeg under GPL
with corresponding source offer.

DeepFilterNet CLI is dual-licensed MIT / Apache-2.0.
See https://github.com/Rikorose/DeepFilterNet
"@ | Set-Content (Join-Path $Lic "THIRD_PARTY.txt") -Encoding UTF8

# Record SHA-256 pins for audit
$Hashes = Join-Path $Lic "BINARIES_SHA256.txt"
Get-ChildItem $Bin -File | ForEach-Object {
  $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
  "{0}  {1}" -f $h, $_.Name
} | Set-Content $Hashes -Encoding ASCII
Write-Host "Wrote $Hashes"
Write-Host "Binaries ready in $Bin"
Get-ChildItem $Bin | Format-Table Name, Length
