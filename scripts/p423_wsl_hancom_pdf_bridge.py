"""Local WSL → Windows Hangul HWPX-to-PDF handoff.

WSL never renders the file: it passes explicitly approved Windows-mounted
paths to the installed Hwp.exe via PowerShell/COM, then validates the PDF
and receipt. Not the production P4.14 signed-agent protocol.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def on_wsl() -> bool:
    if os.name != "posix":
        return False
    release = os.uname().release.lower()
    return "microsoft" in release or "wsl" in release or bool(os.environ.get("WSL_DISTRO_NAME"))


def _approved_windows_mount(path: Path) -> Path:
    resolved = path.resolve()
    if not re.match(r"^/mnt/[a-zA-Z]/", str(resolved)):
        raise ValueError("Local Hancom interop requires paths under /mnt/<windows-drive>/")
    return resolved


def _windows_path(path: Path) -> str:
    converted = subprocess.run(
        ["wslpath", "-w", str(path)],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    if not re.match(r"^[a-zA-Z]:\\", converted):
        raise ValueError("Windows path conversion did not yield a local drive path")
    return converted


def export_wsl_native_pdf(source: Path, destination: Path, *, timeout_seconds: int = 240) -> dict:
    if not on_wsl():
        raise RuntimeError("WSL_ENVIRONMENT_REQUIRED: run in WSL with Windows interop")
    if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 600:
        raise ValueError("timeout_seconds must be an integer from 60 to 600")
    source = _approved_windows_mount(source)
    destination = _approved_windows_mount(destination)
    if source.suffix.lower() != ".hwpx" or not source.is_file():
        raise ValueError("Existing .hwpx input required")
    if destination.suffix.lower() != ".pdf" or destination.exists() or not destination.parent.is_dir():
        raise ValueError("Use a new .pdf path in an existing Windows-mounted directory")
    script = _approved_windows_mount(Path(__file__).resolve().parent / "p423_hancom_native_pdf.ps1")
    if not script.is_file():
        raise FileNotFoundError("P4.23 native PDF PowerShell source missing")
    source_sha = _sha(source)
    receipt = destination.with_suffix(".pdf.receipt.json")
    if receipt.exists():
        raise ValueError("Receipt destination exists; refusing to replace existing evidence")
    cmd = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-File", _windows_path(script),
        "-InputPath", _windows_path(source),
        "-OutputPath", _windows_path(destination),
        "-ReceiptPath", _windows_path(receipt),
    ]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        # Do not kill any Hangul processes: the signed P4.14 worker, not this
        # local smoke runner, owns remote process cleanup authority.
        raise RuntimeError("HANCOM_PDF_TIMEOUT: inspect the Windows job-owned process before retry") from exc
    if not receipt.is_file():
        raise RuntimeError("HANCOM_RECEIPT_MISSING: Windows export did not produce a receipt")
    try:
        parsed = json.loads(receipt.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError("HANCOM_RECEIPT_MALFORMED") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("HANCOM_RECEIPT_MALFORMED")
    if result.returncode != 0 or parsed.get("status") != "PDF_CREATED_UNREVIEWED":
        raise RuntimeError("HANCOM_NATIVE_EXPORT_FAILED: inspect the local receipt")
    if not destination.is_file():
        raise RuntimeError("HANCOM_EXPORT_PDF_MISSING")
    with destination.open("rb") as pdf_stream:
        pdf_signature = pdf_stream.read(5)
    if (
        parsed.get("engine") != "HANCOM_HWP_EXE_COM"
        or parsed.get("input_sha256") != source_sha
        or _sha(source) != source_sha
        or parsed.get("output_sha256") != _sha(destination)
        or parsed.get("output_bytes") != destination.stat().st_size
        or destination.stat().st_size < 64
        or pdf_signature != b"%PDF-"
    ):
        raise RuntimeError("HANCOM_EXPORT_RECEIPT_OR_BYTES_MISMATCH")
    return {
        "status": "PDF_CREATED_UNREVIEWED",
        "native_visual_acceptance": "NOT_ADJUDICATED",
        "input_sha256": source_sha,
        "pdf_sha256": _sha(destination),
        "pdf_bytes": destination.stat().st_size,
        "hancom_product_version": parsed.get("hancom_product_version"),
        "hancom_executable_sha256": parsed.get("hancom_executable_sha256"),
        "hancom_page_count": parsed.get("hancom_page_count"),
        "receipt_path": str(receipt),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="WSL → Windows native Hancom HWPX→PDF smoke test")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        result = export_wsl_native_pdf(args.source, args.destination)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
