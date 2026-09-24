from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hwpx import HwpxDocument

import server
from p2_document import build_document_map
from p321_document_composer import compose_document_plan
from p337_product_workflow import (
    fill_template_atomic,
    product_workflow_contract,
    sniff_hangul_payload,
)


with tempfile.TemporaryDirectory(prefix="p337-") as tmp:
    root = Path(tmp)
    generated = root / "generated.hwpx"
    compose_document_plan(
        generated,
        {
            "preset": "polished-report",
            "blocks": [
                {"type": "title", "text": "P3.37 Product Smoke"},
                {"type": "heading", "level": 1, "text": "1. 목적"},
                {"type": "paragraph", "text": "실제 HWPX 파일 생성과 전달 경로를 검증한다."},
            ],
        },
        validator=lambda candidate: server.validate_hwpx_package(candidate),
    )
    sniffed = sniff_hangul_payload(generated.read_bytes(), "generated.hwpx")
    assert sniffed["actual_format"] == "HWPX"

    template = root / "template.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("이름={{name}}")
    doc.save_to_path(str(template))
    doc.close()
    filled = root / "filled.hwpx"
    receipt = fill_template_atomic(
        template,
        filled,
        {"{{name}}": "P3.37"},
        validator=lambda candidate: server.validate_hwpx_package(candidate),
    )
    assert receipt["atomic_commit"]
    assert "이름=P3.37" in build_document_map(filled)["text"]

contract = product_workflow_contract()
print(json.dumps({
    "status": "PASS",
    "phase": contract["phase"],
    "primary_tools": contract["primary_tools"],
    "sniff": "HWPX",
    "template_fill": "PASS",
}, ensure_ascii=False))
