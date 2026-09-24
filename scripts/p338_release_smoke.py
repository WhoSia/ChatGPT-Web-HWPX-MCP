from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hwpx import HwpxDocument

from p2_document import build_document_map
from p28_tables import build_table_map
from p321_document_composer import compose_document_plan
from p338_rich_builder import (
    compile_rich_document_plan,
    evaluate_preview_readiness,
    intelligent_fill_atomic,
    rich_builder_contract,
)


with tempfile.TemporaryDirectory(prefix="p338-") as tmp:
    root = Path(tmp)
    generated = root / "rich.hwpx"
    compiled = compile_rich_document_plan({
        "preset": "polished-report",
        "sections": [
            {
                "page": {"paper_size": "A4", "orientation": "PORTRAIT"},
                "header": "P3.38",
                "page_numbers": True,
                "blocks": [
                    {"id": "title", "type": "title", "text": "P3.38 Rich Builder"},
                    {"id": "heading", "type": "heading", "level": 1, "text": "Overview"},
                    {"id": "body", "type": "paragraph", "text": "Native rich authoring smoke."},
                    {
                        "id": "table",
                        "type": "table",
                        "rows": 2,
                        "cols": 2,
                        "first_row_header": True,
                        "cells": [["항목", "값"], ["상태", "PASS"]],
                    },
                    {"id": "equation", "type": "equation", "latex": "x^2=1"},
                ],
            },
            {
                "page": {"paper_size": "A4", "orientation": "LANDSCAPE"},
                "blocks": [
                    {"id": "appendix", "type": "heading", "level": 1, "text": "Appendix"},
                    {"id": "appendix-body", "type": "paragraph", "text": "Second section."},
                ],
            },
        ],
    })
    compose_document_plan(generated, compiled["plan"])
    preview = evaluate_preview_readiness(generated)
    assert preview["verdict"] in {"PASS", "PASS_WITH_WARNINGS"}
    assert preview["render_status"] == "NOT_RENDERED"
    assert preview["section_count"] == 2

    template = root / "template.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("담당자={{name}}")
    table = doc.add_table(rows=1, cols=2)
    table.set_cell_text(0, 0, "학교")
    table.set_cell_text(0, 1, "")
    doc.save_to_path(str(template))
    doc.close()

    filled = root / "filled.hwpx"
    fill = intelligent_fill_atomic(
        template,
        filled,
        {"name": "P3.38", "학교": "창원과학고"},
    )
    assert fill["atomic_commit"]
    assert "담당자=P3.38" in build_document_map(filled)["text"]
    table_map = build_table_map(filled)
    assert any(
        cell["text"] == "창원과학고"
        for cell in table_map["tables"][0]["cells"]
    )

contract = rich_builder_contract()
assert contract["phase"] == "P3.38"
print("P3.38 rich multi-section + smart-fill + static-preview smoke PASS")
