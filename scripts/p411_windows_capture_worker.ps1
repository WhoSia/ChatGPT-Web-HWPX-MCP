param(
    [Parameter(Mandatory=$true)][string]$RequestJson,
    [Parameter(Mandatory=$true)][string]$CaptureRunner
)
$ErrorActionPreference = "Stop"

$request = Get-Content -LiteralPath $RequestJson -Raw | ConvertFrom-Json
$before = @(Get-Process Hwp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$started = (Get-Date).ToString("o")

& $CaptureRunner -SourceDir $request.source_dir -OutputDir $request.output_dir

$manifest = Join-Path $request.output_dir "p49-native-capture-manifest.json"
if (-not (Test-Path -LiteralPath $manifest)) { throw "capture manifest missing" }
$m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
$manifestHash = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash

$after = @(Get-Process Hwp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$owned = @($m.rows | ForEach-Object { @($_.owned_hwp_pids) } | ForEach-Object { $_ } | Sort-Object -Unique)
$forced = @($m.rows | ForEach-Object { @($_.forced_cleanup_pids) } | ForEach-Object { $_ } | Sort-Object -Unique)
$receipt = [ordered]@{
    schema = "chatgpt-web-hwpx-mcp/p411/windows-capture-worker/v1"
    phase = "P4.11"
    job_id = $request.job_id
    exact_head = $request.exact_head
    hancom_version_expected = $request.hancom_version_expected
    hancom_version_observed = $null
    parent_pid = $PID
    baseline_hwp_pids = @($before)
    owned_hwp_pids = @($owned)
    forced_cleanup_pids = @($forced)
    source_count = [int]$m.source_count
    pass_count = [int]$m.pass_count
    fail_count = [int]$m.fail_count
    capture_manifest_sha256 = $manifestHash
    started_at = $started
    finished_at = (Get-Date).ToString("o")
    process_snapshot_after = @($after)
    source_receipts = @($m.rows)
    authority = "P4.11_WINDOWS_CAPTURE_WORKER_RECEIPT"
}
$receiptPath = Join-Path $request.output_dir "p411-worker-receipt.json"
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
Write-Host "P411_WORKER_RECEIPT : $receiptPath"
