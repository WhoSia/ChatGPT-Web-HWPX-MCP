param(
  [switch]$RebuildVenv,
  [string]$HancomExe = "",
  [int]$Dpi = 144,
  [int]$MaxAttempts = 3
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Find-HancomExe([string]$Explicit) {
  if ($Explicit) {
    if (-not (Test-Path -LiteralPath $Explicit -PathType Leaf)) { throw "Hancom executable not found: $Explicit" }
    return (Resolve-Path -LiteralPath $Explicit).Path
  }
  $roots = @((Join-Path $env:ProgramFiles "Hnc"), (Join-Path ${env:ProgramFiles(x86)} "Hnc"), (Join-Path $env:ProgramFiles "Hancom")) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
  foreach ($root in $roots) {
    $hit = Get-ChildItem -LiteralPath $root -Filter "Hwp.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
  }
  throw "Hwp.exe was not auto-detected. Re-run with -HancomExe 'C:\path\to\Hwp.exe'."
}

function Export-HancomPdf {
  param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [int]$TimeoutSeconds = 90
  )

  $helper = Join-Path $PSScriptRoot "p313r1_hancom_export_once.ps1"
  $stdout = "$OutputPath.stdout.log"
  $stderr = "$OutputPath.stderr.log"
  foreach ($path in @($stdout, $stderr)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
  }

  $before = @{}
  Get-Process -Name Hwp -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.Id] = $true }

  $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $helper, "-InputPath", $InputPath, "-OutputPath", $OutputPath)
  $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

  if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
    try { $proc.Kill() } catch {}
    Start-Sleep -Milliseconds 500
    Get-Process -Name Hwp -ErrorAction SilentlyContinue | ForEach-Object {
      if (-not $before.ContainsKey($_.Id)) {
        try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
      }
    }
    throw "Hancom export timed out after $TimeoutSeconds seconds for $InputPath"
  }

  try { $proc.WaitForExit() } catch {}
  try { $proc.Refresh() } catch {}

  $exitCode = $null
  try { $exitCode = [int]$proc.ExitCode } catch {}

  $outputValid = $false
  if (Test-Path -LiteralPath $OutputPath) {
    try { $outputValid = ((Get-Item -LiteralPath $OutputPath).Length -gt 0) } catch {}
  }

  if (-not $outputValid -or ($null -ne $exitCode -and $exitCode -ne 0)) {
    $detailParts = @()
    if (Test-Path -LiteralPath $stderr) {
      $stderrText = Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue
      if ($stderrText) { $detailParts += $stderrText.Trim() }
    }
    if (Test-Path -LiteralPath $stdout) {
      $stdoutText = Get-Content -LiteralPath $stdout -Raw -ErrorAction SilentlyContinue
      if ($stdoutText) { $detailParts += $stdoutText.Trim() }
    }
    $detail = [string]::Join(" | ", $detailParts)
    if (-not $detail) { $detail = "helper exited without diagnostic output" }
    $exitLabel = if ($null -eq $exitCode) { "unavailable" } else { [string]$exitCode }
    throw "Hancom export failed for $InputPath. ExitCode=$exitLabel. OutputValid=$outputValid. $detail"
  }

  if ($null -eq $exitCode) {
    Write-Host "WARN: helper ExitCode unavailable, but non-empty PDF exists; accepting output by artifact evidence."
  }
}

function Export-HancomPdfWithRetry {
  param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath
  )

  $timeouts = @(90, 150, 240)
  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    try {
      if ($attempt -gt 1) {
        Write-Host "Retry ${attempt}/${MaxAttempts}: $InputPath"
        Start-Sleep -Seconds 3
      }
      $timeout = $timeouts[[Math]::Min($attempt - 1, $timeouts.Count - 1)]
      Export-HancomPdf -InputPath $InputPath -OutputPath $OutputPath -TimeoutSeconds $timeout
      return
    } catch {
      if ($attempt -eq $MaxAttempts) { throw }
      Write-Host "Transient Hancom export failure: $($_.Exception.Message)"
      Write-Host "RECOVER: clearing leftover Hwp processes before retry."
      Get-Process -Name Hwp -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
      }
      Start-Sleep -Seconds 2
    }
  }
}

if ($Dpi -le 0) { throw "Dpi must be positive." }
if ($MaxAttempts -lt 1 -or $MaxAttempts -gt 3) { throw "MaxAttempts must be between 1 and 3." }
. (Join-Path $PSScriptRoot "common/EnvBootstrap.ps1")
$Python = Initialize-HwpxEnvironment -RepoRoot $RepoRoot -RebuildVenv:$RebuildVenv
$HancomExe = Find-HancomExe $HancomExe
$HancomItem = Get-Item -LiteralPath $HancomExe
$HancomVersion = $HancomItem.VersionInfo.ProductVersion; if (-not $HancomVersion) { $HancomVersion = $HancomItem.VersionInfo.FileVersion }
$HancomHash = (Get-FileHash -LiteralPath $HancomExe -Algorithm SHA256).Hash.ToLowerInvariant()
$RunnerHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$Commit = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $Commit -notmatch '^[0-9a-f]{40}$') { throw "Unable to resolve exact source commit." }
$Tracked = & git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $Tracked) { throw "Tracked working tree changes prevent exact source custody. Commit or restore them first." }

