param(
    [Parameter(Mandatory=$true)]
    [string]$SourceDir,

    [Parameter(Mandatory=$true)]
    [string]$OutputDir,

    [string]$Filter = "*.hwpx",

    [int]$ProcessExitTimeoutSeconds = 8,

    [switch]$Visible
)

$ErrorActionPreference = "Stop"

function Get-HwpPidSet {
    return @(Get-Process Hwp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$beforeAll = @(Get-HwpPidSet)
$sources = @(Get-ChildItem -LiteralPath $SourceDir -Filter $Filter -File | Sort-Object Name)
if ($sources.Count -eq 0) {
    throw "No HWPX sources found in $SourceDir with filter $Filter"
}

$rows = @()

foreach ($src in $sources) {
    $hwp = $null
    $ownedPids = @()
    $opened = $false
    $saved = $false
    $registerModule = $null
    $forcedCleanup = @()
    $status = "PENDING"
    $errorType = $null
    $errorMessage = $null
    $errorHresult = $null
    $startedAt = (Get-Date).ToString("o")
    $before = @(Get-HwpPidSet)
    $pdf = Join-Path $OutputDir ($src.BaseName + ".pdf")

    try {
        $hwp = New-Object -ComObject HWPFrame.HwpObject

        Start-Sleep -Milliseconds 300
        $afterCreate = @(Get-HwpPidSet)
        $ownedPids = @($afterCreate | Where-Object { $_ -notin $before })

        try {
            $registerModule = $hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        }
        catch {
            $registerModule = $false
        }

        if ($Visible) {
            try { $hwp.XHwpWindows.Item(0).Visible = $true } catch {}
        }
        else {
            try { $hwp.XHwpWindows.Item(0).Visible = $false } catch {}
        }

        $opened = [bool]$hwp.Open($src.FullName, "HWPX", "")
        if (-not $opened) {
            throw "HWP Open() returned False"
        }

        $saved = [bool]$hwp.SaveAs($pdf, "PDF", "")
        if (-not (Test-Path -LiteralPath $pdf)) {
            throw "PDF was not materialized"
        }

        $status = "PASS"
    }
    catch {
        $status = "FAIL"
        $errorType = $_.Exception.GetType().FullName
        $errorMessage = $_.Exception.Message
        $errorHresult = ("0x{0:X8}" -f ($_.Exception.HResult -band 0xffffffff))
    }
    finally {
        if ($null -ne $hwp) {
            try { $hwp.Quit() } catch {}
            try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($hwp) } catch {}
            $hwp = $null
        }

        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()

        $deadline = (Get-Date).AddSeconds($ProcessExitTimeoutSeconds)
        do {
            $aliveOwned = @(
                $ownedPids | Where-Object {
                    Get-Process -Id $_ -ErrorAction SilentlyContinue
                }
            )
            if ($aliveOwned.Count -eq 0) { break }
            Start-Sleep -Milliseconds 250
        } while ((Get-Date) -lt $deadline)

        $aliveOwned = @(
            $ownedPids | Where-Object {
                Get-Process -Id $_ -ErrorAction SilentlyContinue
            }
        )

        foreach ($pid in $aliveOwned) {
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                $forcedCleanup += $pid
            }
            catch {}
        }
    }

    $pdfExists = Test-Path -LiteralPath $pdf
    $rows += [PSCustomObject][ordered]@{
        source_name = $src.Name
        source_path = $src.FullName
        source_sha256 = Get-Sha256 $src.FullName
        pdf_path = $pdf
        pdf_exists = $pdfExists
        pdf_bytes = $(if ($pdfExists) { (Get-Item -LiteralPath $pdf).Length } else { $null })
        pdf_sha256 = $(if ($pdfExists) { Get-Sha256 $pdf } else { $null })
        open_return = $opened
        saveas_return = $saved
        register_module_return = $registerModule
        owned_hwp_pids = @($ownedPids)
        forced_cleanup_pids = @($forcedCleanup)
        process_exit_clean = ($forcedCleanup.Count -eq 0)
        status = $status
        error_type = $errorType
        error_hresult = $errorHresult
        error_message = $errorMessage
        started_at = $startedAt
        finished_at = (Get-Date).ToString("o")
    }
}

$manifest = [ordered]@{
    schema = "chatgpt-web-hwpx-mcp/p49/hancom-capture/v1"
    generated_at = (Get-Date).ToString("o")
    source_dir = (Resolve-Path $SourceDir).Path
    output_dir = (Resolve-Path $OutputDir).Path
    baseline_hwp_pids = @($beforeAll)
    source_count = $rows.Count
    pass_count = @($rows | Where-Object status -eq "PASS").Count
    fail_count = @($rows | Where-Object status -eq "FAIL").Count
    rows = $rows
    authority = "HANCOM_NATIVE_CAPTURE_WITH_OWNED_PROCESS_LIFECYCLE"
}

$manifestPath = Join-Path $OutputDir "p49-native-capture-manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "P49_NATIVE_CAPTURE"
Write-Host "PASS : $($manifest.pass_count)"
Write-Host "FAIL : $($manifest.fail_count)"
Write-Host "MANIFEST : $manifestPath"
