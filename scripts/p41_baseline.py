from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from hwpx import HwpxDocument
from hwpx_mcp.operations.p41_operational import PRODUCT, profile_operations, runtime_compatibility_matrix

REQUIRED = {"mimetype", "version.xml", "META-INF/container.xml", "Contents/content.hpf", "Contents/header.xml", "Contents/section0.xml"}

def make_doc(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P4.1 baseline")
    doc.add_paragraph("둘째 문단")
    doc.save_to_path(str(path))
    doc.close()

def validate_package(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        names = {x.filename for x in infos}
        if not REQUIRED.issubset(names):
            raise RuntimeError("baseline HWPX missing required package parts")
        if infos[0].filename != "mimetype" or archive.read("mimetype") != b"application/hwp+zip":
            raise RuntimeError("baseline HWPX mimetype contract failed")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="p41-baseline.json")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        existing = root / "existing.hwpx"
        make_doc(existing)
        validate_package(existing)
        def create_validate():
            target = root / "candidate.hwpx"
            make_doc(target)
            validate_package(target)
        def validate_existing():
            validate_package(existing)
        def compatibility_snapshot():
            runtime_compatibility_matrix()
        result = profile_operations(
            {
                "python_hwpx_create_and_package_validate": (create_validate, 5000.0),
                "existing_hwpx_package_validate": (validate_existing, 3000.0),
                "runtime_compatibility_snapshot": (compatibility_snapshot, 3000.0),
            },
            sample_count=args.samples,
        )
    result["runtime_compatibility"] = runtime_compatibility_matrix()
    result["product"] = PRODUCT
    result["scope"] = "LOCAL_PRODUCT_CORE_BASELINE; LIVE_HTTP_LATENCY_IS_MEASURED_BY_PRODUCTION_BOUNDARY_RECEIPT"
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
