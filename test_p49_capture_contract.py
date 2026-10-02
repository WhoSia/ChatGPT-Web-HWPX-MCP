from pathlib import Path


def test_p49_capture_script_owns_cleanup_by_pid_difference_only():
    text = Path("scripts/p49_run_hancom_capture.ps1").read_text(encoding="utf-8")
    assert "Get-HwpPidSet" in text
    assert "$ownedPids = @($afterCreate | Where-Object { $_ -notin $before })" in text
    assert "Stop-Process -Id $ownedPid -Force" in text
    assert "Get-Process Hwp -ErrorAction SilentlyContinue | Stop-Process" not in text
    assert "$hwp.Quit()" in text
    assert "ReleaseComObject" in text
