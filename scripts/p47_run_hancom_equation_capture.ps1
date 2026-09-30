param(
  [Parameter(Mandatory=$true)][string]$PackDir,
  [string]$OutDir = "",
  [string]$HancomExe = ""
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $RepoRoot "scripts\common\HancomExport.ps1")

$pack = (Resolve-Path -LiteralPath $PackDir).Path
if (-not $OutDir) { $OutDir = Join-Path $pack "hancom-capture" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$exe = Find-HwpxHancomExe -Explicit $HancomExe
$exeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $exe).Hash.ToLowerInvariant()

$helperCandidates = @(
  (Join-Path $RepoRoot "scripts\common\InvokeHancomSaveAsPdf.ps1"),
  (Join-Path $RepoRoot "scripts\p340r1_hancom_saveas_pdf.ps1")
)
$helper = $helperCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $helper) { throw "No Hancom SaveAs PDF helper found." }

$manifestPath = Join-Path $pack "p47-capture-manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$rows = @()
foreach ($candidate in $manifest.candidates) {
  $row = [ordered]@{ candidate_id = $candidate.candidate_id; fixtures = [ordered]@{} }
  foreach ($variant in @("control","candidate")) {
    $srcName = $candidate.fixtures.$variant.filename
    $src = Join-Path $pack $srcName
    $pdf = Join-Path $OutDir ($candidate.candidate_id + "-" + $variant + ".pdf")
    Export-HwpxHancomPdfWithRetry -InputPath $src -OutputPath $pdf -HelperScript $helper
    $row.fixtures[$variant] = [ordered]@{
      hwpx_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash.ToLowerInvariant()
      pdf_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $pdf).Hash.ToLowerInvariant()
      pdf_path = $pdf
      export_succeeded = $true
    }
  }
  $rows += [pscustomobject]$row
}
$receipt = [ordered]@{
  schema = "chatgpt-web-hwpx-mcp/p47/equation-world-contact/v1"
  phase = "P4.7"
  product = "0.33.0-p4.7"
  frontier_sha256 = $manifest.frontier_sha256
  renderer = [ordered]@{
    name = "Hancom Hangul"
    hancom_native = $true
    os = "Windows"
    executable_sha256 = $exeHash
  }
  raw_capture = $rows
  status = "NATIVE_PDFS_CAPTURED_HUMAN_ADJUDICATION_REQUIRED"
}
$receiptPath = Join-Path $OutDir "p47-native-capture-receipt.json"
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
Write-Host "P4.7 Hancom capture complete: $receiptPath"
