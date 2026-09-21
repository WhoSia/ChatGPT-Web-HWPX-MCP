param(
  [string]$FirstPack = "artifacts/p313r1-hancom-capture-pack",
  [string]$OutRoot = "artifacts/p315-cross-version",
  [string]$SecondHancomExe = "",
  [int]$Dpi = 144
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Resolve-RepoPath([string]$PathValue) {
  if ([IO.Path]::IsPathRooted($PathValue)) { return $PathValue }
  return (Join-Path $RepoRoot $PathValue)
}

function Read-Json([string]$PathValue) {
  return Get-Content $PathValue -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-HwpCandidates {
  $roots = @(
    (Join-Path $env:ProgramFiles "Hnc"),
    (Join-Path ${env:ProgramFiles(x86)} "Hnc"),
    (Join-Path $env:ProgramFiles "Hancom")
  ) | Where-Object { $_ -and (Test-Path $_) }

  $rows = @()
  foreach ($root in $roots) {
    Get-ChildItem -Path $root -Filter "Hwp.exe" -File -Recurse -ErrorAction SilentlyContinue |
      ForEach-Object {
        try {
          $version = $_.VersionInfo.ProductVersion
          if (-not $version) { $version = $_.VersionInfo.FileVersion }
          $hash = (Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLowerInvariant()
          $rows += @{
            path = $_.FullName
            version = [string]$version
            sha256 = $hash
          }
        } catch {}
      }
  }

  return @(
    $rows |
      Sort-Object version, path -Unique
  )
}

function Prepare-FrozenPack {
  param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
  )

  if (-not (Test-Path (Join-Path $Source "capture-ready-manifest.json"))) {
    throw "First pack is missing capture-ready-manifest.json: $Source"
  }

  if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
  }

  Get-ChildItem -Path $Destination -Directory -Recurse -Filter "capture" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

  foreach ($name in @("windows-hancom-run-summary.json", "boundary-selection.json")) {
    $path = Join-Path $Destination $name
    if (Test-Path $path) { Remove-Item -Force $path }
  }
}

$FirstPackResolved = Resolve-RepoPath $FirstPack
$OriginalSummaryPath = Join-Path $FirstPackResolved "windows-hancom-run-summary.json"
if (-not (Test-Path $OriginalSummaryPath)) {
  throw "Original P3.14 summary missing: $OriginalSummaryPath"
}

$OriginalSummary = Read-Json $OriginalSummaryPath
$FirstExe = [string]$OriginalSummary.hancom_executable
$FirstVersion = [string]$OriginalSummary.hancom_version
$FirstHash = [string]$OriginalSummary.hancom_executable_sha256

if (-not (Test-Path $FirstExe)) {
  throw "Original Hancom executable no longer exists: $FirstExe"
}

$Candidates = Get-HwpCandidates
$DiscoveryOut = Resolve-RepoPath (Join-Path $OutRoot "hancom-version-discovery.json")
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DiscoveryOut) | Out-Null
$Candidates | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $DiscoveryOut

$Second = $null
if ($SecondHancomExe) {
  $resolved = (Resolve-Path $SecondHancomExe).Path
  $item = Get-Item $resolved
  $version = $item.VersionInfo.ProductVersion
  if (-not $version) { $version = $item.VersionInfo.FileVersion }
  $hash = (Get-FileHash -Algorithm SHA256 -Path $resolved).Hash.ToLowerInvariant()
  $Second = @{
    path = $resolved
    version = [string]$version
    sha256 = $hash
  }
} else {
  $Second = $Candidates |
    Where-Object {
      ($_.version -ne $FirstVersion) -and
      ($_.sha256 -ne $FirstHash)
    } |
    Select-Object -First 1
}

if (-not $Second) {
  Write-Host ""
  Write-Host "P3.15 preparation complete, but no second distinct Hancom version was found."
  Write-Host "Discovery receipt: $DiscoveryOut"
  Write-Host "First version: $FirstVersion"
  Write-Host "Re-run later with -SecondHancomExe 'C:\path\to\other\Hwp.exe'."
  exit 3
}

if (($Second.version -eq $FirstVersion) -or ($Second.sha256 -eq $FirstHash)) {
  throw "SecondHancomExe must be a distinct Hancom version and executable."
}

$OutResolved = Resolve-RepoPath $OutRoot
$VersionA = Join-Path $OutResolved "version-a"
$VersionB = Join-Path $OutResolved "version-b"
Prepare-FrozenPack -Source $FirstPackResolved -Destination $VersionA
Prepare-FrozenPack -Source $FirstPackResolved -Destination $VersionB

$FontA = Join-Path $VersionA "font-file-custody.json"
$FontB = Join-Path $VersionB "font-file-custody.json"

Write-Host "P3.15 VERSION A fresh replay: $FirstVersion"
& (Join-Path $PSScriptRoot "p315_font_file_custody.ps1") -OutFile $FontA
if ($LASTEXITCODE -ne 0) { throw "Version A font custody failed." }

& (Join-Path $PSScriptRoot "p313r1_run_hancom_capture.ps1") `
  -HancomExe $FirstExe `
  -OutDir $VersionA `
  -Dpi $Dpi `
  -ReuseExistingPack
if ($LASTEXITCODE -ne 0) { throw "Version A fresh replay failed." }

Write-Host "P3.15 VERSION B fresh replay: $($Second.version)"
& (Join-Path $PSScriptRoot "p315_font_file_custody.ps1") -OutFile $FontB
if ($LASTEXITCODE -ne 0) { throw "Version B font custody failed." }

& (Join-Path $PSScriptRoot "p313r1_run_hancom_capture.ps1") `
  -HancomExe $Second.path `
  -OutDir $VersionB `
  -Dpi $Dpi `
  -ReuseExistingPack
if ($LASTEXITCODE -ne 0) { throw "Version B fresh replay failed." }

$Venv = Join-Path $RepoRoot ".venv-p313r1"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  throw "Capture virtual environment missing after replay."
}

$Receipt = Join-Path $OutResolved "p315-cross-version-replay.json"
& $VenvPython scripts/p315_build_cross_version_replay.py `
  --first-pack $VersionA `
  --first-font-custody $FontA `
  --second-pack $VersionB `
  --second-font-custody $FontB `
  --out $Receipt
$ReplayExit = $LASTEXITCODE

$FinalZip = "$OutResolved.zip"
if (Test-Path $FinalZip) { Remove-Item -Force $FinalZip }
Compress-Archive -Path (Join-Path $OutResolved "*") -DestinationPath $FinalZip -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.15 cross-version replay finished."
Write-Host "Version A: $FirstVersion"
Write-Host "Version B: $($Second.version)"
Write-Host "Receipt: $Receipt"
Write-Host "Evidence ZIP: $FinalZip"

exit $ReplayExit
