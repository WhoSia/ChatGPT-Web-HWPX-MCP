param([switch]$RebuildVenv, 
  [string]$OutDir = "artifacts/p334r2-candidate-roundtrip-pack",
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

. (Join-Path $PSScriptRoot "common/EnvBootstrap.ps1")
$VenvPython = Initialize-HwpxEnvironment -RepoRoot $RepoRoot -RebuildVenv:$RebuildVenv


$ResolvedOut = if ([IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $RepoRoot $OutDir }
& $VenvPython scripts/p334r2_materialize_candidate_roundtrip_pack.py --out $ResolvedOut
if ($LASTEXITCODE -ne 0) { throw "P3.34-R2 candidate materialization failed." }

$HancomExe = Find-HancomExe $HancomExe
$Manifest = ([IO.File]::ReadAllText((Join-Path $ResolvedOut "roundtrip-manifest.json"), [Text.Encoding]::UTF8) | ConvertFrom-Json)

Write-Host ""
Write-Host "P3.34-R2 implementation-generated resolution round-trip"
Write-Host "이번에는 수락/거부 조작을 하지 않습니다."
Write-Host "각 파일을 열고 아무것도 수정하지 말고 Ctrl+S로 저장한 뒤 창을 닫으세요."
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
}

& $VenvPython scripts/p334r2_analyze_candidate_roundtrip.py --pack $ResolvedOut
$AnalyzerExit = $LASTEXITCODE

$ZipPath = "$ResolvedOut-captured.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $ResolvedOut "*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.34-R2 candidate round-trip complete."
Write-Host "Analyzer exit: $AnalyzerExit"
Write-Host "Upload this ZIP: $ZipPath"
Write-Host "FAIL이어도 ZIP은 그대로 올려주세요."
