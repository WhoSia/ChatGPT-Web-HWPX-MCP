#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hwpx import HwpxDocument

from p2_document import build_document_map
from p322_review_workflow import apply_review_workflow_atomic, build_review_workflow_map


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paragraph_locator(path: Path, text: str) -> str:
    return next(
        item["locator"]
        for item in build_document_map(path)["paragraphs"]
        if item["text"] == text
    )


CASES = [
    {
        "id": "insert-accept",
        "kind": "resolution",
        "op": "tracked_insert",
        "action": "ACCEPT_ALL",
        "base": "alpha base",
        "payload": {"text": " +inserted"},
        "expected_after": "alpha base +inserted",
    },
    {
        "id": "insert-reject",
        "kind": "resolution",
        "op": "tracked_insert",
        "action": "REJECT_ALL",
        "base": "alpha base",
        "payload": {"text": " +inserted"},
        "expected_after": "alpha base",
    },
    {
        "id": "delete-accept",
        "kind": "resolution",
        "op": "tracked_delete",
        "action": "ACCEPT_ALL",
        "base": "beta remove target",
        "payload": {"match": "remove "},
        "expected_after": "beta target",
    },
    {
        "id": "delete-reject",
        "kind": "resolution",
        "op": "tracked_delete",
        "action": "REJECT_ALL",
        "base": "beta remove target",
        "payload": {"match": "remove "},
        "expected_after": "beta remove target",
    },
    {
        "id": "replace-accept",
        "kind": "resolution",
        "op": "tracked_replace",
        "action": "ACCEPT_ALL",
        "base": "gamma old value",
        "payload": {"old": "old", "new": "new"},
        "expected_after": "gamma new value",
    },
    {
        "id": "replace-reject",
        "kind": "resolution",
        "op": "tracked_replace",
        "action": "REJECT_ALL",
        "base": "gamma old value",
        "payload": {"old": "old", "new": "new"},
        "expected_after": "gamma old value",
    },
    {
        "id": "protection-enable",
        "kind": "protection",
        "op": "tracked_insert",
        "action": "ENABLE_TRACK_CHANGE_PROTECTION",
        "base": "delta protected base",
        "payload": {"text": " +protected"},
        "test_password": "P334R2!",
        "expected_after": None,
    },
]


def build_case(root: Path, spec: dict) -> dict:
    d = root / spec["id"]
    d.mkdir(parents=True, exist_ok=True)
    source = d / "source.hwpx"
    target = d / "target.hwpx"

    doc = HwpxDocument.new()
    doc.add_paragraph("P3.34-R2 tracked-change native evidence")
    doc.add_paragraph(spec["base"])
    doc.save_to_path(str(source))
    doc.close()

    loc = paragraph_locator(source, spec["base"])
    operation = {
        "op": spec["op"],
        "paragraph": loc,
        "author": "P3.34-R2 Probe",
        "date": "2026-09-23T12:00:00Z",
        **spec["payload"],
    }
    apply_review_workflow_atomic(
        source,
        [operation],
        expected_revision=1,
        current_revision=1,
    )
    target.write_bytes(source.read_bytes())

    mapped = build_review_workflow_map(source)
    item = {
        **spec,
        "source": str(source),
        "target": str(target),
        "source_sha256": sha256(source),
        "before_review": {
            "counts": mapped["counts"],
            "tracked_changes": mapped["tracked_changes"],
            "track_change_authors": mapped["track_change_authors"],
        },
    }
    (d / "case.json").write_text(
        json.dumps(item, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return item


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/p334r2-tracked-resolution-pack")
    args = ap.parse_args()
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r2/native-resolution-capture/v1",
        "phase": "P3.34-R2",
        "authority": "EVIDENCE_ONLY_NO_RESOLUTION_MUTATION_AUTHORITY",
        "cases": [build_case(root, spec) for spec in CASES],
    }
    (root / "capture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"P3.34-R2 materialized {len(manifest['cases'])} tracked-change native fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
