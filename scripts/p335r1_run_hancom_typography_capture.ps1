param([switch]$RebuildVenv, 
  [string]$OutDir="artifacts/p335r1-native-typography-pack",
  [string]$HancomExe=""
)
$ErrorActionPreference="Stop"
try { chcp 65001 > $null } catch {}
$Utf8NoBom=New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding=$Utf8NoBom
[Console]::OutputEncoding=$Utf8NoBom
$OutputEncoding=$Utf8NoBom
$RepoRoot=(Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Find-HancomExe([string]$Explicit){
  if($Explicit){ if(-not(Test-Path $Explicit)){throw "Hwp.exe not found: $Explicit"}; return (Resolve-Path $Explicit).Path }
  $roots=@((Join-Path $env:ProgramFiles "Hnc"),(Join-Path $env:ProgramFiles "Hancom"))|Where-Object{Test-Path $_}
  $x=[Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  if($x -and (Test-Path (Join-Path $x "Hnc"))){$roots+=(Join-Path $x "Hnc")}
  foreach($r in $roots){$hit=Get-ChildItem $r -Filter Hwp.exe -File -Recurse -ErrorAction SilentlyContinue|Select-Object -First 1;if($hit){return $hit.FullName}}
  throw "Hwp.exe not found."
}
. (Join-Path $PSScriptRoot "common/EnvBootstrap.ps1")
$VP = Initialize-HwpxEnvironment -RepoRoot $RepoRoot -RebuildVenv:$RebuildVenv

$ResolvedOut=if([IO.Path]::IsPathRooted($OutDir)){$OutDir}else{Join-Path $RepoRoot $OutDir}
& $VP scripts/p335r1_materialize_native_typography_pack.py --out $ResolvedOut
if($LASTEXITCODE-ne 0){throw "P3.35-R1 materialization failed"}
$HancomExe=Find-HancomExe $HancomExe
$M=([IO.File]::ReadAllText((Join-Path $ResolvedOut "capture-manifest.json"),[Text.Encoding]::UTF8)|ConvertFrom-Json)

Write-Host ""
Write-Host "P3.35-R1 native typography capture"
Write-Host "각 파일은 본문 한 줄뿐입니다. Ctrl+A 후 지정 서식만 적용하세요."
Write-Host ""

foreach($c in $M.cases){
  $Target=Join-Path (Join-Path $ResolvedOut $c.id) "target.hwpx"
  Write-Host ""; Write-Host "=== $($c.id) ==="
  if($c.kind -eq "spacing"){
    Write-Host "Ctrl+A → [글자 모양]에서 자간을 정확히 $($c.value)% 로 설정 → 확인"
  } elseif($c.kind -eq "font"){
    Write-Host "Ctrl+A → 글꼴을 정확히 '$($c.value)' 로 설정 → 확인"
  } else {
    Write-Host "Ctrl+A → 글자 크기를 정확히 $($c.value) pt 로 설정 → 확인"
  }
  Write-Host "그 외 설정은 건드리지 말고 Ctrl+S → 창 닫기"
  Start-Process -FilePath $HancomExe -ArgumentList ('"'+$Target+'"')|Out-Null
  Read-Host "완료했으면 Enter"
}

& $VP scripts/p335r1_analyze_native_typography.py --pack $ResolvedOut
$Exit=$LASTEXITCODE
$Zip="$ResolvedOut-captured.zip"
if(Test-Path $Zip){Remove-Item $Zip -Force}
Compress-Archive -Path (Join-Path $ResolvedOut "*") -DestinationPath $Zip -CompressionLevel Optimal
Write-Host ""
Write-Host "Analyzer exit: $Exit"
Write-Host "Upload: $Zip"
Write-Host "FAIL이어도 ZIP은 그대로 올려주세요. native encoding 자체가 증거입니다."
