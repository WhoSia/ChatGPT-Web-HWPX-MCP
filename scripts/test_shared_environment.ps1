param([string]$BasePython=(Get-Command python).Source)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'common/EnvBootstrap.ps1')
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('hwpx env test '+[guid]::NewGuid().ToString('N'))
$originalLocal=$env:LOCALAPPDATA; $originalOverride=$env:HWPX_MCP_VENV
function Assert($condition,$message) { if (-not $condition) { throw $message } }
try {
    $env:LOCALAPPDATA=Join-Path $testRoot 'local'
    $env:HWPX_MCP_VENV=$null
    $repo=Join-Path $testRoot 'clone one';New-Item -ItemType Directory $repo -Force|Out-Null
    foreach($f in @('requirements.txt','requirements-capture.txt','requirements-dev.txt')) { Set-Content (Join-Path $repo $f) '# empty fixture' }
    $default=Get-HwpxEnvironmentPlan $repo
    Assert ($default.Root.StartsWith($env:LOCALAPPDATA)) 'default path is not external'
    $env:HWPX_MCP_VENV=Join-Path $testRoot 'shared python'
    $plan=Get-HwpxEnvironmentPlan $repo
    Assert ($plan.Root -eq $env:HWPX_MCP_VENV) 'override ignored'
    $py=Initialize-HwpxEnvironment -RepoRoot $repo -BasePython $BasePython
    $receipt=Join-Path $plan.Root 'hwpx-environment.json'
    $first=Get-Content $receipt -Raw
    $again=Initialize-HwpxEnvironment -RepoRoot $repo -BasePython $BasePython
    Assert ($again -eq $py -and (Get-Content $receipt -Raw) -eq $first) 'reuse unexpectedly synchronized'
    $clone=Join-Path $testRoot 'reclone two';Copy-Item $repo $clone -Recurse
    Assert ((Initialize-HwpxEnvironment -RepoRoot $clone -BasePython $BasePython) -eq $py) 'reclone did not reuse'
    Assert ((Get-Content $receipt -Raw) -eq $first) 'reclone changed sync receipt'
    Add-Content (Join-Path $clone 'requirements.txt') '# changed fingerprint'
    $null=Initialize-HwpxEnvironment -RepoRoot $clone -BasePython $BasePython
    Assert ((Get-Content $receipt -Raw) -ne $first) 'dependency change not synchronized'
    $marker=Join-Path $plan.Root 'rebuild-test-marker';Set-Content $marker 'marker'
    $null=Initialize-HwpxEnvironment -RepoRoot $clone -BasePython $BasePython -RebuildVenv
    Assert (-not(Test-Path $marker)) 'explicit rebuild did not recreate'
    $env:HWPX_MCP_VENV=Join-Path $repo '.venv'
    $rejected=$false;try { Get-HwpxEnvironmentPlan $repo|Out-Null } catch { $rejected=$true }
    Assert $rejected 'in-clone environment accepted'
    $env:HWPX_MCP_VENV=Join-Path $testRoot 'unowned directory';New-Item -ItemType Directory $env:HWPX_MCP_VENV|Out-Null
    $rejected=$false;try { Initialize-HwpxEnvironment -RepoRoot $repo -RebuildVenv|Out-Null } catch {$rejected=$true}
    Assert $rejected 'unowned recursive rebuild accepted'
    function UnsupportedPython { $global:LASTEXITCODE=0; return '3.11' }
    $env:HWPX_MCP_VENV=Join-Path $testRoot 'unsupported ABI'
    $rejected=$false;try { Initialize-HwpxEnvironment -RepoRoot $repo -BasePython UnsupportedPython|Out-Null } catch {$rejected=$_.Exception.Message -like '*3.12*'}
    Assert $rejected 'unsupported Python ABI accepted'
    Write-Host 'PASS: default, override, spaces, reuse, unchanged fingerprint, changed fingerprint, reclone, rebuild, ABI and unsafe path rejection.'
} finally {
    $env:LOCALAPPDATA=$originalLocal;$env:HWPX_MCP_VENV=$originalOverride
    # Verified fixed test root only; never touch the user environment.
    $resolved=[IO.Path]::GetFullPath($testRoot)
    $temp=[IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if($resolved.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf).StartsWith('hwpx env test ')) {Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue}
}
