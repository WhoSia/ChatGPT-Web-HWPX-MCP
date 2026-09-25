function Get-HwpxEnvironmentPlan {
    param([Parameter(Mandatory=$true)][string]$RepoRoot)
    $root = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\','/')
    $chosen = $env:HWPX_MCP_VENV
    if (-not $chosen) { $chosen = Join-Path $env:LOCALAPPDATA 'ChatGPT-Web-HWPX-MCP\venv\py312' }
    if (-not [IO.Path]::IsPathRooted($chosen)) { throw 'HWPX_MCP_VENV must be absolute and outside the clone.' }
    $chosen = [IO.Path]::GetFullPath($chosen).TrimEnd('\','/')
    if ($chosen -eq $root -or $chosen.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or $root.StartsWith($chosen + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Shared environment must be outside the clone, and must not contain it.'
    }
    $inputs = @('requirements.txt','requirements-capture.txt','requirements-dev.txt')
    $fingerprint = ($inputs | ForEach-Object {
        $p = Join-Path $root $_
        if (-not (Test-Path -LiteralPath $p)) { throw "Missing dependency input: $_" }
        $_ + ':' + (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash
    }) -join ';'
    [pscustomobject]@{Root=$chosen; Python=(Join-Path $chosen 'Scripts\python.exe'); Fingerprint=$fingerprint; Inputs=$inputs; RepoRoot=$root}
}

function Get-HwpxPythonVersion {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Executable,
        [string[]]$PrefixArguments=@()
    )
    $argv = @($PrefixArguments) + @('--version')
    try {
        $lines = @(& $Executable @argv 2>&1)
        $exitCode = $LASTEXITCODE
    } catch {
        return $null
    }
    if ($exitCode -ne 0) { return $null }
    $text = ($lines | ForEach-Object { "$_" }) -join "`n"
    $match = [regex]::Match($text, '(?im)^\s*Python\s+(\d+)\.(\d+)(?:\.\d+)?(?:\s.*)?$')
    if (-not $match.Success) { return $null }
    return "$($match.Groups[1].Value).$($match.Groups[2].Value)"
}

function Resolve-HwpxBasePythonCommand {
    [CmdletBinding()]
    param([string]$Override=$env:HWPX_MCP_PYTHON)

    if ($Override) {
        $version = Get-HwpxPythonVersion -Executable $Override
        if ($version -ne '3.12') {
            throw 'HWPX_MCP_PYTHON does not resolve to Python 3.12. Point it to a Python 3.12 executable.'
        }
        return [pscustomobject]@{Executable=$Override; PrefixArguments=@(); Version=$version; Label='HWPX_MCP_PYTHON'}
    }

    $candidates = @()
    $seen = @{}
    foreach ($launcher in @(Get-Command py -CommandType Application -All -ErrorAction SilentlyContinue)) {
        foreach ($source in @($launcher.Source)) {
            if (-not $source) { continue }
            $key = "py|$source"
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $candidates += [pscustomobject]@{Executable=[string]$source; PrefixArguments=@('-3.12'); Label="py -3.12 ($source)"}
            }
        }
    }
    foreach ($name in @('python3.12','python')) {
        foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            foreach ($source in @($command.Source)) {
                if (-not $source) { continue }
                $key = "$name|$source"
                if (-not $seen.ContainsKey($key)) {
                    $seen[$key] = $true
                    $candidates += [pscustomobject]@{Executable=[string]$source; PrefixArguments=@(); Label="$name ($source)"}
                }
            }
        }
    }

    foreach ($candidate in $candidates) {
        $executable = [string]$candidate.Executable
        $prefixArguments = [string[]]@($candidate.PrefixArguments)
        $version = Get-HwpxPythonVersion -Executable $executable -PrefixArguments $prefixArguments
        if ($version -eq '3.12') {
            return [pscustomobject]@{
                Executable=$executable
                PrefixArguments=$prefixArguments
                Version=$version
                Label=$candidate.Label
            }
        }
    }

    throw 'Python 3.12 was not found. Tried py -3.12, python3.12, and python. Install Python 3.12 or set HWPX_MCP_PYTHON to its executable.'
}

