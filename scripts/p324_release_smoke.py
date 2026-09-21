from __future__ import annotations

import tempfile
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hwpx import HwpxDocument

from p324_story_layer import apply_story_layer_atomic, build_story_layer_map


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "p324-release-smoke.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.24 release story layer")
        doc.add_paragraph("body")
        doc.save_to_path(str(path))
        doc.close()

        result = apply_story_layer_atomic(
            path,
            [
                {"op": "set_story_variant", "section_index": 0, "kind": "header", "page_type": "ODD", "text": "Odd Header"},
                {"op": "set_story_variant", "section_index": 0, "kind": "header", "page_type": "EVEN", "text": "Even Header"},
                {"op": "set_page_number_variant", "section_index": 0, "target": "footer", "page_type": "ODD", "prefix": "O-"},
                {"op": "set_first_page_policy", "section_index": 0, "hide_header": True, "hide_page_number": True},
                {
                    "op": "add_section_boundary",
                    "after": 0,
                    "text": "section two",
                    "stories": [{"kind": "footer", "page_type": "BOTH", "text": "Section 2 Footer"}],
                },
            ],
            expected_revision=1,
            current_revision=1,
        )
        if not result["story_layer_changed"] or not result["section_count_changed"]:
            raise RuntimeError("story-layer transaction produced no expected change")

        reopened = HwpxDocument.open(str(path))
        reopened.close()
        mapped = build_story_layer_map(path)
        if mapped["section_count"] != 2:
            raise RuntimeError("section boundary did not survive reopen")
        first = mapped["sections"][0]
        stories = {(s["kind"], s["page_type"]): s for s in first["stories"]}
        if first["first_page_policy"] != {
            "hide_header": True,
            "hide_footer": False,
            "hide_page_number": True,
        }:
            raise RuntimeError("first-page policy did not survive reopen")
        if stories.get(("header", "ODD"), {}).get("text") != "Odd Header":
            raise RuntimeError("odd header did not survive reopen")
        if stories.get(("header", "EVEN"), {}).get("text") != "Even Header":
            raise RuntimeError("even header did not survive reopen")
        if not all(s["linkage_exact"] for s in first["stories"]):
            raise RuntimeError("story apply linkage is not exact")

    print("P3.24 release smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
