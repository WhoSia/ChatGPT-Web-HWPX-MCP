param([Parameter(Mandatory=$true)][string]$JobEnvelopePath)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$signer = Join-Path $PSScriptRoot "p414_sign_receipt.py"
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$python = if ($pythonCommand) { $pythonCommand.Source } else { $null }
if (-not $pythonCommand) {
    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundledPython) { $python = $bundledPython }
}
if (-not $python) { throw "Python 3 with the cryptography package is required for local Ed25519 signing; no supported runtime was found" }
& $python -c "import cryptography" 2>$null
if ($LASTEXITCODE -ne 0) { throw "The selected Python runtime does not provide cryptography for Ed25519 signatures" }
$job = Get-Content -LiteralPath $JobEnvelopePath -Raw | ConvertFrom-Json
$validated = & $python $signer validate-job --job $JobEnvelopePath | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $validated.status -ne "PASS") { throw "P4.14 capture job failed validation: $($validated | ConvertTo-Json -Compress)" }

$sourceRoot = (Resolve-Path -LiteralPath $job.source_root).Path
$outputRoot = [System.IO.Path]::GetFullPath($job.output_target)
$sourcePrefix = $sourceRoot.TrimEnd('\') + '\'
if ($outputRoot.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase) -or $outputRoot.Equals($sourceRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "output target overlaps immutable source root" }
if ((Get-Item -LiteralPath $sourceRoot).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw "job-scoped source root must not be a symlink or reparse point" }
$pathProbe = $outputRoot
while ($pathProbe -and (Test-Path -LiteralPath $pathProbe)) {
    if ((Get-Item -LiteralPath $pathProbe).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw "output path contains a symlink or reparse point; refusing redirected writes" }
    $parentProbe = Split-Path -Parent $pathProbe
    if (-not $parentProbe -or $parentProbe -eq $pathProbe) { break }
    $pathProbe = $parentProbe
}
$jobOutput = Join-Path $outputRoot $job.job_id
$null = New-Item -ItemType Directory -Force -Path $jobOutput
$journal = Join-Path $jobOutput "p414-job-state.json"
$payloadPath = Join-Path $jobOutput "p414-signed-payload.json"
$receiptPath = Join-Path $jobOutput "p414-signed-receipt.json"
$keyRoot = Join-Path $env:LOCALAPPDATA "ChatGPT-Web-HWPX-MCP\P414-CaptureAgent"
$privatePath = Join-Path $keyRoot "agent-ed25519-private.pem"
$publicPath = Join-Path $keyRoot "agent-ed25519-public.b64"
$identityPath = Join-Path $keyRoot "agent-identity.json"
$null = New-Item -ItemType Directory -Force -Path $keyRoot
if (-not (Test-Path -LiteralPath $identityPath)) {
    $created = & $python $signer init-key --private $privatePath --public $publicPath | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "capture signing key initialization failed" }
    $identity = [ordered]@{ agent_id=$created.agent_id; key_id=$created.key_id; public_key_ed25519_b64=$created.public_key_ed25519_b64; created_at=(Get-Date).ToUniversalTime().ToString('o') }
    $identity | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $identityPath -Encoding UTF8
} else { $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json }

if (Test-Path -LiteralPath $receiptPath) {
    Write-Output "P414_CAPTURE_RECEIPT : $receiptPath"
    Write-Output "P414_AGENT_IDENTITY : $identityPath"
    exit 0
}
if (Test-Path -LiteralPath $journal) {
    $old = Get-Content -LiteralPath $journal -Raw | ConvertFrom-Json
    if ($old.status -eq "RUNNING") {
        $now = (Get-Date).ToUniversalTime().ToString("o")
        $recovery = [ordered]@{
            schema="chatgpt-web-hwpx-mcp/p414/distributed-native-capture/v1"; protocol_version="1.0"; product=$job.product
            job_id=$job.job_id; exact_head=$job.exact_head; source_manifest_sha256=$job.source_manifest_sha256
            hancom_version="UNKNOWN"; hancom_build="UNKNOWN"; capture_agent_version="1.0.0"
            issued_at=$job.issued_at; expires_at=$job.expires_at; nonce=$job.nonce
            source_files=@($job.source_manifest.files); outputs=@(); process_custody=@{owned_hwp_pids=@(); terminated_owned_hwp_pids=@(); global_kill_used=$false}
            capture_status="FAILED"; recovery_status="INTERRUPTED"; visual_verdict="PENDING"; visual_observations=@{}
            document_binding=$job.document_binding; captured_at=$now; failure=@{code="INTERRUPTED_JOB_RECOVERY"; prior_state=$old}
        }
        $recovery | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $payloadPath -Encoding UTF8
        $null = & $python $signer sign --payload $payloadPath --private $privatePath --agent-id $identity.agent_id --key-id $identity.key_id --out $receiptPath
        if ($LASTEXITCODE -ne 0) { throw "interrupted-job recovery receipt signing failed" }
        $old.status="RECOVERY_RECEIPT_WRITTEN"; $old.finished_at=$now
        $old | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $journal -Encoding UTF8
        Write-Output "P414_INTERRUPTED_RECOVERY_RECEIPT : $receiptPath"
        Write-Output "P414_AGENT_IDENTITY : $identityPath"
        exit 2
    }
}

