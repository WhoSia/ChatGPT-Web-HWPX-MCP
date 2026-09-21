param(
  [Parameter(Mandatory=$true)][string]$InputPath,
  [Parameter(Mandatory=$true)][string]$OutputPath
)

$ErrorActionPreference = "Stop"
$hwp = $null
try {
  $hwp = New-Object -ComObject HWPFrame.HwpObject
  try { $hwp.XHwpWindows.Item(0).Visible = $false } catch {}
  try { $hwp.SetMessageBoxMode(0x00214411) | Out-Null } catch {}

  $resolved = (Resolve-Path $InputPath).Path
  $opened = $hwp.Open($resolved, "", "lock:false;forceopen:true;versionwarning:false;")
  if ($opened -eq $false) {
    throw "Hancom Open returned false for $InputPath"
  }

  if (Test-Path $OutputPath) {
    Remove-Item -Force $OutputPath
  }
  $saved = $hwp.SaveAs($OutputPath, "PDF", "")
  if ($saved -eq $false -or -not (Test-Path $OutputPath)) {
    throw "Hancom PDF SaveAs failed for $InputPath"
  }

  $item = Get-Item $OutputPath
  if ($item.Length -le 0) {
    throw "Hancom produced an empty PDF for $InputPath"
  }
  exit 0
}
finally {
  if ($hwp -ne $null) {
    try { $hwp.Clear(1) } catch {}
    try { $hwp.Quit() } catch {}
    try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) } catch {}
  }
}
