param(
  [string]$HancomExe = "",
  [string]$OutDir = "artifacts/p313r1-hancom-capture-pack",
  [int]$Dpi = 144,
  [switch]$ReuseExistingPack
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Find-HancomExe {
  param([string]$Explicit)
  if ($Explicit) {
    if (-not (Test-Path $Explicit)) { throw "Hancom executable not found: $Explicit" }
    return (Resolve-Path $Explicit).Path
  }
  $roots = @(
    (Join-Path $env:ProgramFiles "Hnc"),
    (Join-Path ${env:ProgramFiles(x86)} "Hnc"),
    (Join-Path $env:ProgramFiles "Hancom")
  ) | Where-Object { $_ -and (Test-Path $_) }
  foreach ($root in $roots) {
    $hit = Get-ChildItem -Path $root -Filter "Hwp.exe" -File -Recurse -ErrorAction SilentlyContinue |
      Select-Object -First 1
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
    if (Test-Path $path) { Remove-Item -Force $path }
  }

  $before = @{}
  Get-Process -Name Hwp -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.Id] = $true }

  $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $helper, "-InputPath", $InputPath, "-OutputPath", $OutputPath)
  $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $args -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

  if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
    try { $proc.Kill() } catch {}
    Start-Sleep -Milliseconds 500
    Get-Process -Name Hwp -ErrorAction SilentlyContinue | ForEach-Object {
      if (-not $before.ContainsKey($_.Id)) {
        try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
      }
    }
    throw "Hancom export timed out after $TimeoutSeconds s for $InputPath"
  }

  # Flush redirected stdout/stderr and refresh process state before reading ExitCode.
  try { $proc.WaitForExit() } catch {}
  try { $proc.Refresh() } catch {}

  $exitCode = $null
  try { $exitCode = [int]$proc.ExitCode } catch {}

  $outputValid = $false
  if (Test-Path $OutputPath) {
    try {
      $outputValid = ((Get-Item $OutputPath).Length -gt 0)
    } catch {}
  }

  if (-not $outputValid -or ($null -ne $exitCode -and $exitCode -ne 0)) {
    $detailParts = @()
    if (Test-Path $stderr) {
      $stderrText = Get-Content $stderr -Raw -ErrorAction SilentlyContinue
      if ($stderrText) { $detailParts += $stderrText.Trim() }
    }
    if (Test-Path $stdout) {
      $stdoutText = Get-Content $stdout -Raw -ErrorAction SilentlyContinue
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
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [int]$MaxAttempts = 3
  )

  $lastError = $null
  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    try {
      if ($attempt -gt 1) {
        Write-Host "RETRY Hancom export $attempt/$MaxAttempts: $InputPath"
        Start-Sleep -Seconds 2
      }
      Export-HancomPdf -InputPath $InputPath -OutputPath $OutputPath
      return
    }
    catch {
      $lastError = $_
      if ($attempt -ge $MaxAttempts) { throw }
      Write-Host "Transient Hancom export failure: $($_.Exception.Message)"
    }
  }
  if ($lastError) { throw $lastError }
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { throw "Python 3.12+ is required." }

$Venv = Join-Path $RepoRoot ".venv-p313r1"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  & $Python.Source -m venv $Venv
}
& $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-capture.txt

if ([IO.Path]::IsPathRooted($OutDir)) {
  $ResolvedOut = $OutDir
} else {
  $ResolvedOut = Join-Path $RepoRoot $OutDir
}
if ($ReuseExistingPack) {
  $manifest = Join-Path $ResolvedOut "capture-ready-manifest.json"
  if (-not (Test-Path $manifest)) {
    throw "ReuseExistingPack requested but capture-ready-manifest.json is missing: $manifest"
  }
  Write-Host "REUSE existing frozen fixture pack: $ResolvedOut"
} else {
  & $VenvPython scripts/p313r1_materialize_pack.py --out $ResolvedOut
  if ($LASTEXITCODE -ne 0) { throw "P3.13-R1 fixture materialization failed." }
}

$HancomExe = Find-HancomExe $HancomExe
$HancomInfo = Get-Item $HancomExe
$HancomVersion = $HancomInfo.VersionInfo.ProductVersion
if (-not $HancomVersion) { $HancomVersion = $HancomInfo.VersionInfo.FileVersion }
$HancomHash = (Get-FileHash -Algorithm SHA256 -Path $HancomExe).Hash.ToLowerInvariant()
$HarnessHash = (Get-FileHash -Algorithm SHA256 -Path $PSCommandPath).Hash.ToLowerInvariant()

$Summary = @{
  schema = "chatgpt-web-hwpx-mcp/pre-hancom-run/p3.13-r1/v1"
  hancom_executable = $HancomExe
  hancom_version = $HancomVersion
  hancom_executable_sha256 = $HancomHash
  dpi = $Dpi
  succeeded = @()
  skipped = @()
  failed = @()
}

$FixtureDirs = Get-ChildItem -Path $ResolvedOut -Directory -Recurse |
  Where-Object {
    (Test-Path (Join-Path $_.FullName "source.hwpx")) -and
    (Test-Path (Join-Path $_.FullName "target.hwpx"))
  } |
  Sort-Object FullName

