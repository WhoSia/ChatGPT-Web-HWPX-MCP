param(
  [string]$HancomExe = "",
  [string]$OutDir = "artifacts/p313r1-hancom-capture-pack",
  [int]$Dpi = 144
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
    [Parameter(Mandatory=$true)][string]$OutputPath
  )
  $hwp = $null
  try {
    $hwp = New-Object -ComObject HWPFrame.HwpObject
    try { $hwp.XHwpWindows.Item(0).Visible = $false } catch {}
    $opened = $hwp.Open((Resolve-Path $InputPath).Path, "", "")
    if ($opened -eq $false) { throw "Hancom Open returned false for $InputPath" }
    $saved = $hwp.SaveAs($OutputPath, "PDF", "")
    if ($saved -eq $false -or -not (Test-Path $OutputPath)) {
      throw "Hancom PDF SaveAs failed for $InputPath"
    }
  }
  finally {
    if ($hwp -ne $null) {
      try { $hwp.Quit() } catch {}
      try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) } catch {}
    }
  }
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { throw "Python 3.12+ is required." }

$Venv = Join-Path $RepoRoot ".venv-p313r1"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  & $Python.Source -m venv $Venv
}
& $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-capture.txt

$ResolvedOut = Join-Path $RepoRoot $OutDir
& $VenvPython scripts/p313r1_materialize_pack.py --out $ResolvedOut
if ($LASTEXITCODE -ne 0) { throw "P3.13-R1 fixture materialization failed." }

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

  try {
    Export-HancomPdf -InputPath $source -OutputPath $sourcePdf
    Export-HancomPdf -InputPath $target -OutputPath $targetPdf

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
    $Failure | ConvertTo-Json -Depth 5 |
      Set-Content -Encoding UTF8 (Join-Path $capture "capture-failure.json")
  }
}

& $VenvPython scripts/p313r1_select_boundary.py --pack $ResolvedOut
$BoundaryExit = $LASTEXITCODE
$Summary.boundary_ready = ($BoundaryExit -eq 0)

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
Write-Host "Failed: $($Summary.failed.Count)"
Write-Host "Boundary ready: $($Summary.boundary_ready)"

if ($Summary.failed.Count -gt 0 -or -not $Summary.boundary_ready) {
  exit 2
}
exit 0
