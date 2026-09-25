from __future__ import annotations

import base64
import tempfile
import unittest
import zipfile

from lxml import etree
from pathlib import Path

from hwpx import HwpxDocument

import server
from p2_document import build_document_map
from p28_tables import build_table_map
from p29_objects import build_object_map
from p210_equations import build_equation_map
from p318_document_setup import build_document_setup_map
from p319_structured_publishing import build_structured_publishing_map
from p320_annotation_apparatus import build_annotation_apparatus_map
from p321_document_composer import (
    compose_document_plan,
    document_plan_contract,
    validate_document_plan,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlY4AAAAASUVORK5CYII="
)


class P321DocumentComposerTests(unittest.TestCase):
    def test_contract_and_plan_validation(self):
        contract = document_plan_contract()
        self.assertIn("table", contract["block_types"])
        self.assertIn("academic-report", contract["presets"])
        checked = validate_document_plan({
            "preset": "school-report",
            "blocks": [
                {"id": "title", "type": "title", "text": "보고서"},
                {"id": "body", "type": "paragraph", "text": "본문"},
            ],
        })
        self.assertTrue(checked["ok"])
        self.assertEqual(checked["block_count"], 2)

    def test_one_shot_mixed_document_preserves_block_order_and_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.hwpx"
            plan = {
                "preset": "school-report",
                "blocks": [
                    {"id": "title", "type": "title", "text": "전자기학 실험 보고서"},
                    {"id": "h1", "type": "heading", "level": 1, "text": "1. 실험 목적", "bookmark": "purpose"},
                    {"id": "p1", "type": "paragraph", "text": "전압과 전류의 관계를 확인한다."},
                    {"id": "l1", "type": "list_item", "list_id": "materials", "kind": "bullet", "text": "저항"},
                    {"id": "l2", "type": "list_item", "list_id": "materials", "kind": "bullet", "text": "멀티미터"},
                    {
                        "id": "tbl",
                        "type": "table",
                        "rows": 2,
                        "cols": 2,
                        "cells": [["전압", "전류"], ["3 V", "0.1 A"]],
                        "caption": "표 1. 측정값",
                    },
                    {"id": "eq", "type": "equation", "latex": "V=IR", "caption": "식 1. 옴의 법칙"},
                    {
                        "id": "pic",
                        "type": "picture",
                        "content_base64": base64.b64encode(PNG_1X1).decode("ascii"),
                        "image_format": "png",
                        "width": 7200,
                        "height": 7200,
                        "caption": "그림 1. 예시",
                    },
                    {"id": "h2", "type": "heading", "level": 1, "text": "2. 결론"},
                    {"id": "p2", "type": "paragraph", "text": "측정 결과는 선형 관계를 보였다."},
                ],
                "publishing": {
                    "toc": {"title": "목차", "level": 2},
                    "page_numbers": True,
                    "header": "전자기학 실험",
                },
                "annotations": [
                    {"op": "add_footnote", "paragraph": "$block:p1", "text": "측정은 상온에서 수행함."},
                    {"op": "add_index_mark", "paragraph": "$block:p2", "first": "옴의 법칙"},
                ],
                "post_operations": [
                    {
                        "op": "add_page_crossref",
                        "paragraph": "$block:p2",
                        "target_paragraph": "$block:h1",
                        "cached_page": 1,
                    }
                ],
            }
            receipt = compose_document_plan(
                out,
                plan,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            self.assertTrue(out.is_file())
            self.assertTrue(receipt["atomic_commit"])
            self.assertEqual(receipt["block_count"], 10)
            self.assertEqual(set(receipt["bindings"]), {
                "title", "h1", "p1", "l1", "l2", "tbl", "eq", "pic", "h2", "p2"
            })

            document = build_document_map(out)
            texts = [p["text"] for p in document["paragraphs"]]
            def first_with_prefix(prefix: str) -> int:
                return next(i for i, value in enumerate(texts) if value.startswith(prefix))

            self.assertLess(
                first_with_prefix("전자기학 실험 보고서"),
                first_with_prefix("1. 실험 목적"),
            )
            self.assertLess(
                first_with_prefix("1. 실험 목적"),
                first_with_prefix("전압과 전류의 관계를 확인한다."),
            )
            # CROSSREF contributes its cached visible page text to this
            # paragraph, so the authored body remains a prefix rather than
            # necessarily the entire paragraph text.
            self.assertLess(
                first_with_prefix("2. 결론"),
                first_with_prefix("측정 결과는 선형 관계를 보였다."),
            )

            self.assertEqual(len(build_table_map(out)["tables"]), 1)
            self.assertEqual(len(build_object_map(out)["pictures"]), 1)
            self.assertEqual(len(build_equation_map(out)["equations"]), 1)
            self.assertGreaterEqual(build_document_setup_map(out)["section_count"], 1)

            publishing = build_structured_publishing_map(out)
            self.assertGreaterEqual(publishing["toc_field_count"], 1)
            self.assertGreaterEqual(publishing["crossref_field_count"], 1)
            annotations = build_annotation_apparatus_map(out)
            self.assertEqual(annotations["counts"]["footnotes"], 1)
            self.assertEqual(annotations["counts"]["index_marks"], 1)

    def test_template_append_preserves_existing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "template.hwpx"
            doc = HwpxDocument.new()
            doc.add_paragraph("기존 템플릿 본문")
            doc.page.set_header(text="기존 머리말", section=0)
            doc.save_to_path(str(template))
            doc.close()

            out = Path(tmp) / "composed.hwpx"
            receipt = compose_document_plan(
                out,
                {
                    "blocks": [
                        {"id": "new-h", "type": "heading", "level": 1, "text": "추가 장"},
                        {"id": "new-p", "type": "paragraph", "text": "추가된 본문"},
                    ]
                },
                template_path=template,
                validator=lambda candidate: server.validate_hwpx_package(candidate),
            )
            self.assertEqual(receipt["template_mode"], "append")
            text = build_document_map(out)["text"]
            self.assertIn("기존 템플릿 본문", text)
            self.assertIn("추가 장", text)
            self.assertIn("추가된 본문", text)
            setup = build_document_setup_map(out)
            self.assertTrue(any("기존 머리말" in story["text"] for story in setup["sections"][0]["stories"]))

    def test_failure_never_replaces_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "destination.hwpx"
            doc = HwpxDocument.new()
            doc.add_paragraph("보존되어야 함")
            doc.save_to_path(str(out))
            doc.close()
            before = out.read_bytes()

            with self.assertRaises(ValueError):
                compose_document_plan(
                    out,
                    {
                        "blocks": [
                            {"id": "ok", "type": "paragraph", "text": "임시"},
                            {"id": "bad", "type": "equation", "latex": ""},
                        ]
                    },
                    validator=lambda candidate: server.validate_hwpx_package(candidate),
                )
            self.assertEqual(out.read_bytes(), before)


    def test_non_heading_blocks_do_not_inherit_outline_style_and_academic_has_heading_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "academic.hwpx"
            compose_document_plan(out, {
                "preset": "academic-report",
                "blocks": [
                    {"id": "h1", "type": "heading", "level": 1, "text": "분석 설계"},
                    {"id": "body", "type": "paragraph", "text": "본문은 제목 개요 수준을 상속하면 안 된다."},
                    {"id": "table", "type": "table", "rows": 1, "cols": 1, "cells": [["callout"]]},
                ],
            })
            with zipfile.ZipFile(out) as archive:
                header = etree.fromstring(archive.read("Contents/header.xml"))
                section = etree.fromstring(archive.read("Contents/section0.xml"))
            para_props = {
                e.get("id"): e
                for e in header.iter()
                if etree.QName(e).localname == "paraPr"
            }
            rows = {}
            for p in [e for e in section.iter() if etree.QName(e).localname == "p"]:
                text = "".join(
                    (e.text or "") for e in p.iter()
                    if etree.QName(e).localname == "t"
                ).strip()
                if text in {"분석 설계", "본문은 제목 개요 수준을 상속하면 안 된다."}:
                    rows[text] = p
            self.assertEqual(set(rows), {"분석 설계", "본문은 제목 개요 수준을 상속하면 안 된다."})
            heading_p = rows["분석 설계"]
            body_p = rows["본문은 제목 개요 수준을 상속하면 안 된다."]
            heading_prop = para_props[heading_p.get("paraPrIDRef")]
            body_prop = para_props[body_p.get("paraPrIDRef")]
            heading_meta = next(e for e in heading_prop.iter() if etree.QName(e).localname == "heading")
            body_meta = next(e for e in body_prop.iter() if etree.QName(e).localname == "heading")
            self.assertEqual(heading_meta.get("type"), "OUTLINE")
            self.assertEqual(body_meta.get("type"), "NONE")
            self.assertNotEqual(
                next(e for e in heading_p if etree.QName(e).localname == "run").get("charPrIDRef"),
                next(e for e in body_p if etree.QName(e).localname == "run").get("charPrIDRef"),
            )


if __name__ == "__main__":
    unittest.main()
