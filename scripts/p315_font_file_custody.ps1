param(
  [Parameter(Mandatory=$true)][string]$OutFile
)

$ErrorActionPreference = "Stop"

function Resolve-FontPath {
  param([string]$Value)
  if (-not $Value) { return $null }
  $expanded = [Environment]::ExpandEnvironmentVariables($Value)
  if ([IO.Path]::IsPathRooted($expanded) -and (Test-Path $expanded)) {
    return (Resolve-Path $expanded).Path
  }
  $candidate = Join-Path $env:WINDIR "Fonts\$expanded"
  if (Test-Path $candidate) {
    return (Resolve-Path $candidate).Path
  }
  return $null
}

$entries = @()
$registryRoots = @(
  "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
  "HKCU:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
)

foreach ($root in $registryRoots) {
  if (-not (Test-Path $root)) { continue }
  $props = Get-ItemProperty -Path $root
  foreach ($prop in $props.PSObject.Properties) {
    if ($prop.Name -like "PS*") { continue }
    $resolved = Resolve-FontPath ([string]$prop.Value)
    if (-not $resolved) { continue }
    try {
      $file = Get-Item $resolved
      $hash = (Get-FileHash -Algorithm SHA256 -Path $resolved).Hash.ToLowerInvariant()
      $entries += @{
        registry_name = [string]$prop.Name
        path = $resolved
        sha256 = $hash
        bytes = [int64]$file.Length
      }
    } catch {}
  }
}

$entries = @(
  $entries |
    Sort-Object registry_name, path, sha256 -Unique
)

if ($entries.Count -eq 0) {
  throw "No Windows font files could be resolved and hashed."
}

$canonical = $entries | ConvertTo-Json -Depth 5 -Compress
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
  $bytes = [Text.Encoding]::UTF8.GetBytes($canonical)
  $digest = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
} finally {
  $sha.Dispose()
}

$receipt = @{
  schema = "chatgpt-web-hwpx-mcp/font-file-custody/p3.15/v1"
  captured_at = (Get-Date).ToUniversalTime().ToString("o")
  machine_id = $env:COMPUTERNAME
  os_name = (Get-CimInstance Win32_OperatingSystem).Caption
  os_version = [Environment]::OSVersion.VersionString
  locale = (Get-Culture).Name
  files = $entries
  file_count = $entries.Count
  font_file_custody_sha256 = $digest
  authority = "WINDOWS_FONT_FILE_CRYPTOGRAPHIC_CUSTODY"
}

$parent = Split-Path -Parent $OutFile
if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
$receipt | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $OutFile
Write-Output $OutFile
