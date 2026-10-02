param(
  [string]$FirstPassZip = "",
  [switch]$RebuildVenv,
  [string]$HancomExe = "",
  [int]$Dpi = 144,
  [int]$MaxAttempts = 3
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$ExpectedFirstPassSha256 = "a80b4fc01ed472611601ce34ea75b2aa521e0cb86d770af964e882367f6c9d9c"
$ExpectedFirstPassCommit = "3b6a80bc79040502735d5d04423973ffc9f25ccf"
$ExpectedFrozenManifestSha256 = "fdce51f20795c206838eec2ddb23083bee80de77a89a645b85eb0193cd18820c"

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

$Commit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $Commit -notmatch "^[0-9a-f]{40}$") {
  throw "Unable to resolve exact source commit."
}
$Tracked = & git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $Tracked) {
  throw "Tracked working tree changes prevent exact runner custody. Commit or restore them first."
}

if (-not $FirstPassZip) {
  $FirstPassZip = Join-Path $RepoRoot "artifacts/p344-authorbench-first-pass.zip"
}
if (-not (Test-Path -LiteralPath $FirstPassZip -PathType Leaf)) {
  throw "Frozen P3.44 first-pass artifact is required. Put it at artifacts/p344-authorbench-first-pass.zip or pass -FirstPassZip <path>."
}
$FirstPassZip = (Resolve-Path -LiteralPath $FirstPassZip).Path
$FirstPassHash = (Get-FileHash -LiteralPath $FirstPassZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($FirstPassHash -ne $ExpectedFirstPassSha256) {
  throw "Frozen first-pass artifact hash mismatch: expected $ExpectedFirstPassSha256, got $FirstPassHash"
}

$RunId = "$($Commit.Substring(0,12))-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))"
$PackRoot = Join-Path $RepoRoot "artifacts/p344-authorbench-native-capture-pack"
$RunDir = Join-Path $PackRoot "runs/$RunId"
$CapturedZip = Join-Path $RepoRoot "artifacts/p344-authorbench-native-capture-pack-captured.zip"
$HistoryDir = Join-Path $RepoRoot "artifacts/p344-authorbench-native-capture-history"
New-Item -ItemType Directory -Force -Path $PackRoot | Out-Null

if (Test-Path -LiteralPath $CapturedZip) {
  New-Item -ItemType Directory -Force -Path $HistoryDir | Out-Null
  $oldHash = (Get-FileHash -LiteralPath $CapturedZip -Algorithm SHA256).Hash.ToLowerInvariant()
  $archive = Join-Path $HistoryDir "$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))-$($oldHash.Substring(0,16)).zip"
  Move-Item -LiteralPath $CapturedZip -Destination $archive
  Write-Host "Preserved previous captured ZIP: $archive"
}

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
Expand-Archive -LiteralPath $FirstPassZip -DestinationPath $RunDir -Force

$ManifestPath = Join-Path $RunDir "capture-ready-manifest.json"
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Frozen artifact lacks capture-ready-manifest.json" }
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.source_commit -ne $ExpectedFirstPassCommit) {
  throw "Frozen first-pass source commit mismatch: $($Manifest.source_commit)"
}
if ($Manifest.frozen_manifest_sha256 -ne $ExpectedFrozenManifestSha256) {
  throw "Frozen prospective-manifest hash mismatch: $($Manifest.frozen_manifest_sha256)"
}
if ($Manifest.fixtures.Count -ne 8) {
  throw "P3.44 capture requires exactly eight first-pass fixtures."
}

$Summary = [ordered]@{
  schema = "authorbench/p3.44/windows-native-run-summary/v1"
  phase = "P3.44"
  run_id = $RunId
  runner_commit = $Commit
  first_pass_source_commit = $ExpectedFirstPassCommit
  first_pass_artifact_sha256 = $ExpectedFirstPassSha256
  frozen_manifest_sha256 = $ExpectedFrozenManifestSha256
  hancom_executable = $HancomExe
  hancom_version = $HancomVersion
  hancom_executable_sha256 = $HancomHash
  dpi = $Dpi
  succeeded = @()
  failed = @()
}

