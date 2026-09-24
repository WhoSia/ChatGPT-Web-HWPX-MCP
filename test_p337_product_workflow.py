from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hwpx import HwpxDocument

import server as core
import server_p2 as api
from p2_document import build_document_map
from p337_product_workflow import (
    HWP5_CFBF_MAGIC,
    fill_template_atomic,
    plan_literal_placeholder_fill,
    product_workflow_contract,
    sniff_hangul_payload,
)


class MemoryRevisions:
    mode = "test-memory"

    def __init__(self):
        self.rows = {}

    def put_revision(self, **kwargs):
        doc_id, revision = kwargs["document_id"], int(kwargs["revision"])
        current = self.load_current(doc_id)
        if (
            current
            and revision == current["revision"]
            and hashlib.sha256(kwargs["data"]).hexdigest() == current["sha256"]
        ):
            return {"revision": revision, "idempotent_replay": True}
        if int(kwargs["expected_revision"]) != (current["revision"] if current else 0):
            raise RuntimeError("Revision CAS conflict")
        self.rows[(doc_id, revision)] = {
            "document_id": doc_id,
            "revision": revision,
            "metadata": copy.deepcopy(kwargs["metadata"]),
            "bytes": bytes(kwargs["data"]),
            "sha256": hashlib.sha256(kwargs["data"]).hexdigest(),
            "owner_subject": kwargs["owner_subject"],
            "expires_at_epoch": kwargs["expires_at_epoch"],
        }
        return {"revision": revision}

    def load_current(self, doc_id, **kwargs):
        rows = [row for (key, _), row in self.rows.items() if key == doc_id]
        return copy.deepcopy(max(rows, key=lambda row: row["revision"])) if rows else None

    def load_revision(self, doc_id, revision):
        return copy.deepcopy(self.rows.get((doc_id, int(revision))))

    def cleanup_expired(self):
        return 0

    def delete_document(self, doc_id):
        keys = [key for key in self.rows if key[0] == doc_id]
        for key in keys:
            del self.rows[key]
        return bool(keys)


class P337ProductWorkflowTests(unittest.TestCase):
    def test_sniff_bytes_not_extension(self):
        mismatch = sniff_hangul_payload(HWP5_CFBF_MAGIC + b"legacy", "mislabel.hwpx")
        self.assertEqual(mismatch["actual_format"], "HWP5")
        self.assertTrue(mismatch["format_mismatch"])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "real.hwpx"
            doc = HwpxDocument.new()
            doc.add_paragraph("native")
            doc.save_to_path(str(path))
            doc.close()
            sniffed = sniff_hangul_payload(path.read_bytes(), "wrong.hwp")
            self.assertEqual(sniffed["actual_format"], "HWPX")
            self.assertTrue(sniffed["format_mismatch"])

    def test_literal_template_fill_is_atomic_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "template.hwpx"
            destination = Path(tmp) / "filled.hwpx"
            doc = HwpxDocument.new()
            doc.add_paragraph("성명: {{name}} / 소속: {{org}}")
            doc.save_to_path(str(source))
            doc.close()
            before = source.read_bytes()
            planned = plan_literal_placeholder_fill(
                source,
                {"{{name}}": "김우준", "{{org}}": "연구팀"},
            )
            self.assertEqual(planned["operation_count"], 2)
            receipt = fill_template_atomic(
                source,
                destination,
                {"{{name}}": "김우준", "{{org}}": "연구팀"},
                validator=lambda path: core.validate_hwpx_package(path),
            )
            self.assertTrue(receipt["atomic_commit"])
            self.assertEqual(source.read_bytes(), before)
            text = build_document_map(destination)["text"]
            self.assertIn("김우준", text)
            self.assertIn("연구팀", text)
            self.assertNotIn("{{name}}", text)

    def test_contract_is_narrow_product_surface(self):
        contract = product_workflow_contract()
        self.assertEqual(contract["phase"], "P3.37")
        self.assertEqual(len(contract["primary_tools"]), 4)
        self.assertIn("create_and_deliver_document", contract["primary_tools"])

    def test_server_product_create_and_template_fill_return_resource_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryRevisions()
            patches = [
                patch.object(core, "OBJECT_DIR", Path(tmp)),
                patch.object(core, "DOCUMENT_STORE", store),
                patch.object(core, "DOWNLOAD_SECRET", "p337-test-secret"),
                patch.object(core, "_caller_subject", return_value="owner"),
            ]
            for item in patches:
                item.start()
                self.addCleanup(item.stop)

            created = api.create_and_deliver_document(
                {
                    "preset": "school-report",
                    "blocks": [
                        {"type": "title", "text": "P3.37 실제 파일"},
                        {"type": "paragraph", "text": "성명: {{name}}"},
                    ],
                },
                filename="product.hwpx",
                request_id="p337-create",
                design_mode="",
            )
            receipt = created.structured_content
            self.assertEqual(receipt["phase"], "P3.37")
            self.assertEqual(receipt["delivery_status"], "READY_FOR_DOWNLOAD")
            self.assertIn("/deliveries/", receipt["download_url"])
            template_id = receipt["document_id"]

            filled = api.fill_template_and_deliver(
                template_id,
                {"{{name}}": "김우준"},
                filename="filled.hwpx",
                request_id="p337-fill",
                require_unique=True,
            )
            filled_receipt = filled.structured_content
            self.assertNotEqual(filled_receipt["document_id"], template_id)
            self.assertEqual(filled_receipt["delivery_status"], "READY_FOR_DOWNLOAD")
            self.assertIn("/deliveries/", filled_receipt["download_url"])
            mapped = api.get_document_map(filled_receipt["document_id"])
            self.assertIn("성명: 김우준", mapped["paragraphs"][-1]["text"])
            original = api.get_document_map(template_id)
            self.assertIn("{{name}}", original["paragraphs"][-1]["text"])


if __name__ == "__main__":
    unittest.main()
