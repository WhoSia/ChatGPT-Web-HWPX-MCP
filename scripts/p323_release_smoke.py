from __future__ import annotations

import tempfile
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hwpx import HwpxDocument

from p323_advanced_tables import apply_advanced_table_edits_atomic, build_advanced_table_map


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "p323-release-smoke.hwpx"
        doc = HwpxDocument.new()
        doc.add_paragraph("P3.23 release table")
        table = doc.add_table(rows=3, cols=3)
        for r in range(3):
            for c in range(3):
                table.set_cell_text(r, c, f"{r}:{c}")
        doc.save_to_path(str(path))
        doc.close()

        before = build_advanced_table_map(path)
        mapped = before["tables"][0]
        center = next(c["locator"] for c in mapped["cells"] if c["row"] == 1 and c["col"] == 1)

        result = apply_advanced_table_edits_atomic(
            path,
            [
                {"op": "set_repeat_header", "table": mapped["locator"], "row": 0, "enabled": True},
                {"op": "set_row_properties", "table": mapped["locator"], "row": 1, "height": 2600},
                {
                    "op": "set_cell_vertical_alignment",
                    "table": mapped["locator"],
                    "cell": center,
                    "alignment": "BOTTOM",
                },
                {"op": "set_table_page_break", "table": mapped["locator"], "mode": "TABLE"},
            ],
            expected_revision=1,
            current_revision=1,
        )
        if not result["advanced_table_layout_changed"]:
            raise RuntimeError("advanced-table transaction produced no layout change")

        reopened = HwpxDocument.open(str(path))
        reopened.close()
        after = build_advanced_table_map(path)["tables"][0]
        if not after["repeat_header"] or after["page_break"] != "TABLE":
            raise RuntimeError("repeat-header/page-break state did not survive reopen")
        if not after["row_geometry"][0]["all_header"]:
            raise RuntimeError("header-row cell semantics did not survive reopen")
        if after["row_geometry"][1]["heights"] != [2600]:
            raise RuntimeError("row height did not survive reopen")
        cell = next(c for c in after["cells"] if c["row"] == 1 and c["col"] == 1)
        if cell["vertical_alignment"] != "BOTTOM":
            raise RuntimeError("vertical alignment did not survive reopen")

    print("P3.23 release smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
