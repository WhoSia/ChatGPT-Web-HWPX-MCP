#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import server
from p2_document import build_document_map
from p322_review_workflow import build_review_workflow_map


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_ok(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in {path}: {bad}")
        names = zf.namelist()
        if not names or names[0] != "mimetype":
            raise RuntimeError("mimetype is not first ZIP entry")
        if zf.read("mimetype") != b"application/hwp+zip":
            raise RuntimeError("invalid HWPX mimetype")
        for name in names:
            if name.endswith((".xml", ".rdf", ".opf", ".hpf")):
                ET.fromstring(zf.read(name))
        return {"entry_count": len(names), "crc_pass": True, "xml_parse_pass": True}


def body(path: Path) -> list[str]:
    return [
        item["text"]
        for item in build_document_map(path)["paragraphs"]
        if item.get("body_paragraph_index") is not None
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default="artifacts/p334r2-candidate-roundtrip-pack")
    args = ap.parse_args()
    root = Path(args.pack)
    manifest = json.loads((root / "roundtrip-manifest.json").read_text(encoding="utf-8"))

    reports = []
    failures = []
    for case in manifest["cases"]:
        d = root / case["id"]
        before = d / "candidate-before-hancom.hwpx"
        after = d / "candidate-after-hancom.hwpx"
        if not after.exists():
            failures.append({"case": case["id"], "reason": "after_missing"})
            continue

        b_counts = build_review_workflow_map(before)["counts"]
        a_counts = build_review_workflow_map(after)["counts"]
        b_body = body(before)
        a_body = body(after)
        structural = (
            b_counts["tracked_changes"] == 0
            and b_counts["track_change_authors"] == 0
            and a_counts["tracked_changes"] == 0
            and a_counts["track_change_authors"] == 0
            and b_body == a_body
            and case["expected"] in a_body
        )
        report = {
            "case_id": case["id"],
            "before_sha256": sha(before),
            "after_sha256": sha(after),
            "byte_identical": before.read_bytes() == after.read_bytes(),
            "before_counts": b_counts,
            "after_counts": a_counts,
            "before_body_text": b_body,
            "after_body_text": a_body,
            "before_package": package_ok(before),
            "after_package": package_ok(after),
            "validator_ok": bool(server.validate_hwpx_package(after).get("ok", False)),
            "structure_preserved": structural,
        }
        report["pass"] = report["validator_ok"] and structural
        if not report["pass"]:
            failures.append({"case": case["id"], "reason": "roundtrip_semantic_drift"})
        (d / "analysis.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        reports.append(report)

    summary = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r2/candidate-roundtrip-analysis/v1",
        "cases_analyzed": len(reports),
        "failures": failures,
        "pass": len(reports) == len(manifest["cases"]) and not failures,
        "reports": reports,
    }
    (root / "analysis-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"pass": summary["pass"], "failures": failures}, ensure_ascii=False))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
