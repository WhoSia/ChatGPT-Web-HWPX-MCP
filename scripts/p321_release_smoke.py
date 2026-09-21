from __future__ import annotations

import tempfile
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p28_tables import build_table_map
from p210_equations import build_equation_map
from p321_document_composer import compose_document_plan


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "p321-release-smoke.hwpx"
        receipt = compose_document_plan(
            target,
            {
                "preset": "default",
                "blocks": [
                    {"id": "h1", "type": "heading", "level": 1, "text": "P3.21 release smoke"},
                    {"id": "p1", "type": "paragraph", "text": "one-shot composition"},
                    {
                        "id": "t1",
                        "type": "table",
                        "rows": 2,
                        "cols": 2,
                        "cells": [["A", "B"], ["1", "2"]],
                    },
                    {"id": "e1", "type": "equation", "latex": "x=1"},
                ],
            },
            validator=None,
        )
        if not target.is_file() or not receipt.get("atomic_commit"):
            raise RuntimeError("P3.21 composition did not commit a target package")

        document = HwpxDocument.open(str(target))
        document.close()

        mapped = build_document_map(target)
        if "P3.21 release smoke" not in mapped["text"]:
            raise RuntimeError("P3.21 heading missing after reopen")
        if len(build_table_map(target)["tables"]) != 1:
            raise RuntimeError("P3.21 table missing after reopen")
        if len(build_equation_map(target)["equations"]) != 1:
            raise RuntimeError("P3.21 equation missing after reopen")

    print("P3.21 release smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
