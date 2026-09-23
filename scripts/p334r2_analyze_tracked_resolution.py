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

from p2_document import build_document_map
from p322_review_workflow import build_review_workflow_map


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def archive_census(path: Path) -> dict:
    marks = {
        "insertBegin": 0,
        "insertEnd": 0,
        "deleteBegin": 0,
        "deleteEnd": 0,
    }
    track_nodes = {}
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
            if not name.endswith((".xml", ".rdf", ".opf", ".hpf")):
                continue
            root = ET.fromstring(zf.read(name))
            for node in root.iter():
                ln = local(node.tag)
                if ln in marks:
                    marks[ln] += 1
                lower = ln.lower()
                if "trackchange" in lower:
                    payload = {
                        "tag": ln,
                        "attrs": dict(sorted(node.attrib.items())),
                        "child_tags": [local(child.tag) for child in list(node)],
                    }
                    if "encr" in lower:
                        payload["subtree_sha256"] = hashlib.sha256(
                            ET.tostring(node, encoding="utf-8")
                        ).hexdigest()
                    track_nodes.setdefault(name, []).append(payload)

        return {
            "entry_count": len(names),
            "crc_pass": True,
            "xml_parse_pass": True,
            "marks": marks,
            "track_nodes": track_nodes,
        }


def visible_body_text(path: Path) -> list[str]:
    return [
        item["text"]
        for item in build_document_map(path)["paragraphs"]
        if item.get("body_paragraph_index") is not None
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default="artifacts/p334r2-tracked-resolution-pack")
    args = ap.parse_args()
    root = Path(args.pack)
    manifest = json.loads((root / "capture-manifest.json").read_text(encoding="utf-8"))

    reports = []
    failures = []
    for case in manifest["cases"]:
        d = root / case["id"]
        source = d / "source.hwpx"
        target = d / "target.hwpx"
        if not target.exists():
            failures.append({"case": case["id"], "reason": "target_missing"})
            continue

        before = build_review_workflow_map(source)
        after = build_review_workflow_map(target)
        source_census = archive_census(source)
        target_census = archive_census(target)
        body = visible_body_text(target)

        report = {
            "case_id": case["id"],
            "kind": case["kind"],
            "action": case["action"],
            "source_sha256": sha(source),
            "target_sha256": sha(target),
            "byte_identical": source.read_bytes() == target.read_bytes(),
            "before_counts": before["counts"],
            "after_counts": after["counts"],
            "before_body_text": visible_body_text(source),
            "after_body_text": body,
            "source_census": source_census,
            "target_census": target_census,
        }

        if case["kind"] == "resolution":
            expected = case["expected_after"]
            resolved_text_ok = expected in body
            marks_cleared = all(v == 0 for v in target_census["marks"].values())
            header_changes_cleared = after["counts"]["tracked_changes"] == 0
            report["expected_after"] = expected
            report["resolved_text_ok"] = resolved_text_ok
            report["marks_cleared"] = marks_cleared
            report["header_changes_cleared"] = header_changes_cleared
            report["pass"] = resolved_text_ok and marks_cleared and header_changes_cleared
        else:
            encryption_nodes = []
            for part_nodes in target_census["track_nodes"].values():
                encryption_nodes.extend(
                    node for node in part_nodes if "encr" in node["tag"].lower()
                )
            report["protection_encryption_nodes"] = encryption_nodes
            report["pass"] = bool(encryption_nodes)
            if not encryption_nodes:
                report["note"] = (
                    "No track-change encryption subtree observed; do not infer protection authority."
                )

        if not report["pass"]:
            failures.append({"case": case["id"], "reason": "semantic_probe_failed"})
        (d / "analysis.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        reports.append(report)

    summary = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r2/native-resolution-analysis/v1",
        "cases_analyzed": len(reports),
        "failures": failures,
        "all_resolution_semantics_pass": all(
            r["pass"] for r in reports if r["kind"] == "resolution"
        ) and len([r for r in reports if r["kind"] == "resolution"]) == 6,
        "protection_encoding_observed": any(
            r["pass"] for r in reports if r["kind"] == "protection"
        ),
        "reports": reports,
    }
    (root / "analysis-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "analyzed": summary["cases_analyzed"],
        "failures": failures,
        "resolution_pass": summary["all_resolution_semantics_pass"],
        "protection_encoding_observed": summary["protection_encoding_observed"],
    }, ensure_ascii=False))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
