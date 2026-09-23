param(
  [string]$Source = "artifacts/p334r2-tracked-resolution-pack/protection-enable/target.hwpx",
  [string]$OutDir = "artifacts/p334r2-protected-resolution-pack",
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

$SourcePath = if ([IO.Path]::IsPathRooted($Source)) { $Source } else { Join-Path $RepoRoot $Source }
$ResolvedOut = if ([IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $RepoRoot $OutDir }

& $VenvPython scripts/p334r2_materialize_protected_resolution_pack.py --source $SourcePath --out $ResolvedOut
if ($LASTEXITCODE -ne 0) { throw "P3.34-R2 protected materialization failed." }

$HancomExe = Find-HancomExe $HancomExe
$Manifest = ([IO.File]::ReadAllText((Join-Path $ResolvedOut "capture-manifest.json"), [Text.Encoding]::UTF8) | ConvertFrom-Json)

Write-Host ""
Write-Host "P3.34-R2 protected-resolution boundary capture"
Write-Host "암호는 P334R2! 입니다."
Write-Host ""

foreach ($case in $Manifest.cases) {
  $Target = Join-Path (Join-Path $ResolvedOut $case.id) "target.hwpx"
  Write-Host ""
  Write-Host "=== $($case.id) ==="

  if ($case.id -eq "protected-cancel-accept") {
    Write-Host "1) [검토]에서 변경 내용을 모두 수락하려고 시도하세요."
    Write-Host "2) 암호 입력 창이 뜨면 암호를 입력하지 말고 취소하세요."
    Write-Host "3) Ctrl+S로 저장하고 창을 닫으세요."
  } elseif ($case.id -eq "protected-correct-accept") {
    Write-Host "1) 변경 내용을 모두 수락하세요."
    Write-Host "2) 암호를 요구하면 P334R2! 를 입력하세요."
    Write-Host "3) Ctrl+S로 저장하고 창을 닫으세요."
  } else {
    Write-Host "1) 변경 내용을 모두 거부하세요."
    Write-Host "2) 암호를 요구하면 P334R2! 를 입력하세요."
    Write-Host "3) Ctrl+S로 저장하고 창을 닫으세요."
  }

  Start-Process -FilePath $HancomExe -ArgumentList ('"' + $Target + '"') | Out-Null
  Read-Host "지시 작업 + 저장 + 창 닫기를 완료했으면 Enter"
}

& $VenvPython scripts/p334r2_analyze_protected_resolution.py --pack $ResolvedOut
$AnalyzerExit = $LASTEXITCODE

$ZipPath = "$ResolvedOut-captured.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $ResolvedOut "*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.34-R2 protected-resolution capture complete."
Write-Host "Analyzer exit: $AnalyzerExit"
Write-Host "Upload this ZIP: $ZipPath"
Write-Host "FAIL이어도 ZIP은 그대로 올려주세요."
