param([switch]$RebuildVenv, [string]$OutDir="artifacts/p334r3-group-ungroup-pack",[string]$HancomExe="")
$ErrorActionPreference="Stop"
try { chcp 65001 > $null } catch {}
$Utf8NoBom=New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding=$Utf8NoBom; [Console]::OutputEncoding=$Utf8NoBom; $OutputEncoding=$Utf8NoBom
$RepoRoot=(Resolve-Path (Join-Path $PSScriptRoot "..")).Path; Set-Location $RepoRoot
function Find-HancomExe([string]$Explicit){
 if($Explicit){return (Resolve-Path $Explicit).Path}
 $roots=@((Join-Path $env:ProgramFiles "Hnc"),(Join-Path $env:ProgramFiles "Hancom")) | Where-Object {Test-Path $_}
 $x=[Environment]::GetEnvironmentVariable("ProgramFiles(x86)"); if($x -and (Test-Path (Join-Path $x "Hnc"))){$roots+=(Join-Path $x "Hnc")}
 foreach($r in $roots){$hit=Get-ChildItem $r -Filter Hwp.exe -File -Recurse -ErrorAction SilentlyContinue|Select-Object -First 1;if($hit){return $hit.FullName}}
 throw "Hwp.exe not found."
}
. (Join-Path $PSScriptRoot "common/EnvBootstrap.ps1")
$VP = Initialize-HwpxEnvironment -RepoRoot $RepoRoot -RebuildVenv:$RebuildVenv

$ResolvedOut=if([IO.Path]::IsPathRooted($OutDir)){$OutDir}else{Join-Path $RepoRoot $OutDir}
& $VP scripts/p334r3_materialize_group_ungroup_pack.py --out $ResolvedOut
if($LASTEXITCODE -ne 0){throw "R3 materialization failed"}
$HancomExe=Find-HancomExe $HancomExe
$M=([IO.File]::ReadAllText((Join-Path $ResolvedOut "capture-manifest.json"),[Text.Encoding]::UTF8)|ConvertFrom-Json)
Write-Host "P3.34-R3 native group/ungroup capture"
foreach($c in $M.cases){
 $Target=Join-Path (Join-Path $ResolvedOut $c.id) "target.hwpx"
 Write-Host ""; Write-Host "=== $($c.id) ==="
 if($c.action -eq "GROUP_SELECTED"){
  Write-Host "두 도형을 모두 선택한 뒤 [그룹]으로 묶으세요. 위치/크기는 바꾸지 마세요."
 } else {
  Write-Host "그룹 개체를 선택한 뒤 [그룹 해제]만 하세요. 위치/크기는 바꾸지 마세요."
 }
 Start-Process -FilePath $HancomExe -ArgumentList ('"'+$Target+'"')|Out-Null
 Read-Host "작업 후 Ctrl+S → 창 닫기 → Enter"
}
& $VP scripts/p334r3_analyze_group_ungroup.py --pack $ResolvedOut
$Zip="$ResolvedOut-captured.zip"; if(Test-Path $Zip){Remove-Item $Zip -Force}
Compress-Archive -Path (Join-Path $ResolvedOut "*") -DestinationPath $Zip -CompressionLevel Optimal
Write-Host "Upload: $Zip"
