param(
  [switch]$RebuildVenv,
  [string]$HancomExe = "",
  [int]$Dpi = 144,
  [int]$MaxAttempts = 3
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

if ($Dpi -le 0) { throw "Dpi must be positive." }
if ($MaxAttempts -lt 1 -or $MaxAttempts -gt 3) { throw "MaxAttempts must be between 1 and 3." }

. (Join-Path $PSScriptRoot "common/EnvBootstrap.ps1")
. (Join-Path $PSScriptRoot "common/HancomExport.ps1")

$Python = Initialize-HwpxEnvironment -RepoRoot $RepoRoot -RebuildVenv:$RebuildVenv
$HancomExe = Find-HwpxHancomExe -Explicit $HancomExe
$HancomItem = Get-Item -LiteralPath $HancomExe
$HancomVersion = $HancomItem.VersionInfo.ProductVersion
if (-not $HancomVersion) { $HancomVersion = $HancomItem.VersionInfo.FileVersion }
$HancomHash = (Get-FileHash -LiteralPath $HancomExe -Algorithm SHA256).Hash.ToLowerInvariant()
$RunnerHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$ExportHelper = Join-Path $PSScriptRoot "p313r1_hancom_export_once.ps1"
$CommonExportHelper = Join-Path $PSScriptRoot "common/HancomExport.ps1"
$CommonExportHash = (Get-FileHash -LiteralPath $CommonExportHelper -Algorithm SHA256).Hash.ToLowerInvariant()

$Commit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $Commit -notmatch "^[0-9a-f]{40}$") {
  throw "Unable to resolve exact source commit."
}
$Tracked = & git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $Tracked) {
  throw "Tracked working tree changes prevent exact source custody. Commit or restore them first."
}

$RunId = "$($Commit.Substring(0,12))-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))"
$PackRoot = Join-Path $RepoRoot "artifacts/p341r1-authorbench-a3-capture-pack"
$RunDir = Join-Path $PackRoot "runs/$RunId"
$CapturedZip = Join-Path $RepoRoot "artifacts/p341r1-authorbench-a3-capture-pack-captured.zip"
$HistoryDir = Join-Path $RepoRoot "artifacts/p341r1-authorbench-a3-capture-history"
New-Item -ItemType Directory -Force -Path $PackRoot | Out-Null

if (Test-Path -LiteralPath $CapturedZip) {
  New-Item -ItemType Directory -Force -Path $HistoryDir | Out-Null
  $oldHash = (Get-FileHash -LiteralPath $CapturedZip -Algorithm SHA256).Hash.ToLowerInvariant()
  $archive = Join-Path $HistoryDir "$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))-$($oldHash.Substring(0,16)).zip"
  Move-Item -LiteralPath $CapturedZip -Destination $archive
  Write-Host "Preserved previous captured ZIP: $archive"
}

& $Python scripts/p341r1_materialize_capture_pack.py --out $RunDir
if ($LASTEXITCODE -ne 0) { throw "P3.41-R1 fixture materialization failed." }

$ManifestPath = Join-Path $RunDir "capture-ready-manifest.json"
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.source.runner_commit -ne $Commit) {
  throw "Materialized source commit mismatch."
}

$Summary = [ordered]@{
  schema = "authorbench/p341r1-windows-run-summary/v1"
  phase = "P3.41-R1"
  run_id = $RunId
  source_commit = $Commit
  frozen_benchmark_commit = $Manifest.benchmark_authority.frozen_commit
  frozen_workflow_run = $Manifest.benchmark_authority.workflow_run
  hancom_executable = $HancomExe
  hancom_version = $HancomVersion
  hancom_executable_sha256 = $HancomHash
  common_export_helper_sha256 = $CommonExportHash
  dpi = $Dpi
  succeeded = @()
  failed = @()
}

foreach ($Fixture in $Manifest.fixtures) {
  $FixtureDir = Join-Path $RunDir "fixtures/$($Fixture.fixture_id)"
  $Input = Join-Path $RunDir $Fixture.path
  $ActualHash = (Get-FileHash -LiteralPath $Input -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($ActualHash -ne $Fixture.sha256) {
    throw "Pre-render fixture hash mismatch: $($Fixture.fixture_id)"
  }

  $CaptureDir = Join-Path $FixtureDir "capture"
  New-Item -ItemType Directory -Force -Path $CaptureDir | Out-Null
  $Pdf = Join-Path $CaptureDir "hancom-render.pdf"
  Write-Host ""
  Write-Host "Capture: $($Fixture.fixture_id) [$($Fixture.archetype)]"

  try {
    Export-HwpxHancomPdfWithRetry -InputPath $Input -OutputPath $Pdf -HelperScript $ExportHelper -MaxAttempts $MaxAttempts
    & $Python scripts/p341r1_capture_pdf.py --pack $RunDir --fixture-id $Fixture.fixture_id --pdf $Pdf --hancom-version $HancomVersion --hancom-sha256 $HancomHash --dpi $Dpi --runner-sha256 $RunnerHash
    if ($LASTEXITCODE -ne 0) { throw "Raster/page-composition custody extraction failed." }
    $Diagnostic = Get-Content -LiteralPath (Join-Path $CaptureDir "page-composition-diagnostic.json") -Raw | ConvertFrom-Json
    $Summary.succeeded += @{
      fixture_id = $Fixture.fixture_id
      archetype = $Fixture.archetype
      source_sha256 = $ActualHash
      page_count = $Diagnostic.page_count
      composition_verdict = $Diagnostic.verdict
      composition_finding_count = $Diagnostic.finding_count
    }
  } catch {
    $Failure = @{
      fixture_id = $Fixture.fixture_id
      archetype = $Fixture.archetype
      error = $_.Exception.Message
      failed_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $Summary.failed += $Failure
    $Failure | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $CaptureDir "capture-failure.json") -Encoding UTF8
    Write-Host "Failed: $($Fixture.fixture_id) - $($_.Exception.Message)"
  }
}

$SummaryPath = Join-Path $RunDir "windows-hancom-run-summary.json"
$Summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SummaryPath -Encoding UTF8

if ($Summary.failed.Count -eq 0) {
  & $Python scripts/p341r1_finalize_capture_pack.py --pack $RunDir --zip $CapturedZip
  if ($LASTEXITCODE -ne 0) { throw "P3.41-R1 capture-pack final validation failed." }
}

Write-Host ""
Write-Host "P3.41-R1 AuthorBench A3 Hancom capture complete."
Write-Host "Source commit: $Commit"
Write-Host "Frozen A3 authority: $($Manifest.benchmark_authority.frozen_commit) / workflow $($Manifest.benchmark_authority.workflow_run)"
Write-Host "Succeeded: $($Summary.succeeded.Count)"
Write-Host "Failed: $($Summary.failed.Count)"
Write-Host "Summary: $SummaryPath"

if ($Summary.failed.Count -eq 0) {
  Write-Host "Upload this ZIP:"
  Write-Host $CapturedZip
  exit 0
}

Write-Host "No final ZIP was issued because one or more fixtures failed. Evidence remains isolated in:"
Write-Host $RunDir
exit 2
