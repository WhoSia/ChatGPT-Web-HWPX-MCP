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


def password_info(path: Path) -> list[dict]:
    found = []
    with zipfile.ZipFile(path) as zf:
        if zf.testzip():
            raise RuntimeError(f"CRC failure: {path}")
        for name in zf.namelist():
            if not name.endswith((".xml", ".hpf", ".rdf", ".opf")):
                continue
            root = ET.fromstring(zf.read(name))
            for node in root.iter():
                if local(node.tag) != "config-item-set":
                    continue
                if node.attrib.get("name") != "TrackChangePasswordInfo":
                    continue
                items = {}
                for child in list(node):
                    if local(child.tag) != "config-item":
                        continue
                    items[child.attrib.get("name")] = child.text or ""
                found.append({
                    "part": name,
                    "items": items,
                    "sha256": hashlib.sha256(
                        ET.tostring(node, encoding="utf-8")
                    ).hexdigest(),
                })
    return found


def body_text(path: Path) -> list[str]:
    return [
        item["text"]
        for item in build_document_map(path)["paragraphs"]
        if item.get("body_paragraph_index") is not None
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default="artifacts/p334r2-protected-resolution-pack")
    args = ap.parse_args()
    root = Path(args.pack)
    manifest = json.loads((root / "capture-manifest.json").read_text(encoding="utf-8"))

    reports = []
    failures = []
    for case in manifest["cases"]:
        target = root / case["id"] / "target.hwpx"
        if not target.exists():
            failures.append({"case": case["id"], "reason": "target_missing"})
            continue
        mapped = build_review_workflow_map(target)
        texts = body_text(target)
        pw = password_info(target)
        tracked = mapped["counts"]["tracked_changes"]
        authors = mapped["counts"]["track_change_authors"]

        report = {
            "case_id": case["id"],
            "action": case["action"],
            "sha256": sha(target),
            "body_text": texts,
            "tracked_changes": tracked,
            "track_change_authors": authors,
            "password_info": pw,
        }
        if case["id"] == "protected-cancel-accept":
            report["pass"] = (
                tracked == 1
                and authors == 1
                and bool(pw)
                and "delta protected base" in texts
            )
        elif case["id"] == "protected-correct-accept":
            report["pass"] = (
                tracked == 0
                and "delta protected base +protected" in texts
            )
            report["password_info_after_resolution"] = bool(pw)
        else:
            report["pass"] = (
                tracked == 0
                and "delta protected base" in texts
                and all("+protected" not in text for text in texts)
            )
            report["password_info_after_resolution"] = bool(pw)

        if not report["pass"]:
            failures.append({"case": case["id"], "reason": "protected_resolution_semantics_failed"})
        (root / case["id"] / "analysis.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        reports.append(report)

    summary = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r2/protected-resolution-analysis/v1",
        "cases_analyzed": len(reports),
        "failures": failures,
        "pass": len(reports) == 3 and not failures,
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
