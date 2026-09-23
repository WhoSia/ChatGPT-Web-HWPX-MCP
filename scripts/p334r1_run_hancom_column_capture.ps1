param(
  [string]$OutDir = "artifacts/p334r1-column-insertion-pack",
  [string]$HancomExe = ""
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

  $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  $roots = @(
    (Join-Path $env:ProgramFiles "Hnc"),
    ($(if ($programFilesX86) { Join-Path $programFilesX86 "Hnc" } else { $null })),
    (Join-Path $env:ProgramFiles "Hancom")
  ) | Where-Object { $_ -and (Test-Path $_) }

  foreach ($root in $roots) {
    $hit = Get-ChildItem -Path $root -Filter "Hwp.exe" -File -Recurse -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if ($hit) { return $hit.FullName }
  }
  throw "Hwp.exe was not auto-detected. Re-run with -HancomExe 'C:\path\to\Hwp.exe'."
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { throw "Python 3.12+ is required." }

$Venv = Join-Path $RepoRoot ".venv-p334r1"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  & $Python.Source -m venv $Venv
}
& $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt

if ([IO.Path]::IsPathRooted($OutDir)) { $ResolvedOut = $OutDir }
else { $ResolvedOut = Join-Path $RepoRoot $OutDir }

& $VenvPython scripts/p334r1_materialize_column_insertion_pack.py --out $ResolvedOut
if ($LASTEXITCODE -ne 0) { throw "P3.34-R1 materialization failed." }

$HancomExe = Find-HancomExe $HancomExe
$HancomItem = Get-Item $HancomExe
$HancomVersion = $HancomItem.VersionInfo.ProductVersion
if (-not $HancomVersion) { $HancomVersion = $HancomItem.VersionInfo.FileVersion }
$ManifestPath = Join-Path $ResolvedOut "capture-manifest.json"
$Manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json

$Summary = @{
  schema = "chatgpt-web-hwpx-mcp/p3.34-r1/hancom-manual-capture/v1"
  hancom_executable = $HancomExe
  hancom_version = $HancomVersion
  captured = @()
  skipped = @()
}

Write-Host ""
Write-Host "P3.34-R1 Hancom column-insertion capture"
Write-Host "각 케이스는 target.hwpx 복사본에서 딱 한 번의 표 조작만 수행합니다."
Write-Host "한컴에서 다른 내용은 수정하지 마세요."
Write-Host ""

foreach ($case in $Manifest.cases) {
  $Dir = Join-Path $ResolvedOut $case.id
  $Source = Join-Path $Dir "source.hwpx"
  $Target = Join-Path $Dir "target.hwpx"
  $Receipt = Join-Path $Dir "capture-receipt.json"

  if ((Test-Path $Target) -and (Test-Path $Receipt)) {
    Write-Host "SKIP completed: $($case.id)"
    $Summary.skipped += $case.id
    continue
  }

  Copy-Item -Force $Source $Target

  Write-Host ""
  Write-Host "=== $($case.id) ==="
  Write-Host $case.manual.instruction_ko
  Write-Host "작업 후 Ctrl+S로 저장하고 한컴 창을 닫은 다음 이 PowerShell로 돌아오세요."
  Write-Host ""

  Start-Process -FilePath $HancomExe -ArgumentList ('"' + $Target + '"') | Out-Null
  Read-Host "작업/저장/창 닫기를 완료했으면 Enter"

  if (-not (Test-Path $Target)) { throw "Target disappeared: $Target" }

  $sourceHash = (Get-FileHash -Algorithm SHA256 -Path $Source).Hash.ToLowerInvariant()
  $targetHash = (Get-FileHash -Algorithm SHA256 -Path $Target).Hash.ToLowerInvariant()
  if ($sourceHash -eq $targetHash) {
    throw "No byte change detected for $($case.id). Hancom action may not have been saved."
  }

  $receiptData = @{
    case_id = $case.id
    instruction_ko = $case.manual.instruction_ko
    source_sha256 = $sourceHash
    target_sha256 = $targetHash
    captured_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  $receiptData | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $Receipt
  $Summary.captured += $case.id
}

& $VenvPython scripts/p334r1_analyze_column_capture.py --pack $ResolvedOut
$AnalyzeExit = $LASTEXITCODE
if ($AnalyzeExit -ne 0) { throw "P3.34-R1 analysis incomplete. Exit=$AnalyzeExit" }

$SummaryPath = Join-Path $ResolvedOut "windows-hancom-column-capture-summary.json"
$Summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $SummaryPath

$ZipPath = "$ResolvedOut-captured.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $ResolvedOut "*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.34-R1 Hancom column capture complete."
Write-Host "Summary: $SummaryPath"
Write-Host "Upload this ZIP: $ZipPath"
