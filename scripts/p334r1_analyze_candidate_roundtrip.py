#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from xml.etree import ElementTree as ET

from p323_advanced_tables import build_advanced_table_map


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in {path}: {bad}")
        names = zf.namelist()
        if not names or names[0] != "mimetype":
            raise RuntimeError(f"{path}: mimetype is not first ZIP entry")
        if zf.read("mimetype") != b"application/hwp+zip":
            raise RuntimeError(f"{path}: invalid HWPX mimetype")
        for name in names:
            if name.endswith((".xml", ".rdf", ".opf")):
                ET.fromstring(zf.read(name))
        return {"entry_count": len(names), "crc_pass": True, "xml_parse_pass": True}


def compare(before: Path, after: Path) -> dict:
    b = validate_archive(before)
    a = validate_archive(after)
    bm = build_advanced_table_map(before)["tables"][0]
    am = build_advanced_table_map(after)["tables"][0]

    def geometry(table: dict) -> list[dict]:
        return [
            {
                "row": c["row"],
                "col": c["col"],
                "row_span": c["row_span"],
                "col_span": c["col_span"],
                "width": c["width"],
                "height": c["height"],
                "text": c["text"],
            }
            for c in table["cells"]
        ]

    before_geometry = geometry(bm)
    after_geometry = geometry(am)
    return {
        "before_sha256": sha(before),
        "after_sha256": sha(after),
        "byte_identical": before.read_bytes() == after.read_bytes(),
        "before_archive": b,
        "after_archive": a,
        "before_rows": bm["rows"],
        "after_rows": am["rows"],
        "before_cols": bm["cols"],
        "after_cols": am["cols"],
        "structure_preserved": (
            bm["rows"] == am["rows"]
            and bm["cols"] == am["cols"]
            and before_geometry == after_geometry
        ),
        "before_geometry": before_geometry,
        "after_geometry": after_geometry,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default="artifacts/p334r1-candidate-roundtrip-pack")
    args = ap.parse_args()
    root = Path(args.pack)
    manifest = json.loads((root / "roundtrip-manifest.json").read_text(encoding="utf-8"))

    reports = []
    missing = []
    failed = []
    for case in manifest["cases"]:
        d = root / case["id"]
        before = d / "candidate-before-hancom.hwpx"
        after = d / "candidate-after-hancom.hwpx"
        if not after.exists():
            missing.append(case["id"])
            continue
        report = {"case_id": case["id"], **compare(before, after)}
        if not report["structure_preserved"]:
            failed.append(case["id"])
        (d / "roundtrip-analysis.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        reports.append(report)

    summary = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r1/candidate-roundtrip-analysis/v1",
        "cases_analyzed": len(reports),
        "cases_missing": missing,
        "cases_structure_failed": failed,
        "pass": not missing and not failed,
        "reports": reports,
    }
    (root / "roundtrip-analysis-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"analyzed": len(reports), "missing": missing, "failed": failed}, ensure_ascii=False))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
