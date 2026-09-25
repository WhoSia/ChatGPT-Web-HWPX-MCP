function Find-HwpxHancomExe {
  [CmdletBinding()]
  param([string]$Explicit = "")

  if ($Explicit) {
    if (-not (Test-Path -LiteralPath $Explicit -PathType Leaf)) {
      throw "Hancom executable not found: $Explicit"
    }
    return (Resolve-Path -LiteralPath $Explicit).Path
  }

  $roots = @()
  foreach ($base in @($env:ProgramFiles, $env:ProgramFilesX86)) {
    if ($base) {
      $roots += (Join-Path $base "Hnc")
      $roots += (Join-Path $base "Hancom")
    }
  }
  if ($env:ProgramFiles -and (Test-Path Env:"ProgramFiles(x86)")) {
    $x86 = (Get-Item Env:"ProgramFiles(x86)").Value
    if ($x86) {
      $roots += (Join-Path $x86 "Hnc")
      $roots += (Join-Path $x86 "Hancom")
    }
  }

  foreach ($root in ($roots | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    $hit = Get-ChildItem -LiteralPath $root -Filter "Hwp.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
  }
  throw "Hwp.exe was not auto-detected. Re-run with -HancomExe C:\path\to\Hwp.exe."
}

function Export-HwpxHancomPdf {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$HelperScript,
    [int]$TimeoutSeconds = 90
  )

  if (-not (Test-Path -LiteralPath $HelperScript -PathType Leaf)) {
    throw "Hancom export helper missing: $HelperScript"
  }
  $stdout = "$OutputPath.stdout.log"
  $stderr = "$OutputPath.stderr.log"
  foreach ($path in @($stdout, $stderr)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
  }

  $before = @{}
  Get-Process -Name Hwp -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.Id] = $true }

  $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $HelperScript, "-InputPath", $InputPath, "-OutputPath", $OutputPath)
  $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

  if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
    try { $proc.Kill() } catch {}
    Start-Sleep -Milliseconds 500
    Get-Process -Name Hwp -ErrorAction SilentlyContinue | ForEach-Object {
      if (-not $before.ContainsKey($_.Id)) {
        try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
      }
    }
    throw "Hancom export timed out after $TimeoutSeconds seconds for $InputPath"
  }

  try { $proc.WaitForExit() } catch {}
  try { $proc.Refresh() } catch {}
  $exitCode = $null
  try { $exitCode = [int]$proc.ExitCode } catch {}

  $outputValid = $false
  if (Test-Path -LiteralPath $OutputPath) {
    try { $outputValid = ((Get-Item -LiteralPath $OutputPath).Length -gt 0) } catch {}
  }

  if (-not $outputValid -or ($null -ne $exitCode -and $exitCode -ne 0)) {
    $detailParts = @()
    if (Test-Path -LiteralPath $stderr) {
      $stderrText = Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue
      if ($stderrText) { $detailParts += $stderrText.Trim() }
    }
    if (Test-Path -LiteralPath $stdout) {
      $stdoutText = Get-Content -LiteralPath $stdout -Raw -ErrorAction SilentlyContinue
      if ($stdoutText) { $detailParts += $stdoutText.Trim() }
    }
    $detail = [string]::Join(" | ", $detailParts)
    if (-not $detail) { $detail = "helper exited without diagnostic output" }
    $exitLabel = if ($null -eq $exitCode) { "unavailable" } else { [string]$exitCode }
    throw "Hancom export failed for $InputPath. ExitCode=$exitLabel. OutputValid=$outputValid. $detail"
  }

  if ($null -eq $exitCode) {
    Write-Host "WARN: helper ExitCode unavailable, but non-empty PDF exists; accepting output by artifact evidence."
  }
}

function Export-HwpxHancomPdfWithRetry {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$HelperScript,
    [int]$MaxAttempts = 3
  )

  if ($MaxAttempts -lt 1 -or $MaxAttempts -gt 3) {
    throw "MaxAttempts must be between 1 and 3."
  }
  $timeouts = @(90, 150, 240)
  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    try {
      if ($attempt -gt 1) {
        Write-Host "Retry $attempt/$MaxAttempts: $InputPath"
        Start-Sleep -Seconds 3
      }
      $timeout = $timeouts[[Math]::Min($attempt - 1, $timeouts.Count - 1)]
      Export-HwpxHancomPdf -InputPath $InputPath -OutputPath $OutputPath -HelperScript $HelperScript -TimeoutSeconds $timeout
      return
    } catch {
      if ($attempt -eq $MaxAttempts) { throw }
      Write-Host "Transient Hancom export failure: $($_.Exception.Message)"
      Start-Sleep -Seconds 2
    }
  }
}
