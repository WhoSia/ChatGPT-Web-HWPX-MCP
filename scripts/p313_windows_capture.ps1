param(
  [Parameter(Mandatory=$true)][string]$FixtureId,
  [Parameter(Mandatory=$true)][string]$SourceDocument,
  [Parameter(Mandatory=$true)][string]$TargetDocument,
  [Parameter(Mandatory=$true)][string]$OutDir,
  [Parameter(Mandatory=$true)][string]$HancomExe,
  [Parameter(Mandatory=$true)][string]$HancomVersion,
  [Parameter(Mandatory=$true)][string]$HarnessSha256,
  [string]$PreviousBundleSha256 = ""
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Sha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

$hancomHash = Sha256 $HancomExe
$machineId = "$env:COMPUTERNAME"
$capturedAt = (Get-Date).ToUniversalTime().ToString("o")

# P3.13 runner contract:
# 1. caller must render BOTH source and target with the named Hancom executable;
# 2. output artifacts must include PDFs/raster pages/line-box JSON/font inventory JSON;
# 3. this script does not automate undocumented Hancom GUI/API behavior.
#    A site-specific adapter should materialize these files before custody sealing.

$required = @{
  "source-document" = $SourceDocument
  "target-document" = $TargetDocument
  "source-raster" = (Join-Path $OutDir "source-page-000.png")
  "target-raster" = (Join-Path $OutDir "target-page-000.png")
  "line-box-capture" = (Join-Path $OutDir "line-boxes.json")
  "font-inventory" = (Join-Path $OutDir "fonts.json")
  "render-receipt" = (Join-Path $OutDir "render-receipt.json")
}

$artifacts = @()
foreach ($role in $required.Keys) {
  $path = $required[$role]
  if (-not (Test-Path $path)) {
    throw "Missing required P3.13 artifact for role $role : $path"
  }
  $item = Get-Item $path
  $artifacts += @{
    path = [IO.Path]::GetFileName($path)
    sha256 = Sha256 $path
    bytes = $item.Length
    role = $role
  }
}

foreach ($pair in @(
  @("source-pdf", (Join-Path $OutDir "source.pdf")),
  @("target-pdf", (Join-Path $OutDir "target.pdf")),
  @("runner-log", (Join-Path $OutDir "runner.log"))
)) {
  if (Test-Path $pair[1]) {
    $item = Get-Item $pair[1]
    $artifacts += @{
      path = [IO.Path]::GetFileName($pair[1])
      sha256 = Sha256 $pair[1]
      bytes = $item.Length
      role = $pair[0]
    }
  }
}

$bundle = @{
  schema = "chatgpt-web-hwpx-mcp/capture-bundle/p3.13/v1"
  fixture_id = $FixtureId
  captured_at = $capturedAt
  previous_bundle_sha256 = $PreviousBundleSha256
  runner = @{
    schema = "chatgpt-web-hwpx-mcp/windows-hancom-runner/p3.13/v1"
    os = (Get-CimInstance Win32_OperatingSystem).Caption
    os_version = [Environment]::OSVersion.VersionString
    machine_id = $machineId
    hancom_version = $HancomVersion
    hancom_executable_sha256 = $hancomHash
    harness_sha256 = $HarnessSha256.ToLowerInvariant()
    capture_user = $env:USERNAME
    locale = (Get-Culture).Name
    display_scale_percent = 100
  }
  artifacts = $artifacts
}

$bundlePath = Join-Path $OutDir "capture-bundle.json"
$bundle | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $bundlePath
Write-Output $bundlePath
