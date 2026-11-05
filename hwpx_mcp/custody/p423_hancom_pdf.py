"""Native Windows Hancom PDF conversion worker.

This worker uses the installed Hancom Hangul Hwp.exe automation server
(HWPFrame.HwpObject), never LibreOffice or a look-alike renderer. It is an
on-Windows conversion primitive, not the Linux Render delivery endpoint.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


class HancomPdfUnavailable(RuntimeError):
    """Native Hangul cannot run in the current execution environment."""


class HancomPdfConversionError(RuntimeError):
    """Hangul opened or saved unsuccessfully; no PDF may be published."""


def is_windows_hancom_host() -> bool:
    return os.name == "nt"


def native_pdf_capability() -> dict[str, Any]:
    return {
        "engine": "HANCOM_HWP_EXE_COM",
        "available": is_windows_hancom_host(),
        "installation_verified": False,
        "availability_basis": "OS platform only; COM activation attempted at conversion time",
        "required_platform": "Windows",
        "requires_interactive_hancom_installation": True,
        "native_pdf_visual_adjudication": "SEPARATE_REQUIRED",
        "host_delivery": "NOT_IMPLEMENTED_BY_WORKER",
    }


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_native_hwp_pdf(
    source: str | Path,
    destination: str | Path,
    *,
    powershell_exe: str = "powershell.exe",
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Create a *real* Hancom PDF or fail without changing the source.

    Input must be an existing .hwpx owned/authorized by the higher-level
    caller; output is a new .pdf path. Caller is responsible for user approval,
    access control, durable revision binding and download delivery.
    """
    if not is_windows_hancom_host():
        raise HancomPdfUnavailable("WINDOWS_HANCOM_AGENT_REQUIRED")
    source = Path(source).resolve(strict=True)
    destination = Path(destination).absolute()
    if source.suffix.lower() != ".hwpx" or destination.suffix.lower() != ".pdf":
        raise ValueError("source must be .hwpx and destination must be .pdf")
    if not destination.parent.is_dir() or destination.exists():
        raise ValueError("PDF destination parent must exist and output must not exist")
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 600:
        raise ValueError("timeout_seconds must be an integer between 30 and 600")
    if not powershell_exe or "/" in powershell_exe or "\\" in powershell_exe:
        raise ValueError("powershell executable must be a command name, not a path")
    script = Path(__file__).resolve().parents[2] / "scripts" / "p423_hancom_native_pdf.ps1"
    if not script.is_file():
        raise FileNotFoundError("Native Windows Hancom export script is missing")
    before = _sha(source)
    with tempfile.TemporaryDirectory(prefix="p423-native-pdf-") as tmp:
        receipt_path = Path(tmp) / "receipt.json"
        command = [
            powershell_exe, "-NoProfile", "-NonInteractive", "-File", str(script),
            "-InputPath", str(source), "-OutputPath", str(destination),
            "-ReceiptPath", str(receipt_path),
        ]
        try:
            completed = subprocess.run(
                command, text=True, capture_output=True, timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            if destination.exists():
                destination.unlink()
            raise HancomPdfConversionError("HANCOM_PDF_CONVERSION_TIMED_OUT") from exc
        if completed.returncode != 0 or not receipt_path.is_file():
            if destination.exists():
                destination.unlink()
            raise HancomPdfConversionError("HANCOM_PDF_CONVERSION_FAILED")
        # The worker is an external process: its receipt is untrusted until
        # parsed, checked against the real bytes, and bound to unchanged input.
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
            if not isinstance(receipt, dict):
                raise ValueError("receipt must be an object")
            valid = (
                receipt.get("status") == "PDF_CREATED_UNREVIEWED"
                and receipt.get("engine") == "HANCOM_HWP_EXE_COM"
                and receipt.get("input_sha256") == before
                and _sha(source) == before
                and destination.is_file()
                and receipt.get("output_sha256") == _sha(destination)
                and receipt.get("output_bytes") == destination.stat().st_size
                and destination.stat().st_size >= 64
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            valid = False
        if not valid:
            if destination.exists():
                destination.unlink()
            raise HancomPdfConversionError("HANCOM_PDF_RECEIPT_MISMATCH")
        receipt["source_path"] = None
        receipt["output_path"] = None
        receipt["pdf_sha256"] = receipt.pop("output_sha256")
        receipt["source_sha256"] = receipt.pop("input_sha256")
        return receipt