function Initialize-HwpxEnvironment {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$RepoRoot, [switch]$RebuildVenv, [string]$BasePython=$env:HWPX_MCP_PYTHON)
    $plan = Get-HwpxEnvironmentPlan -RepoRoot $RepoRoot
    $receiptPath = Join-Path $plan.Root 'hwpx-environment.json'
    # Lock outside the venv so an explicit rebuild remains serialized.
    $parent = Split-Path $plan.Root -Parent
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $lock = $null
    try { $lock = [IO.File]::Open($plan.Root + '.lock', 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { throw 'Shared environment is busy. Wait for the other capture/bootstrap to finish.' }
    try {
        if ($RebuildVenv -and (Test-Path -LiteralPath $plan.Root)) {
            # Never recursively remove an unowned directory or a junction.
            $resolved = (Resolve-Path -LiteralPath $plan.Root).Path.TrimEnd('\','/')
            if ($resolved -ne $plan.Root -or -not (Test-Path -LiteralPath $receiptPath) -or -not (Test-Path -LiteralPath (Join-Path $resolved 'pyvenv.cfg'))) { throw 'Refusing rebuild: target is not a registered HWPX environment.' }
            $old = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
            if ($old.schema -ne 'hwpx-shared-environment/v1' -or $old.root -ne $resolved) { throw 'Refusing rebuild: environment receipt does not match target.' }
            $links = @(Get-Item -LiteralPath $resolved) + @(Get-ChildItem -LiteralPath $resolved -Recurse -Force)
            if ($links | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'Refusing rebuild through a junction or symbolic link.' }
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
        if (-not (Test-Path -LiteralPath $plan.Root)) {
            $base = Resolve-HwpxBasePythonCommand -Override $BasePython
            $baseExe = $base.Executable
            $baseArgs = @($base.PrefixArguments) + @('-m','venv',$plan.Root)
            & $baseExe @baseArgs
            if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed. Inspect the target; it will not be silently recreated.' }
        }
        if (-not (Test-Path -LiteralPath $plan.Python) -or -not (Test-Path -LiteralPath (Join-Path $plan.Root 'pyvenv.cfg'))) { throw 'Shared environment is incomplete. Repair it or explicitly rebuild a registered environment.' }
        $version = Get-HwpxPythonVersion -Executable $plan.Python
        if ($version -ne '3.12') { throw 'Shared Python ABI mismatch. Select a Python 3.12 environment; no automatic recreation was performed.' }
        $receipt = $null
        if (Test-Path -LiteralPath $receiptPath) { $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json }
        if ($receipt -and ($receipt.schema -ne 'hwpx-shared-environment/v1' -or $receipt.root -ne $plan.Root)) { throw 'Environment receipt mismatch. Inspect the configured environment before reuse.' }
        if (-not $receipt -or $receipt.dependency_fingerprint -ne $plan.Fingerprint) {
            $pipArgs = @('-m','pip','install','--disable-pip-version-check')
            foreach ($input in $plan.Inputs) { $pipArgs += @('-r',(Join-Path $plan.RepoRoot $input)) }
            & $plan.Python @pipArgs | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Dependency sync failed; fingerprint was not advanced. Retry bootstrap after correcting the error.' }
            & $plan.Python -m pip check | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed; fingerprint was not advanced.' }
            $receipt = @{schema='hwpx-shared-environment/v1';root=$plan.Root;python=$plan.Python;python_version=$version;dependency_fingerprint=$plan.Fingerprint;last_successful_sync=[DateTime]::UtcNow.ToString('o')}
            $receipt | ConvertTo-Json | Set-Content -LiteralPath ($receiptPath + '.tmp') -Encoding UTF8
            Move-Item -LiteralPath ($receiptPath + '.tmp') -Destination $receiptPath -Force
        }
        return $plan.Python
    } finally { if ($lock) { $lock.Dispose() } }
}
