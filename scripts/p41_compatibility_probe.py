from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from hwpx import HwpxDocument

TARGET_TESTS = [
    "test_p318_document_setup.py",
    "test_p319_structured_publishing.py",
    "test_p338_rich_builder.py",
    "test_p41_operational.py",
]

def minimal_smoke() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P4.1 compatibility probe")
        doc.add_paragraph("둘째 문단")
        doc.save_to_path(str(path))
        doc.close()
        with zipfile.ZipFile(path, "r") as archive:
            return archive.infolist()[0].filename == "mimetype" and archive.read("mimetype") == b"application/hwp+zip"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--mode", choices=["pinned", "candidate"], required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    observed = md.version("python-hwpx")
    smoke_ok = False
    smoke_error = None
    try:
        smoke_ok = minimal_smoke()
    except Exception as exc:
        smoke_error = type(exc).__name__
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TARGET_TESTS],
        capture_output=True, text=True, timeout=240, check=False,
    )
    tests_ok = proc.returncode == 0
    version_ok = observed == args.expected_version
    verdict = "PASS" if version_ok and smoke_ok and tests_ok else "INCOMPATIBLE_OR_UNVALIDATED"
    receipt = {
        "schema": "chatgpt-web-hwpx-mcp/p4.1/compatibility-probe/v1",
        "mode": args.mode,
        "expected_python_hwpx": args.expected_version,
        "observed_python_hwpx": observed,
        "version_match": version_ok,
        "minimal_hwpx_smoke": smoke_ok,
        "smoke_error_class": smoke_error,
        "targeted_regression_tests": tests_ok,
        "targeted_test_files": TARGET_TESTS,
        "pytest_returncode": proc.returncode,
        "pytest_tail": (proc.stdout + "\n" + proc.stderr)[-6000:],
        "verdict": verdict,
        "production_pin_changed": False,
    }
    Path(args.out).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    if args.mode == "pinned":
        return 0 if verdict == "PASS" else 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
