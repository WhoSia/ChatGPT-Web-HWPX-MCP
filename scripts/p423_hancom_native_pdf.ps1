# Native HWPX -> PDF via installed Hancom Hangul COM automation.
# Run on a licensed, interactive Windows desktop with Hwp.exe installed.
# This is NOT a Linux/Render PDF renderer and never claims PDF creation
# when HWPFrame.HwpObject is unavailable.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$ReceiptPath = "",
    [switch]$AllowOverwrite
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$hwp = $null
$stage = 'validate'
$tempPdf = $null
$inputInfo = $null
$sourceHash = $null
$ownedHwp = $false
$beforeHwpPids = @()
$jobHwpPid = $null
$jobHwpStartedAtUtc = $null
$receipt = [ordered]@{
    schema = 'chatgpt-web-hwpx-mcp/p423/native-pdf-export/v1'
    status = 'NOT_STARTED'
    engine = 'HANCOM_HWP_EXE_COM'
    render_verified = $false
    native_visual_acceptance = 'NOT_ADJUDICATED'
    input_sha256 = $null
    output_sha256 = $null
    output_bytes = $null
    output_path = $null
    stage = 'validate'
}
try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'WINDOWS_HANCOM_REQUIRED: Native PDF export requires Windows'
    }
    if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
        throw 'SOURCE_NOT_FOUND: HWPX source file is missing'
    }
    $inputInfo = Get-Item -LiteralPath $InputPath
    if ($inputInfo.Extension.ToLowerInvariant() -ne '.hwpx') {
        throw 'UNSUPPORTED_SOURCE: Native PDF task accepts only HWPX'
    }
    if ($inputInfo.Length -lt 100 -or $inputInfo.Length -gt 100MB) {
        throw 'SOURCE_SIZE_INVALID: HWPX source is outside 100B..100MB bounds'
    }
    $sourceHash = (Get-FileHash -LiteralPath $inputInfo.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt.input_sha256 = $sourceHash
    $fullOutput = [IO.Path]::GetFullPath($OutputPath)
    if ([IO.Path]::GetExtension($fullOutput).ToLowerInvariant() -ne '.pdf') {
        throw 'OUTPUT_EXTENSION_INVALID: use a .pdf output path'
    }
    if ([IO.Path]::GetFullPath($inputInfo.FullName) -eq $fullOutput) {
        throw 'SOURCE_OVERWRITE_FORBIDDEN'
    }
    $outputParent = Split-Path -Parent $fullOutput
    if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
        throw 'OUTPUT_DIRECTORY_MISSING: Create destination directory explicitly'
    }
    if ((Test-Path -LiteralPath $fullOutput -PathType Leaf) -and -not $AllowOverwrite) {
        throw 'OUTPUT_EXISTS: Refusing to overwrite unapproved PDF'
    }
    $receipt.output_path = $fullOutput
    $tempPdf = Join-Path $outputParent ('.p423-' + [guid]::NewGuid().ToString('N') + '.pdf')
    $stage = 'com'
    $hwp = New-Object -ComObject HWPFrame.HwpObject
    try { $hwp.XHwpWindows.Item(0).Visible = $false } catch { }
    # Preserve native security behavior: do not auto-register an untrusted
    # path-check DLL, disable prompts globally, or kill unrelated Hwp.exe PIDs.
    $stage = 'open'
    $opened = $hwp.Open($inputInfo.FullName, 'HWPX', '')
    if ($opened -eq $false) {
        throw 'HANCOM_OPEN_FAILED: Native Hangul refused the source document'
    }
    $stage = 'save-as-pdf'
    $saved = $hwp.SaveAs($tempPdf, 'PDF', '')
    if ($saved -eq $false -or -not (Test-Path -LiteralPath $tempPdf -PathType Leaf)) {
        throw 'HANCOM_PDF_SAVE_FAILED: SaveAs PDF returned false or wrote no file'
    }
    $stage = 'verify-pdf'
    $size = (Get-Item -LiteralPath $tempPdf).Length
    if ($size -lt 64) { throw 'INVALID_PDF_SIZE: PDF is truncated or empty' }
    $stream = [IO.File]::OpenRead($tempPdf)
    try {
        $prefix = [byte[]]::new(5)
        $read = $stream.Read($prefix, 0, 5)
        if ($read -ne 5 -or [Text.Encoding]::ASCII.GetString($prefix) -ne '%PDF-') {
            throw 'INVALID_PDF_HEADER: not a PDF file'
        }
    }
    finally { $stream.Dispose() }
    if ((Get-FileHash -LiteralPath $inputInfo.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceHash) {
        throw 'SOURCE_CHANGED_DURING_RENDER: no output can be committed'
    }
    $stage = 'commit'
    if ($AllowOverwrite -and (Test-Path -LiteralPath $fullOutput -PathType Leaf)) {
        # Rename the prior result to a rollback file before replacing it.
        $backup = $fullOutput + '.rollback-' + [guid]::NewGuid().ToString('N')
        Move-Item -LiteralPath $fullOutput -Destination $backup
        try { Move-Item -LiteralPath $tempPdf -Destination $fullOutput -ErrorAction Stop }
        catch {
            Move-Item -LiteralPath $backup -Destination $fullOutput
            throw
        }
        Remove-Item -LiteralPath $backup -Force
    }
    else { Move-Item -LiteralPath $tempPdf -Destination $fullOutput -ErrorAction Stop }
    $receipt.status = 'PDF_CREATED_UNREVIEWED'
    $receipt.render_verified = $true
    $receipt.output_bytes = (Get-Item -LiteralPath $fullOutput).Length
    $receipt.output_sha256 = (Get-FileHash -LiteralPath $fullOutput -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt.stage = 'complete'
}
catch {
    $receipt.status = 'FAILED'
    $receipt.stage = $stage
    $receipt.error_code = $_.Exception.Message
}
finally {
    if ($null -ne $hwp) {
        try { $hwp.Clear(1) } catch {}
        try { $hwp.Quit() } catch {}
        try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) } catch {}
    }
    if ($tempPdf -and (Test-Path -LiteralPath $tempPdf -PathType Leaf)) {
        Remove-Item -LiteralPath $tempPdf -Force
    }
    $receipt.finished_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    $json = $receipt | ConvertTo-Json -Depth 6
    if ($ReceiptPath) {
        $json | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
    }
    Write-Output $json
}
if ($receipt.status -ne 'PDF_CREATED_UNREVIEWED') { exit 1 }
exit 0