[ordered]@{ job_id=$job.job_id; status="RUNNING"; started_at=(Get-Date).ToUniversalTime().ToString("o"); parent_pid=$PID } | ConvertTo-Json | Set-Content -LiteralPath $journal -Encoding UTF8
$windows = Get-CimInstance Win32_OperatingSystem
$hwpExe = @("${env:ProgramFiles(x86)}\HNC\Office 2024\HOffice130\Bin\Hwp.exe", "$env:ProgramFiles\HNC\Office 2024\HOffice130\Bin\Hwp.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $hwpExe) { throw "Hancom Hwp.exe was not found in known installation paths" }
$exeInfo = Get-Item -LiteralPath $hwpExe
$exeSha = (Get-FileHash -LiteralPath $hwpExe -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceReceipts = @(); $pdfReceipts = @(); $owned = [System.Collections.Generic.List[object]]::new(); $terminatedOwned = [System.Collections.Generic.List[int]]::new(); $allOk = $true
$agentSessionId = (Get-Process -Id $PID).SessionId
$baselineHwpPids = @(Get-Process -Name Hwp -ErrorAction SilentlyContinue | Where-Object SessionId -eq $agentSessionId | ForEach-Object { [pscustomobject]@{ Id=$_.Id; SessionId=$_.SessionId; StartTime=$_.StartTime.ToUniversalTime().ToString('o') } })
$adjudications = @()
$jobStarted = (Get-Date).ToUniversalTime().ToString("o")
foreach ($entry in $job.source_manifest.files) {
    $rel = [string]$entry.path
    $src = [System.IO.Path]::GetFullPath((Join-Path $sourceRoot $rel))
    if (-not $src.StartsWith($sourcePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw "source path escaped job-scoped source root" }
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "declared source file missing: $rel" }
    if ((Get-Item -LiteralPath $src).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw "declared source file must not be a symlink or reparse point: $rel" }
    $beforeHash = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($beforeHash -ne ([string]$entry.sha256).ToLowerInvariant()) { throw "source hash mismatch before capture: $rel" }
    $beforePids = @(Get-Process -Name Hwp -ErrorAction SilentlyContinue | Where-Object SessionId -eq $agentSessionId | ForEach-Object { [pscustomobject]@{ Id=$_.Id; SessionId=$_.SessionId; StartTime=$_.StartTime.ToUniversalTime().ToString('o') } })
    $hwp = $null; $ownedThis = @(); $pdfPath = Join-Path $jobOutput (([System.IO.Path]::GetFileNameWithoutExtension($rel)) + ".pdf"); $opened=$false; $saved=$false; $err=$null; $pageCount=$null
    $started = (Get-Date).ToUniversalTime().ToString("o"); $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if ([string]$job.hancom_build_expected -notin @([string]$exeInfo.VersionInfo.ProductVersion,[string]$exeInfo.VersionInfo.FileVersion)) { throw "HANCOM_BUILD_MISMATCH: expected $($job.hancom_build_expected), found product=$($exeInfo.VersionInfo.ProductVersion), file=$($exeInfo.VersionInfo.FileVersion)" }
        $hwp = New-Object -ComObject HWPFrame.HwpObject
        for ($probe=0; $probe -lt 20; $probe++) {
            $afterPids = @(Get-Process -Name Hwp -ErrorAction SilentlyContinue | Where-Object SessionId -eq $agentSessionId)
            $ownedThis = @($afterPids | Where-Object { $p=$_.Id; $p -notin @($beforePids.Id) } | ForEach-Object { [pscustomobject]@{ Id=$_.Id; SessionId=$_.SessionId; StartTime=$_.StartTime.ToUniversalTime().ToString('o') } })
            if ($ownedThis.Count -gt 0) { break }
            Start-Sleep -Milliseconds 250
        }
        if ($ownedThis.Count -ne 1) { throw "COM activation did not create exactly one job-owned Hwp.exe in the current interactive session; refusing document calls or Quit" }
        foreach ($p in $ownedThis) { $owned.Add($p) }
        try { $hwp.XHwpWindows.Item(0).Visible = $false } catch {}
        $opened = [bool]$hwp.Open($src,"HWPX","")
        if (-not $opened) { throw "Hwp Open returned false" }
        try { $pageCount = [int]$hwp.PageCount } catch {}
        $saved = [bool]$hwp.SaveAs($pdfPath,"PDF","")
        if (-not $saved -or -not (Test-Path -LiteralPath $pdfPath -PathType Leaf)) { throw "Hwp PDF export failed" }
    } catch { $err = @{ type=$_.Exception.GetType().FullName; message=$_.Exception.Message; hresult=("0x{0:X8}" -f ($_.Exception.HResult -band 0xffffffff)) }; $allOk=$false }
    finally {
        if ($null -ne $hwp) { if ($ownedThis.Count -eq 1) { try { $hwp.Quit() } catch {} }; try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) } catch {}; $hwp=$null }
        [GC]::Collect(); [GC]::WaitForPendingFinalizers()
        foreach ($ownedPid in $ownedThis) {
            $proc = Get-Process -Id $ownedPid.Id -ErrorAction SilentlyContinue
            if ($proc -and $proc.ProcessName -eq "Hwp" -and $proc.StartTime.ToUniversalTime().ToString('o') -eq $ownedPid.StartTime) {
                try { Stop-Process -Id $ownedPid.Id -Force -ErrorAction Stop } catch {}
            }
            if (-not (Get-Process -Id $ownedPid.Id -ErrorAction SilentlyContinue)) { $terminatedOwned.Add([int]$ownedPid.Id) }
        }
    }
    $sw.Stop(); $afterHash = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($afterHash -ne $beforeHash) { throw "immutable source bytes changed during capture: $rel" }
    $pdfExists = Test-Path -LiteralPath $pdfPath -PathType Leaf
    $pdfHash = if ($pdfExists) { (Get-FileHash -LiteralPath $pdfPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    $sourceReceipts += [ordered]@{ fixture_id=$entry.fixture_id; path=$rel; sha256=$beforeHash; bytes=(Get-Item -LiteralPath $src).Length; unchanged_after_capture=($beforeHash -eq $afterHash); lowering_family=$entry.lowering_family }
    $pdfReceipts += [ordered]@{ fixture_id=$entry.fixture_id; pdf_file=[System.IO.Path]::GetFileName($pdfPath); pdf_sha256=$pdfHash; bytes=$(if($pdfExists){(Get-Item -LiteralPath $pdfPath).Length}else{$null}); export_succeeded=($saved -and $pdfExists); elapsed_ms=[math]::Round($sw.Elapsed.TotalMilliseconds,3); error=$err; page_count=$pageCount }
}
$jobFinished = (Get-Date).ToUniversalTime().ToString("o")
$environment = [ordered]@{ hancom_version=$exeInfo.VersionInfo.ProductVersion; hancom_build=$exeInfo.VersionInfo.FileVersion; hancom_executable_path=$hwpExe; hancom_executable_sha256=$exeSha; windows_version=$windows.Caption; windows_build=$windows.BuildNumber; capture_process_id=$PID; process_session_id=$agentSessionId; interactive_session=($agentSessionId -ne 0); process_architecture=[System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString(); run_as_user="$env:USERDOMAIN\$env:USERNAME" }
$captureManifest = [ordered]@{ schema="chatgpt-web-hwpx-mcp/p414/capture-manifest/v1"; job_id=$job.job_id; exact_head=$job.exact_head; source_manifest_sha256=$job.source_manifest_sha256; environment=$environment; source_files=$sourceReceipts; outputs=$pdfReceipts; process_custody=@{ parent_pid=$PID; baseline_hwp_pids=$baselineHwpPids; owned_hwp_pids=@($owned); global_kill_used=$false }; started_at=$jobStarted; finished_at=$jobFinished }
$captureManifestPath = Join-Path $jobOutput "p414-capture-manifest.json"
$captureManifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $captureManifestPath -Encoding UTF8
$captureManifestSha = (Get-FileHash -LiteralPath $captureManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
foreach ($pdf in $pdfReceipts | Where-Object export_succeeded) {
    $viewPath = Join-Path $jobOutput $pdf.pdf_file
    Write-Host "Review axes: semantic math/hierarchy and references; table headers/overflow/page breaks; bar proportionality/visibility; KPI spacing/visibility; page rhythm/orphans/overlap. Record only evidence visible in this PDF."
    try { Start-Process -FilePath $viewPath | Out-Null } catch {}
    $visual = (Read-Host "Review $($pdf.fixture_id) in the PDF viewer. Enter PASS, PASS_WITH_RESIDUALS, FAIL, or PENDING")
    $visual = $visual.Trim().ToUpperInvariant()
    while ($visual -notin @("PASS","PASS_WITH_RESIDUALS","FAIL","PENDING")) { $visual = (Read-Host "Use only PASS, PASS_WITH_RESIDUALS, FAIL, or PENDING").Trim().ToUpperInvariant() }
    $notes = Read-Host "Optional visual note for $($pdf.fixture_id) (press Enter if none)"
    $defectsText = Read-Host "Observed defect codes, comma-separated: SEMANTIC_DISAPPEARANCE,VECTOR_ESCAPE,CLIPPING,OVERLAP,BAR_VISIBILITY_REGRESSION,KPI_VISIBILITY_REGRESSION,NOVEL_DEFECT (Enter if none)"
    $allowedDefects = @("SEMANTIC_DISAPPEARANCE","VECTOR_ESCAPE","CLIPPING","OVERLAP","BAR_VISIBILITY_REGRESSION","KPI_VISIBILITY_REGRESSION","NOVEL_DEFECT")
    $defects = @($defectsText.Split(',') | ForEach-Object { $_.Trim().ToUpperInvariant() } | Where-Object { $_ })
    if (@($defects | Where-Object { $_ -notin $allowedDefects }).Count -gt 0) { throw "Unknown P4.14 defect code entered: $defectsText" }
    $expectedDrift = Read-Host "If this is an already documented, build-specific expected difference, enter its P4.12/P4.13 reference; do not use for unexplained differences"
    $adjudication = [ordered]@{ fixture_id=$pdf.fixture_id; status=$visual; reviewer="$env:USERDOMAIN\$env:USERNAME"; reviewed_at=(Get-Date).ToUniversalTime().ToString('o'); note=$notes; defects=$defects }
    if (-not [string]::IsNullOrWhiteSpace($expectedDrift)) { $adjudication.build_specific_expected_drift = $expectedDrift.Trim() }
    $adjudications += $adjudication
}
$visualVerdict = if (@($adjudications | Where-Object status -eq "FAIL").Count -gt 0) { "FAIL" } elseif (@($adjudications | Where-Object status -eq "PENDING").Count -gt 0 -or $adjudications.Count -ne $pdfReceipts.Count) { "PENDING" } elseif (@($adjudications | Where-Object status -eq "PASS_WITH_RESIDUALS").Count -gt 0) { "PASS_WITH_RESIDUALS" } else { "PASS" }
$payload = [ordered]@{
    schema="chatgpt-web-hwpx-mcp/p414/distributed-native-capture/v1"; protocol_version="1.0"; product=$job.product
    job_id=$job.job_id; exact_head=$job.exact_head; source_manifest_sha256=$job.source_manifest_sha256; source_manifest=$job.source_manifest
    hancom_version=$exeInfo.VersionInfo.ProductVersion; hancom_build=$exeInfo.VersionInfo.FileVersion; hancom_executable_path=$hwpExe; hancom_executable_sha256=$exeSha
    windows_version=$windows.Caption; windows_build=$windows.BuildNumber; capture_agent_version="1.0.0"
    issued_at=$job.issued_at; expires_at=$job.expires_at; nonce=$job.nonce; source_files=$sourceReceipts; outputs=$pdfReceipts
    capture_manifest_sha256=$captureManifestSha
    process_custody=@{ parent_pid=$PID; baseline_hwp_pids=$baselineHwpPids; owned_hwp_pids=@($owned); terminated_owned_hwp_pids=@($terminatedOwned); global_kill_used=$false }
    capture_status=$(if($allOk -and $sourceReceipts.Count -eq $pdfReceipts.Count){"CAPTURED"}else{"FAILED"}); recovery_status="COMPLETE"
    visual_verdict=$visualVerdict; visual_observations=@{ human_adjudications=$adjudications; scope="PER_FIXTURE_HANCOM_PDF_INSPECTION" }
    document_binding=$job.document_binding; captured_at=$jobFinished; started_at=$jobStarted; finished_at=$jobFinished; elapsed_ms=[math]::Round(((Get-Date $jobFinished)-(Get-Date $jobStarted)).TotalMilliseconds,3)
}
$payload | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $payloadPath -Encoding UTF8
$null = & $python $signer sign --payload $payloadPath --private $privatePath --agent-id $identity.agent_id --key-id $identity.key_id --out $receiptPath
if ($LASTEXITCODE -ne 0) { throw "signed receipt materialization failed" }
$state = @{ job_id=$job.job_id; status="COMPLETE"; started_at=$jobStarted; finished_at=$jobFinished; receipt_sha256=(Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant() }
$state | ConvertTo-Json | Set-Content -LiteralPath $journal -Encoding UTF8
Write-Output "P414_CAPTURE_RECEIPT : $receiptPath"
Write-Output "P414_AGENT_IDENTITY : $identityPath"
Write-Output "P414_CAPTURE_STATUS : $($payload.capture_status)"
if (-not $allOk) { exit 1 }