foreach ($dir in $FixtureDirs) {
  $fixtureId = $dir.Name
  $capture = Join-Path $dir.FullName "capture"
  New-Item -ItemType Directory -Force -Path $capture | Out-Null
  $source = Join-Path $dir.FullName "source.hwpx"
  $target = Join-Path $dir.FullName "target.hwpx"
  $sourcePdf = Join-Path $capture "source.pdf"
  $targetPdf = Join-Path $capture "target.pdf"
  $receiptPath = Join-Path $capture "render-receipt.json"

  if ((Test-Path $receiptPath) -and (Test-Path $sourcePdf) -and (Test-Path $targetPdf)) {
    try {
      $existing = Get-Content $receiptPath -Raw | ConvertFrom-Json
      $sourceHashNow = (Get-FileHash -Algorithm SHA256 -Path $source).Hash.ToLowerInvariant()
      $targetHashNow = (Get-FileHash -Algorithm SHA256 -Path $target).Hash.ToLowerInvariant()
      if (($existing.source_sha256 -eq $sourceHashNow) -and ($existing.target_sha256 -eq $targetHashNow)) {
        Write-Host "SKIP completed fixture: $fixtureId"
        $Summary.skipped += @{ fixture_id = $fixtureId; directory = $dir.FullName; reason = "existing receipt matches source/target hashes" }
        continue
      }
    } catch {}
  }

  Write-Host "CAPTURE fixture: $fixtureId"

  try {
    Export-HancomPdfWithRetry -InputPath $source -OutputPath $sourcePdf
    Export-HancomPdfWithRetry -InputPath $target -OutputPath $targetPdf

    & $VenvPython scripts/p313r1_pdf_capture.py `
      --fixture-id $fixtureId `
      --source-hwpx $source `
      --target-hwpx $target `
      --source-pdf $sourcePdf `
      --target-pdf $targetPdf `
      --out-dir $capture `
      --hancom-version $HancomVersion `
      --hancom-executable-sha256 $HancomHash `
      --dpi $Dpi
    if ($LASTEXITCODE -ne 0) { throw "PDF capture extraction failed." }

    $isCalibration = $dir.FullName -like "*\calibration\*"
    if (-not $isCalibration) {
      & (Join-Path $PSScriptRoot "p313_windows_capture.ps1") `
        -FixtureId $fixtureId `
        -SourceDocument $source `
        -TargetDocument $target `
        -OutDir $capture `
        -HancomExe $HancomExe `
        -HancomVersion $HancomVersion `
        -HarnessSha256 $HarnessHash
      if ($LASTEXITCODE -ne 0) { throw "Custody sealing failed." }
    }

    $Summary.succeeded += @{
      fixture_id = $fixtureId
      directory = $dir.FullName
      calibration = $isCalibration
    }
  }
  catch {
    $Failure = @{
      fixture_id = $fixtureId
      directory = $dir.FullName
      error = $_.Exception.Message
    }
    $Summary.failed += $Failure
    $FailurePath = Join-Path $capture "capture-failure.json"
    $Failure | ConvertTo-Json -Depth 5 |
      Set-Content -Encoding UTF8 $FailurePath
    Write-Host "FAILED fixture: $fixtureId"
    Write-Host "Reason: $($_.Exception.Message)"
    Write-Host "Failure receipt: $FailurePath"
  }
}

if ($Summary.failed.Count -eq 0 -and ($Summary.succeeded.Count -gt 0 -or $Summary.skipped.Count -gt 0)) {
  & $VenvPython scripts/p313r1_select_boundary.py --pack $ResolvedOut
  $BoundaryExit = $LASTEXITCODE
  $Summary.boundary_ready = ($BoundaryExit -eq 0)
} else {
  $BoundaryExit = 2
  $Summary.boundary_ready = $false
  if ($Summary.failed.Count -gt 0) {
    Write-Host "Boundary selection skipped: incomplete fixture capture ($($Summary.failed.Count) failed)."
  } else {
    Write-Host "Boundary selection skipped: no successful fixture captures."
  }
}

$SummaryPath = Join-Path $ResolvedOut "windows-hancom-run-summary.json"
$Summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $SummaryPath

$CapturedZip = "$ResolvedOut-captured.zip"
if (Test-Path $CapturedZip) { Remove-Item -Force $CapturedZip }
Compress-Archive -Path (Join-Path $ResolvedOut "*") -DestinationPath $CapturedZip -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.13-R1 Hancom capture bootstrap complete."
Write-Host "Summary: $SummaryPath"
Write-Host "Upload this ZIP for P3.14: $CapturedZip"
Write-Host "Succeeded: $($Summary.succeeded.Count)"
Write-Host "Skipped: $($Summary.skipped.Count)"
Write-Host "Failed: $($Summary.failed.Count)"
Write-Host "Boundary ready: $($Summary.boundary_ready)"

if ($Summary.failed.Count -gt 0 -or -not $Summary.boundary_ready) {
  exit 2
}
exit 0