$RunId = "$($Commit.Substring(0,12))-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))"
$PackRoot = Join-Path $RepoRoot "artifacts/p340r1-authorbench-capture-pack"
$RunDir = Join-Path $PackRoot "runs/$RunId"
$CapturedZip = Join-Path $RepoRoot "artifacts/p340r1-authorbench-capture-pack-captured.zip"
$HistoryDir = Join-Path $RepoRoot "artifacts/p340r1-authorbench-capture-history"
New-Item -ItemType Directory -Force -Path $PackRoot | Out-Null
if (Test-Path -LiteralPath $CapturedZip) {
  New-Item -ItemType Directory -Force -Path $HistoryDir | Out-Null
  $oldHash = (Get-FileHash -LiteralPath $CapturedZip -Algorithm SHA256).Hash.ToLowerInvariant()
  $archive = Join-Path $HistoryDir "$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))-$($oldHash.Substring(0,16)).zip"
  Move-Item -LiteralPath $CapturedZip -Destination $archive
  Write-Host "Preserved previous captured ZIP: $archive"
}

& $Python scripts/p340r1_materialize_capture_pack.py --out $RunDir
if ($LASTEXITCODE -ne 0) { throw "P3.40-R1 fixture materialization failed." }
$ManifestPath = Join-Path $RunDir "capture-ready-manifest.json"
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.source.commit -ne $Commit) { throw "Materialized source commit mismatch." }
$Summary = [ordered]@{schema="authorbench/p340r1-windows-run-summary/v1"; phase="P3.40-R1"; run_id=$RunId; source_commit=$Commit; hancom_executable=$HancomExe; hancom_version=$HancomVersion; hancom_executable_sha256=$HancomHash; dpi=$Dpi; succeeded=@(); failed=@()}

foreach ($Fixture in $Manifest.fixtures) {
  $FixtureDir = Join-Path $RunDir "fixtures/$($Fixture.fixture_id)"; $Input = Join-Path $RunDir $Fixture.path
  $ActualHash = (Get-FileHash -LiteralPath $Input -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($ActualHash -ne $Fixture.sha256) { throw "Pre-render fixture hash mismatch: $($Fixture.fixture_id)" }
  $CaptureDir = Join-Path $FixtureDir "capture"; New-Item -ItemType Directory -Force -Path $CaptureDir | Out-Null
  $Pdf = Join-Path $CaptureDir "hancom-render.pdf"
  Write-Host ""; Write-Host "Capture: $($Fixture.fixture_id)"
  try {
    Export-HancomPdfWithRetry $Input $Pdf
    & $Python scripts/p340r1_capture_pdf.py --pack $RunDir --fixture-id $Fixture.fixture_id --pdf $Pdf --hancom-version $HancomVersion --hancom-sha256 $HancomHash --dpi $Dpi --runner-sha256 $RunnerHash
    if ($LASTEXITCODE -ne 0) { throw "Raster/custody extraction failed." }
    $Summary.succeeded += @{fixture_id=$Fixture.fixture_id; source_sha256=$ActualHash}
  } catch {
    $Failure = @{fixture_id=$Fixture.fixture_id; error=$_.Exception.Message; failed_at_utc=[DateTime]::UtcNow.ToString('o')}
    $Summary.failed += $Failure
    $Failure | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $CaptureDir "capture-failure.json") -Encoding UTF8
    Write-Host "Failed: $($Fixture.fixture_id) — $($_.Exception.Message)"
  }
}

$SummaryPath = Join-Path $RunDir "windows-hancom-run-summary.json"
$Summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
if ($Summary.failed.Count -eq 0) {
  & $Python scripts/p340r1_finalize_capture_pack.py --pack $RunDir --zip $CapturedZip
  if ($LASTEXITCODE -ne 0) { throw "Capture-pack final validation failed." }
}
Write-Host ""; Write-Host "P3.40-R1 AuthorBench Hancom capture complete."
Write-Host "Source commit: $Commit"; Write-Host "Succeeded: $($Summary.succeeded.Count)"; Write-Host "Failed: $($Summary.failed.Count)"; Write-Host "Summary: $SummaryPath"
if ($Summary.failed.Count -eq 0) { Write-Host "Upload this ZIP:"; Write-Host $CapturedZip; exit 0 }
Write-Host "No final ZIP was issued because one or more fixtures failed. Evidence remains isolated in:"; Write-Host $RunDir; exit 2
