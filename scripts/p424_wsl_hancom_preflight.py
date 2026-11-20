"""Read-only readiness check for a user-approved WSL -> Windows Hancom job.

Never launches Hwp.exe, COM, PowerShell, or native conversion. The result
cannot establish that Hancom is installed or that native rendering passes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import zipfile

# Both `python3 scripts/p424_wsl_hancom_preflight.py` and package imports
# are supported without modifying sys.path or running arbitrary loaders.
if __package__:
    from .p423_wsl_hancom_pdf_bridge import _approved_windows_mount, on_wsl
else:
    from p423_wsl_hancom_pdf_bridge import _approved_windows_mount, on_wsl

MAX_SOURCE_BYTES = 100 * 1024 * 1024


def inspect_wsl_hancom_preflight(
    source: Path,
    destination: Path,
    *,
    repository_script: Path | None = None,
) -> dict:
    checks: dict[str, bool] = {"wsl_kernel": on_wsl()}
    errors: list[str] = []
    if not checks["wsl_kernel"]:
        errors.append("WSL_KERNEL_REQUIRED")
    for executable in ("wslpath", "powershell.exe"):
        checks[executable + "_on_path"] = shutil.which(executable) is not None
        if not checks[executable + "_on_path"]:
            errors.append("COMMAND_UNAVAILABLE_" + executable.upper().replace(".", "_"))
    script = repository_script or (
        Path(__file__).resolve().parent / "p423_hancom_native_pdf.ps1"
    )
    for label, path in (
        ("source", Path(source)),
        ("destination", Path(destination)),
        ("powershell_script", script),
    ):
        try:
            _approved_windows_mount(path)
            checks[label + "_on_windows_mount"] = True
        except (OSError, ValueError, RuntimeError):
            checks[label + "_on_windows_mount"] = False
            errors.append(label.upper() + "_MUST_BE_WINDOWS_MOUNTED")
    src = Path(source)
    dst = Path(destination)
    checks["source_regular_file"] = src.is_file() and not src.is_symlink()
    if not checks["source_regular_file"]:
        errors.append("SOURCE_MUST_BE_REGULAR_FILE")
    checks["source_extension"] = src.suffix.lower() == ".hwpx"
    if not checks["source_extension"]:
        errors.append("SOURCE_MUST_BE_HWPX")
    if checks["source_regular_file"]:
        size = src.stat().st_size
        checks["source_size"] = 100 <= size <= MAX_SOURCE_BYTES
        with src.open("rb") as inp:
            checks["source_zip_header"] = inp.read(4) in (bytes((80, 75, 3, 4)), bytes((80, 75, 5, 6)))
        checks["source_zip_directory"] = zipfile.is_zipfile(src)
    else:
        checks["source_size"] = False
        checks["source_zip_header"] = False
        checks["source_zip_directory"] = False
    if not checks["source_size"]:
        errors.append("SOURCE_SIZE_INVALID")
    if not checks["source_zip_header"]:
        errors.append("SOURCE_ZIP_HEADER_INVALID")
    if not checks["source_zip_directory"]:
        errors.append("SOURCE_ZIP_DIRECTORY_INVALID")
    checks["destination_new_pdf"] = (
        dst.suffix.lower() == ".pdf" and not dst.exists()
        and not dst.is_symlink() and dst.parent.is_dir()
    )
    if not checks["destination_new_pdf"]:
        errors.append("DESTINATION_MUST_BE_NEW_PDF")
    receipt = dst.with_suffix(".pdf.receipt.json")
    checks["receipt_path_vacant"] = not receipt.exists() and not receipt.is_symlink()
    if not checks["receipt_path_vacant"]:
        errors.append("RECEIPT_PATH_ALREADY_USED")
    checks["companion_script"] = script.is_file() and not script.is_symlink()
    if not checks["companion_script"]:
        errors.append("NATIVE_SCRIPT_NOT_FOUND")
    return {
        "schema": "p424/wsl-hancom-readonly-preflight/v1",
        "status": "READY_FOR_MANUAL_SMOKE" if not errors else "BLOCKED",
        "checks": checks,
        "issues": sorted(set(errors)),
        "hancom_installation_verified": False,
        "native_render_verified": False,
        "powershell_or_com_executed": False,
        "user_authorization_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    outcome = inspect_wsl_hancom_preflight(args.source, args.destination)
    print(json.dumps(outcome, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if outcome["status"] == "READY_FOR_MANUAL_SMOKE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
