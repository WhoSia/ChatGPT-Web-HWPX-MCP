from __future__ import annotations

import tempfile
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p325_drawing_layer import apply_drawing_layer_atomic, build_drawing_layer_map


with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "p325-release-smoke.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.25 release anchor")
    doc.save_to_path(str(path))
    doc.close()

    mapped = build_document_map(path)
    anchor = next(item["locator"] for item in mapped["paragraphs"] if item.get("text") == "P3.25 release anchor")

    apply_drawing_layer_atomic(
        path,
        [{
            "op": "insert_textbox",
            "anchor": anchor,
            "text": "release drawing",
            "width": 9000,
            "height": 4500,
            "treat_as_char": False,
            "horizontal_offset": 1000,
            "vertical_offset": 700,
            "z_order": 4,
        }],
        expected_revision=1,
        current_revision=1,
    )

    drawing = build_drawing_layer_map(path)["objects"][0]
    apply_drawing_layer_atomic(
        path,
        [
            {
                "op": "set_drawing_layout",
                "drawing": drawing["locator"],
                "text_wrap": "IN_FRONT_OF_TEXT",
                "z_order": 9,
                "horizontal_offset": 1800,
                "vertical_offset": 1400,
            },
            {
                "op": "resize_drawing_object",
                "drawing": drawing["locator"],
                "width": 10000,
                "height": 5000,
            },
        ],
        expected_revision=2,
        current_revision=2,
    )

    reopened = build_drawing_layer_map(path)
    item = reopened["objects"][0]
    assert reopened["drawing_count"] == 1
    assert item["text"] == "release drawing"
    assert item["text_wrap"] == "IN_FRONT_OF_TEXT"
    assert item["z_order"] == 9
    assert item["width"] == 10000
    assert item["height"] == 5000

print("P3.25 release smoke PASS")
