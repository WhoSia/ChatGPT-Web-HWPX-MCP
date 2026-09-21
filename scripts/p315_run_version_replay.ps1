param(
  [Parameter(Mandatory=$true)][string]$SessionId,
  [string]$HancomExe = "",
  [string]$OutRoot = "artifacts/p315-replays"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$SessionRoot = Join-Path $RepoRoot (Join-Path $OutRoot $SessionId)
$PackDir = Join-Path $SessionRoot "pack"
$Before = Join-Path $SessionRoot "font-files-before.json"
$After = Join-Path $SessionRoot "font-files-after.json"
$SessionJson = Join-Path $SessionRoot "session.json"

New-Item -ItemType Directory -Force -Path $SessionRoot | Out-Null

& (Join-Path $PSScriptRoot "p315_font_file_custody.ps1") -OutFile $Before
if ($LASTEXITCODE -ne 0) { throw "Pre-capture font custody failed." }

$runner = Join-Path $PSScriptRoot "p313r1_run_hancom_capture.ps1"
$runnerArgs = @("-ExecutionPolicy","Bypass","-File",$runner,"-OutDir",(Join-Path $OutRoot (Join-Path $SessionId "pack")))
if ($HancomExe) { $runnerArgs += @("-HancomExe",$HancomExe) }
& powershell @runnerArgs
if ($LASTEXITCODE -ne 0) { throw "Hancom replay capture failed." }

& (Join-Path $PSScriptRoot "p315_font_file_custody.ps1") -OutFile $After
if ($LASTEXITCODE -ne 0) { throw "Post-capture font custody failed." }

$VenvPython = Join-Path $RepoRoot ".venv-p313r1\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  $py = Get-Command python -ErrorAction SilentlyContinue
  if (-not $py) { throw "Python 3.12+ is required." }
  $Venv = Join-Path $RepoRoot ".venv-p313r1"
  & $py.Source -m venv $Venv
  & $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-capture.txt
}

$buildArgs = @(
  "scripts/p315_build_session.py",
  "--pack",$PackDir,
  "--font-before",$Before,
  "--font-after",$After,
  "--session-id",$SessionId,
  "--out",$SessionJson
)
& $VenvPython @buildArgs
if ($LASTEXITCODE -ne 0) { throw "P3.15 replay-session construction failed." }

$Zip = "$SessionRoot.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
Compress-Archive -Path (Join-Path $SessionRoot "*") -DestinationPath $Zip -CompressionLevel Optimal

Write-Host ""
Write-Host "P3.15 replay session complete."
Write-Host "Session: $SessionJson"
Write-Host "Upload-ready ZIP: $Zip"
Write-Host ""
Write-Host "For cross-version promotion, run this script once per distinct Hancom version on the same Windows/font environment."
