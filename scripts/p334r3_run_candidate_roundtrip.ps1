param([switch]$RebuildVenv, [string]$OutDir="artifacts/p334r3-candidate-roundtrip-pack",[string]$HancomExe="")
$ErrorActionPreference="Stop";try{chcp 65001>$null}catch{}
$Utf8NoBom=New-Object System.Text.UTF8Encoding($false);[Console]::InputEncoding=$Utf8NoBom;[Console]::OutputEncoding=$Utf8NoBom;$OutputEncoding=$Utf8NoBom
$RepoRoot=(Resolve-Path (Join-Path $PSScriptRoot "..")).Path;Set-Location $RepoRoot
function Find-HancomExe([string]$Explicit){if($Explicit){return(Resolve-Path $Explicit).Path};$roots=@((Join-Path $env:ProgramFiles "Hnc"),(Join-Path $env:ProgramFiles "Hancom"))|Where-Object{Test-Path $_};$x=[Environment]::GetEnvironmentVariable("ProgramFiles(x86)");if($x -and(Test-Path(Join-Path $x "Hnc"))){$roots+=(Join-Path $x "Hnc")};foreach($r in $roots){$hit=Get-ChildItem $r -Filter Hwp.exe -File -Recurse -ErrorAction SilentlyContinue|Select-Object -First 1;if($hit){return $hit.FullName}};throw"Hwp.exe not found."}
. (Join-Path $PSScriptRoot "common/EnvBootstrap.ps1")
$VP = Initialize-HwpxEnvironment -RepoRoot $RepoRoot -RebuildVenv:$RebuildVenv

$ResolvedOut=if([IO.Path]::IsPathRooted($OutDir)){$OutDir}else{Join-Path $RepoRoot $OutDir}
&$VP scripts/p334r3_materialize_candidate_roundtrip_pack.py --out $ResolvedOut;if($LASTEXITCODE-ne 0){throw"R3 candidate materialization failed"}
$HancomExe=Find-HancomExe $HancomExe;$M=([IO.File]::ReadAllText((Join-Path $ResolvedOut "roundtrip-manifest.json"),[Text.Encoding]::UTF8)|ConvertFrom-Json)
Write-Host "P3.34-R3 implementation-generated group/ungroup round-trip";Write-Host "이번에는 그룹 조작을 하지 않습니다. 열기 → Ctrl+S → 닫기만 하세요."
foreach($c in $M.cases){$D=Join-Path $ResolvedOut $c.id;$B=Join-Path $D "candidate-before-hancom.hwpx";$A=Join-Path $D "candidate-after-hancom.hwpx";Copy-Item -Force $B $A;Write-Host "";Write-Host "=== $($c.id) ===";Start-Process -FilePath $HancomExe -ArgumentList ('"'+$A+'"')|Out-Null;Read-Host "아무것도 수정하지 않고 저장+닫기 완료 후 Enter"}
&$VP scripts/p334r3_analyze_candidate_roundtrip.py --pack $ResolvedOut;$Exit=$LASTEXITCODE
$Zip="$ResolvedOut-captured.zip";if(Test-Path $Zip){Remove-Item $Zip -Force};Compress-Archive -Path(Join-Path $ResolvedOut "*") -DestinationPath $Zip -CompressionLevel Optimal
Write-Host "Analyzer exit: $Exit";Write-Host "Upload: $Zip";Write-Host "FAIL이어도 ZIP은 그대로 올려주세요."
