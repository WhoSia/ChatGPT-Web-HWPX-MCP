param(
  [Parameter(Mandatory=$true)][string]$InputPath,
  [Parameter(Mandatory=$true)][string]$OutputPath
)

$ErrorActionPreference = "Stop"
$hwp = $null
$step = "init"
try {
  $step = "create-com"
  $hwp = New-Object -ComObject HWPFrame.HwpObject
  $step = "window-visibility"
  try { $hwp.XHwpWindows.Item(0).Visible = $false } catch {}
  $step = "message-box-mode"
  try { $hwp.SetMessageBoxMode(0x00214411) | Out-Null } catch {}

  $step = "resolve-input"
  $resolvedItem = Resolve-Path $InputPath
  if (-not $resolvedItem) { throw "Input path could not be resolved: $InputPath" }
  $resolved = $resolvedItem.Path

  $step = "open"
  $opened = $hwp.Open($resolved, "", "lock:false;forceopen:true;versionwarning:false;")
  if ($opened -eq $false) {
    throw "Hancom Open returned false for $InputPath"
  }

  if (Test-Path $OutputPath) {
    Remove-Item -Force $OutputPath
  }
  $step = "save-as-pdf"
  $saved = $hwp.SaveAs($OutputPath, "PDF", "")
  if ($saved -eq $false -or -not (Test-Path $OutputPath)) {
    throw "Hancom PDF SaveAs failed for $InputPath"
  }

  $step = "validate-pdf"
  $item = Get-Item $OutputPath
  if ($item.Length -le 0) {
    throw "Hancom produced an empty PDF for $InputPath"
  }
  exit 0
}
catch {
  [Console]::Error.WriteLine("P3.13-R1 Hancom export failed at step '$step': $($_.Exception.Message)")
  exit 1
}
finally {
  if ($hwp -ne $null) {
    try { $hwp.Clear(1) } catch {}
    try { $hwp.Quit() } catch {}
    try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) } catch {}
  }
}
