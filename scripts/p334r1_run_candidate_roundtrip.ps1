param(
  [string]$OutDir = "artifacts/p334r1-candidate-roundtrip-pack",
  [string]$HancomExe = ""
)

$ErrorActionPreference = "Stop"
try { chcp 65001 > $null } catch {}
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

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

& $VenvPython scripts/p334r1_materialize_candidate_roundtrip_pack.py --out $ResolvedOut
if ($LASTEXITCODE -ne 0) { throw "P3.34-R1 candidate materialization failed." }

$HancomExe = Find-HancomExe $HancomExe
$HancomItem = Get-Item $HancomExe
$HancomVersion = $HancomItem.VersionInfo.ProductVersion
if (-not $HancomVersion) { $HancomVersion = $HancomItem.VersionInfo.FileVersion }

$ManifestPath = Join-Path $ResolvedOut "roundtrip-manifest.json"
$ManifestJson = [IO.File]::ReadAllText($ManifestPath, [Text.Encoding]::UTF8)
$Manifest = $ManifestJson | ConvertFrom-Json

$Summary = @{
  schema = "chatgpt-web-hwpx-mcp/p3.34-r1/candidate-roundtrip-windows/v1"
  hancom_executable = $HancomExe
  hancom_version = $HancomVersion
  completed = @()
}

Write-Host ""
Write-Host "P3.34-R1 implementation-generated HWPX round-trip"
Write-Host "이번에는 표 조작을 하지 않습니다."
Write-Host "각 파일을 열고, 아무 내용도 수정하지 말고 Ctrl+S로 저장한 뒤 창을 닫으세요."
Write-Host ""

foreach ($case in $Manifest.cases) {
  $Dir = Join-Path $ResolvedOut $case.id
  $Before = Join-Path $Dir "candidate-before-hancom.hwpx"
  $After = Join-Path $Dir "candidate-after-hancom.hwpx"
  Copy-Item -Force $Before $After

  Write-Host ""
  Write-Host "=== $($case.id) ==="
  Write-Host "열기 → 아무것도 수정하지 않기 → Ctrl+S → 창 닫기"
  Start-Process -FilePath $HancomExe -ArgumentList ('"' + $After + '"') | Out-Null
  Read-Host "저장하고 한컴 창을 닫았으면 Enter"

  if (-not (Test-Path $After)) { throw "Round-trip target disappeared: $After" }
  $Summary.completed += $case.id
}

& $VenvPython scripts/p334r1_analyze_candidate_roundtrip.py --pack $ResolvedOut
if ($LASTEXITCODE -ne 0) { throw "P3.34-R1 candidate round-trip structural analysis failed." }

$SummaryPath = Join-Path $ResolvedOut "windows-hancom-candidate-roundtrip-summary.json"
$Summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $SummaryPath

$ZipPath = "$ResolvedOut-captured.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $ResolvedOut "*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.34-R1 candidate round-trip complete."
Write-Host "Upload this ZIP: $ZipPath"
