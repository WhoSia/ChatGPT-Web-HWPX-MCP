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

import server
from p2_document import build_document_map
from p322_review_workflow import apply_review_workflow_atomic, build_review_workflow_map


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locator(path: Path, text: str) -> str:
    return next(
        item["locator"]
        for item in build_document_map(path)["paragraphs"]
        if item["text"] == text
    )


CASES = [
    {
        "id": "candidate-insert-accept",
        "base": "alpha base",
        "author_op": {"op": "tracked_insert", "text": " +inserted"},
        "resolution_op": "accept_all_tracked_changes",
        "expected": "alpha base +inserted",
    },
    {
        "id": "candidate-delete-reject",
        "base": "beta remove target",
        "author_op": {"op": "tracked_delete", "match": "remove "},
        "resolution_op": "reject_all_tracked_changes",
        "expected": "beta remove target",
    },
    {
        "id": "candidate-replace-accept",
        "base": "gamma old value",
        "author_op": {"op": "tracked_replace", "old": "old", "new": "new"},
        "resolution_op": "accept_all_tracked_changes",
        "expected": "gamma new value",
    },
    {
        "id": "candidate-replace-reject",
        "base": "gamma old value",
        "author_op": {"op": "tracked_replace", "old": "old", "new": "new"},
        "resolution_op": "reject_all_tracked_changes",
        "expected": "gamma old value",
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/p334r2-candidate-roundtrip-pack")
    args = ap.parse_args()
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r2/candidate-roundtrip/v1",
        "phase": "P3.34-R2",
        "authority": "CANDIDATE_UNPROTECTED_ACCEPT_REJECT_ALL",
        "cases": [],
    }

    for spec in CASES:
        d = root / spec["id"]
        d.mkdir(parents=True, exist_ok=True)
        before = d / "candidate-before-hancom.hwpx"
        after = d / "candidate-after-hancom.hwpx"
        if after.exists():
            after.unlink()

        doc = HwpxDocument.new()
        doc.add_paragraph("P3.34-R2 implementation-generated resolution")
        doc.add_paragraph(spec["base"])
        doc.save_to_path(str(before))
        doc.close()

        paragraph = locator(before, spec["base"])
        author_op = {
            **spec["author_op"],
            "paragraph": paragraph,
            "author": "P3.34-R2 Candidate",
            "date": "2026-09-23T15:00:00Z",
        }
        apply_review_workflow_atomic(
            before,
            [author_op],
            expected_revision=1,
            current_revision=1,
            validator=server.validate_hwpx_package,
        )
        resolution = apply_review_workflow_atomic(
            before,
            [{"op": spec["resolution_op"]}],
            expected_revision=2,
            current_revision=2,
            validator=server.validate_hwpx_package,
        )
        mapped = build_review_workflow_map(before)
        body = [
            item["text"]
            for item in build_document_map(before)["paragraphs"]
            if item.get("body_paragraph_index") is not None
        ]
        if mapped["counts"]["tracked_changes"] != 0 or mapped["counts"]["track_change_authors"] != 0:
            raise RuntimeError(f"{spec['id']}: candidate retained tracked metadata")
        if spec["expected"] not in body:
            raise RuntimeError(f"{spec['id']}: candidate final text mismatch")
        if not server.validate_hwpx_package(before).get("ok", False):
            raise RuntimeError(f"{spec['id']}: package validation failed")

        item = {
            **spec,
            "candidate_sha256": sha(before),
            "candidate_counts": mapped["counts"],
            "candidate_body_text": body,
            "resolution_receipt": resolution,
            "user_action_ko": "한컴에서 열고 아무것도 수정하지 않은 채 Ctrl+S로 저장한 뒤 창을 닫으세요.",
        }
        (d / "case.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest["cases"].append(item)

    (root / "roundtrip-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"P3.34-R2 materialized {len(manifest['cases'])} resolution round-trip candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
