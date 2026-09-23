param(
  [string]$OutDir = "artifacts/p334r2-tracked-resolution-pack",
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

$Venv = Join-Path $RepoRoot ".venv-p334r2"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { & $Python.Source -m venv $Venv }
& $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt

if ([IO.Path]::IsPathRooted($OutDir)) { $ResolvedOut = $OutDir }
else { $ResolvedOut = Join-Path $RepoRoot $OutDir }

& $VenvPython scripts/p334r2_materialize_tracked_resolution_pack.py --out $ResolvedOut
if ($LASTEXITCODE -ne 0) { throw "P3.34-R2 materialization failed." }

$HancomExe = Find-HancomExe $HancomExe
$HancomItem = Get-Item $HancomExe
$HancomVersion = $HancomItem.VersionInfo.ProductVersion
if (-not $HancomVersion) { $HancomVersion = $HancomItem.VersionInfo.FileVersion }

$ManifestPath = Join-Path $ResolvedOut "capture-manifest.json"
$ManifestJson = [IO.File]::ReadAllText($ManifestPath, [Text.Encoding]::UTF8)
$Manifest = $ManifestJson | ConvertFrom-Json

$Summary = @{
  schema = "chatgpt-web-hwpx-mcp/p3.34-r2/windows-native-resolution/v1"
  hancom_executable = $HancomExe
  hancom_version = $HancomVersion
  completed = @()
}

Write-Host ""
Write-Host "P3.34-R2 tracked-change native capture"
Write-Host "각 파일에는 이 probe가 만든 변경 내용만 있습니다."
Write-Host "지시된 수락/거부/보호 조작 외에는 수정하지 마세요."
Write-Host ""

foreach ($case in $Manifest.cases) {
  $Dir = Join-Path $ResolvedOut $case.id
  $Target = Join-Path $Dir "target.hwpx"

  Write-Host ""
  Write-Host "=== $($case.id) ==="
  if ($case.kind -eq "resolution") {
    if ($case.action -eq "ACCEPT_ALL") {
      Write-Host "한컴 [검토]에서 이 문서의 변경 내용을 모두 수락하세요."
    } else {
      Write-Host "한컴 [검토]에서 이 문서의 변경 내용을 모두 거부하세요."
    }
    Write-Host "그 다음 Ctrl+S로 저장하고 한컴 창을 닫으세요."
  } else {
    Write-Host "한컴 [검토]의 변경 내용 추적 보호(변경 내용 보호) 기능을 켜세요."
    Write-Host "테스트 암호는 정확히: P334R2!"
    Write-Host "보호를 켠 뒤 Ctrl+S로 저장하고 한컴 창을 닫으세요."
    Write-Host "※ 이 파일에서는 변경 내용을 수락/거부하지 마세요."
  }

  Start-Process -FilePath $HancomExe -ArgumentList ('"' + $Target + '"') | Out-Null
  Read-Host "지시 작업 + 저장 + 창 닫기를 완료했으면 Enter"
  $Summary.completed += $case.id
}

& $VenvPython scripts/p334r2_analyze_tracked_resolution.py --pack $ResolvedOut
$AnalyzerExit = $LASTEXITCODE

$SummaryPath = Join-Path $ResolvedOut "windows-hancom-run-summary.json"
$Summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $SummaryPath

$ZipPath = "$ResolvedOut-captured.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $ResolvedOut "*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.34-R2 capture complete."
Write-Host "Analyzer exit: $AnalyzerExit"
Write-Host "Upload this ZIP: $ZipPath"
Write-Host "분석기가 FAIL이어도 ZIP은 그대로 올려주세요. native 의미를 판정하는 증거로 사용합니다."
