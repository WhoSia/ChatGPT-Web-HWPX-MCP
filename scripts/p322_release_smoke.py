from __future__ import annotations

import tempfile
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p322_review_workflow import apply_review_workflow_atomic, build_review_workflow_map


def locator(path: Path, text: str) -> str:
    return next(
        item["locator"]
        for item in build_document_map(path)["paragraphs"]
        if item["text"] == text
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "p322-release-smoke.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.22 release review")
        doc.add_paragraph("alpha review target")
        doc.add_paragraph("beta form target")
        doc.save_to_path(str(path))
        doc.close()

        alpha = locator(path, "alpha review target")
        beta = locator(path, "beta form target")
        result = apply_review_workflow_atomic(
            path,
            [
                {
                    "op": "tracked_replace",
                    "paragraph": alpha,
                    "old": "review",
                    "new": "revision",
                    "author": "Release Smoke",
                },
                {
                    "op": "add_form_field",
                    "paragraph": beta,
                    "name": "reviewer",
                    "prompt": "검토자",
                },
                {
                    "op": "add_check_box",
                    "paragraph": beta,
                    "caption": "검토 완료",
                    "name": "done",
                    "checked": True,
                },
                {
                    "op": "add_highlight",
                    "paragraph": alpha,
                    "match": "alpha",
                    "color": "#FFFF00",
                },
                {
                    "op": "set_document_metadata",
                    "title": "P3.22 Release Smoke",
                    "creator": "ChatGPT Web HWPX MCP",
                },
            ],
            expected_revision=1,
            current_revision=1,
        )
        if not result["changed"]:
            raise RuntimeError("review transaction produced no structural change")

        reopened = HwpxDocument.open(str(path))
        reopened.close()
        mapped = build_review_workflow_map(path)
        if mapped["counts"]["tracked_changes"] != 2:
            raise RuntimeError("tracked replace did not survive reopen")
        if mapped["counts"]["form_fields"] != 1:
            raise RuntimeError("form field did not survive reopen")
        if mapped["counts"]["check_boxes"] != 1 or not mapped["check_boxes"][0]["checked"]:
            raise RuntimeError("checkbox did not survive reopen")
        if mapped["counts"]["highlights"] != 1:
            raise RuntimeError("highlight did not survive reopen")
        if not mapped["metadata"] or mapped["metadata"]["title"] != "P3.22 Release Smoke":
            raise RuntimeError("document metadata did not survive reopen")

    print("P3.22 release smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
