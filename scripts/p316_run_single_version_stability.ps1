param(
  [string]$FirstPack = "artifacts/p313r1-hancom-capture-pack",
  [string]$OutRoot = "artifacts/p316-single-version",
  [int]$Repetitions = 3,
  [int]$Dpi = 144
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

if ($Repetitions -lt 3) {
  throw "P3.16 requires at least 3 fresh repetitions."
}

function Resolve-RepoPath([string]$PathValue) {
  if ([IO.Path]::IsPathRooted($PathValue)) { return $PathValue }
  return (Join-Path $RepoRoot $PathValue)
}

function Read-Json([string]$PathValue) {
  return Get-Content $PathValue -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Prepare-FrozenPack {
  param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
  )

  if (-not (Test-Path (Join-Path $Source "capture-ready-manifest.json"))) {
    throw "Source pack is missing capture-ready-manifest.json: $Source"
  }

  if (Test-Path $Destination) {
    Remove-Item $Destination -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force

  Get-ChildItem -Path $Destination -Directory -Recurse -Filter "capture" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

  foreach ($name in @(
    "windows-hancom-run-summary.json",
    "boundary-selection.json"
  )) {
    $path = Join-Path $Destination $name
    if (Test-Path $path) { Remove-Item -Force $path }
  }
}

$FirstPackResolved = Resolve-RepoPath $FirstPack
$SummaryPath = Join-Path $FirstPackResolved "windows-hancom-run-summary.json"
if (-not (Test-Path $SummaryPath)) {
  throw "Original Hancom summary missing: $SummaryPath"
}

$Original = Read-Json $SummaryPath
$HancomExe = [string]$Original.hancom_executable
$HancomVersion = [string]$Original.hancom_version
$HancomHash = [string]$Original.hancom_executable_sha256

if (-not (Test-Path $HancomExe)) {
  throw "Original Hancom executable no longer exists: $HancomExe"
}

$ExeItem = Get-Item $HancomExe
$CurrentVersion = $ExeItem.VersionInfo.ProductVersion
if (-not $CurrentVersion) { $CurrentVersion = $ExeItem.VersionInfo.FileVersion }
$CurrentHash = (Get-FileHash -Algorithm SHA256 -Path $HancomExe).Hash.ToLowerInvariant()
if (($CurrentVersion -ne $HancomVersion) -or ($CurrentHash -ne $HancomHash)) {
  throw "P3.14 Hancom executable identity drifted; P3.16 version-indexed replay must use the exact captured executable."
}

$OutResolved = Resolve-RepoPath $OutRoot
New-Item -ItemType Directory -Force -Path $OutResolved | Out-Null

$Venv = Join-Path $RepoRoot ".venv-p313r1"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

$RepeatArgs = @()
$SessionSummary = @{
  schema = "chatgpt-web-hwpx-mcp/single-version-run/p3.16/v1"
  renderer_version = $HancomVersion
  renderer_executable_sha256 = $HancomHash
  repetitions_requested = $Repetitions
  repetitions = @()
}

for ($i = 1; $i -le $Repetitions; $i++) {
  $name = "repeat-{0:d2}" -f $i
  $dir = Join-Path $OutResolved $name
  Prepare-FrozenPack -Source $FirstPackResolved -Destination $dir

  $FontBefore = Join-Path $dir "font-file-custody-before.json"
  $FontAfter = Join-Path $dir "font-file-custody-after.json"

  Write-Host ""
  Write-Host "P3.16 fresh replay $i/$Repetitions — $HancomVersion"

  & (Join-Path $PSScriptRoot "p315_font_file_custody.ps1") -OutFile $FontBefore
  if (-not $? -or -not (Test-Path $FontBefore)) {
    throw "Repeat $i pre-capture font custody failed."
  }

  $CaptureArgs = @{
    HancomExe = $HancomExe
    OutDir = $dir
    Dpi = $Dpi
    ReuseExistingPack = $true
  }
  & (Join-Path $PSScriptRoot "p313r1_run_hancom_capture.ps1") @CaptureArgs
  if ($LASTEXITCODE -ne 0) { throw "Repeat $i Hancom capture failed." }

  & (Join-Path $PSScriptRoot "p315_font_file_custody.ps1") -OutFile $FontAfter
  if (-not $? -or -not (Test-Path $FontAfter)) {
    throw "Repeat $i post-capture font custody failed."
  }

  $A = Read-Json $FontBefore
  $B = Read-Json $FontAfter
  if ($A.font_file_custody_sha256 -ne $B.font_file_custody_sha256) {
    throw "Repeat $i font-file custody changed during replay."
  }

  $RepeatArgs += @("--repeat", $dir, $FontAfter)
  $SessionSummary.repetitions += @{
    repetition = $i
    pack = $dir
    font_file_custody_sha256 = [string]$B.font_file_custody_sha256
  }
}

if (-not (Test-Path $VenvPython)) {
  throw "Capture virtual environment missing after replay."
}

$Receipt = Join-Path $OutResolved "p316-version-indexed-authority.json"
$Args = @("scripts/p316_build_version_indexed_authority.py")
$Args += $RepeatArgs
$Args += @("--out", $Receipt)

& $VenvPython @Args
$AdjudicationExit = $LASTEXITCODE

$SessionSummary.receipt = $Receipt
$SessionSummary.completed = ($AdjudicationExit -eq 0)
$SummaryOut = Join-Path $OutResolved "p316-run-summary.json"
$SessionSummary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $SummaryOut

$FinalZip = "$OutResolved.zip"
if (Test-Path $FinalZip) { Remove-Item -Force $FinalZip }
Compress-Archive -Path (Join-Path $OutResolved "*") -DestinationPath $FinalZip -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.16 single-version stability replay finished."
Write-Host "Renderer: $HancomVersion"
Write-Host "Repetitions: $Repetitions"
Write-Host "Receipt: $Receipt"
Write-Host "Evidence ZIP: $FinalZip"

exit $AdjudicationExit