$BlindCases = @()
foreach ($Fixture in $Manifest.fixtures) {
  $FixtureId = [string]$Fixture.fixture_id
  $Input = Join-Path $RunDir ([string]$Fixture.path)
  if (-not (Test-Path -LiteralPath $Input -PathType Leaf)) {
    throw "Missing frozen fixture: $FixtureId"
  }
  $ActualHash = (Get-FileHash -LiteralPath $Input -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($ActualHash -ne [string]$Fixture.sha256) {
    throw "Pre-render fixture hash mismatch: $FixtureId"
  }

  $CaptureDir = Join-Path $RunDir "fixtures/$FixtureId/capture"
  New-Item -ItemType Directory -Force -Path $CaptureDir | Out-Null
  $Pdf = Join-Path $CaptureDir "hancom-render.pdf"
  Write-Host ""
  Write-Host "Capture: $FixtureId [$($Fixture.archetype)]"

  try {
    Export-HwpxHancomPdfWithRetry -InputPath $Input -OutputPath $Pdf -HelperScript $ExportHelper -MaxAttempts $MaxAttempts
    & $Python scripts/p344_capture_pdf.py --pack $RunDir --fixture-id $FixtureId --pdf $Pdf --hancom-version $HancomVersion --hancom-sha256 $HancomHash --dpi $Dpi --runner-sha256 $RunnerHash
    if ($LASTEXITCODE -ne 0) { throw "P3.44 native capture extraction failed." }

    $ReceiptPath = Join-Path $CaptureDir "render-receipt.json"
    $Receipt = Get-Content -LiteralPath $ReceiptPath -Raw | ConvertFrom-Json
    $ReceiptHash = (Get-FileHash -LiteralPath $ReceiptPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $Summary.succeeded += @{
      fixture_id = $FixtureId
      source_sha256 = $ActualHash
      page_count = [int]$Receipt.page_count
      diagnostic_verdict = [string]$Receipt.diagnostic.verdict
      render_receipt_sha256 = $ReceiptHash
    }

    $BlindCases += @{
      case_id = $FixtureId
      source_sha256 = $ActualHash
      renderer = @{
        hancom_native = [bool]$Receipt.renderer.hancom_native
        version = [string]$Receipt.renderer.version
        executable_sha256 = [string]$Receipt.renderer.executable_sha256
        dpi = [int]$Receipt.renderer.dpi
      }
      page_count = [int]$Receipt.page_count
      world_contact_valid = [bool]$Receipt.diagnostic.world_contact_valid
      diagnostic_verdict = [string]$Receipt.diagnostic.verdict
      severity_counts = $Receipt.diagnostic.severity_counts
      finding_codes = @($Receipt.diagnostic.finding_codes)
      render_receipt_sha256 = $ReceiptHash
    }
  } catch {
    $Failure = @{
      fixture_id = $FixtureId
      error = $_.Exception.Message
      failed_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $Summary.failed += $Failure
    $Failure | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $CaptureDir "capture-failure.json") -Encoding UTF8
    Write-Host "Failed: $FixtureId - $($_.Exception.Message)"
  }
}

$SummaryPath = Join-Path $RunDir "windows-hancom-run-summary.json"
$Summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
$Blind = [ordered]@{
  schema = "authorbench/p3.44/native-blind-packet/v1"
  phase = "P3.44"
  first_pass_source_commit = $ExpectedFirstPassCommit
  frozen_manifest_sha256 = $ExpectedFrozenManifestSha256
  cases = $BlindCases
  authority = "NATIVE_PACKET_WITH_DOMAIN_SPLIT_AUDIENCE_WITHHELD_FROM_SCORING"
}
$Blind | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $RunDir "authorbench-p344-native-blind.json") -Encoding UTF8

$Complete = ($Summary.failed.Count -eq 0 -and $Summary.succeeded.Count -eq 8)
$Validation = [ordered]@{
  schema = "authorbench/p3.44/native-capture-validation/v1"
  phase = "P3.44"
  complete = $Complete
  expected_fixture_count = 8
  succeeded = $Summary.succeeded.Count
  failed = $Summary.failed.Count
  first_pass_artifact_sha256 = $ExpectedFirstPassSha256
  first_pass_source_commit = $ExpectedFirstPassCommit
  authority = if ($Complete) { "P3.44_NATIVE_HANCOM_WORLD_CONTACT_COMPLETE" } else { "INCOMPLETE_NATIVE_WORLD_CONTACT" }
}
$Validation | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $RunDir "capture-validation.json") -Encoding UTF8

Write-Host ""
Write-Host "P3.44 AuthorBench Hancom capture complete."
Write-Host "Runner commit: $Commit"
Write-Host "Frozen first-pass commit: $ExpectedFirstPassCommit"
Write-Host "Succeeded: $($Summary.succeeded.Count)"
Write-Host "Failed: $($Summary.failed.Count)"

if (-not $Complete) {
  Write-Host "No final ZIP was issued because native world contact is incomplete."
  Write-Host "Evidence remains isolated in: $RunDir"
  exit 2
}

if (Test-Path -LiteralPath $CapturedZip) { Remove-Item -LiteralPath $CapturedZip -Force }
Compress-Archive -Path (Join-Path $RunDir "*") -DestinationPath $CapturedZip -CompressionLevel Optimal -Force
$CapturedHash = (Get-FileHash -LiteralPath $CapturedZip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Captured ZIP SHA256: $CapturedHash"
Write-Host "Upload this ZIP:"
Write-Host $CapturedZip
exit 0
