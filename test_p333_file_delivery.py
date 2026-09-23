from __future__ import annotations

import asyncio
import copy
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from starlette.requests import Request

import server as core
import server_p2 as api
from p333_file_delivery import delivery_contract, download_revision, handoff


class MemoryRevisions:
    """Test double only; production continues to use encrypted Postgres custody."""
    mode = "test-memory"

    def __init__(self):
        self.rows = {}

    def put_revision(self, **kwargs):
        doc_id, revision = kwargs["document_id"], kwargs["revision"]
        current = self.load_current(doc_id)
        if current and revision == current["revision"] and hashlib.sha256(kwargs["data"]).hexdigest() == current["sha256"]:
            return {"revision": revision, "idempotent_replay": True}
        if kwargs["expected_revision"] != (current["revision"] if current else 0):
            raise RuntimeError("Revision CAS conflict")
        self.rows[(doc_id, revision)] = {
            "document_id": doc_id, "revision": revision, "metadata": copy.deepcopy(kwargs["metadata"]),
            "bytes": kwargs["data"], "sha256": hashlib.sha256(kwargs["data"]).hexdigest(),
            "owner_subject": kwargs["owner_subject"], "expires_at_epoch": kwargs["expires_at_epoch"],
        }
        return {"revision": revision}

    def load_current(self, doc_id, **kwargs):
        rows = [v for (key, _), v in self.rows.items() if key == doc_id]
        return copy.deepcopy(max(rows, key=lambda r: r["revision"])) if rows else None

    def load_revision(self, doc_id, revision):
        return copy.deepcopy(self.rows.get((doc_id, revision)))

    def cleanup_expired(self):
        return 0

    def delete_document(self, doc_id):
        keys = [k for k in self.rows if k[0] == doc_id]
        for key in keys:
            del self.rows[key]
        return bool(keys)


class FileDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = MemoryRevisions()
        for name, value in {"OBJECT_DIR": Path(self.tmp.name), "DOCUMENT_STORE": self.store,
                            "DOWNLOAD_SECRET": "test-only-secret-not-production",
                            "_caller_subject": lambda: "owner"}.items():
            p = patch.object(core, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.plan = {"preset": "school-report", "blocks": [
            {"id": "title", "type": "title", "text": "파일 전달 검증"},
            {"id": "body", "type": "paragraph", "text": "첫 번째 본문"},
        ]}

    def generate(self):
        return api.generate_document(self.plan, "전달 결과.hwpx", "delivery-test").structured_content

    def download(self, url):
        parsed = urlsplit(url)
        request = Request({"type": "http", "method": "GET", "path": parsed.path,
                           "query_string": parsed.query.encode(), "headers": [],
                           "path_params": {"document_id": parsed.path.rsplit("/", 1)[-1]}})
        return asyncio.run(download_revision(core, request))

    def test_generate_handoff_download_reingest_and_replay(self):
        receipt = self.generate()
        replay = self.generate()
        self.assertEqual(receipt["document_id"], replay["document_id"])
        self.assertEqual(len(self.store.rows), 1)
        result = handoff(receipt).model_dump(by_alias=True, mode="json")
        self.assertEqual(result["content"][1]["type"], "resource_link")
        self.assertEqual(result["content"][1]["mimeType"], "application/hwp+zip")
        response = self.download(receipt["download_url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(hashlib.sha256(response.body).hexdigest(), receipt["sha256"])
        self.assertIn("attachment; filename*=UTF-8''", response.headers["content-disposition"])
        path = Path(self.tmp.name) / "reingested.hwpx"
        path.write_bytes(response.body)
        self.assertTrue(core.validate_hwpx_package(path, ingress=True)["valid"])

    def test_edit_and_old_link_keeps_exact_revision(self):
        first = self.generate()
        mapped = api.get_document_map(first["document_id"])
        target = next(p["locator"] for p in mapped["paragraphs"] if p["text"] == "첫 번째 본문")
        result = api.edit_document_and_deliver(first["document_id"], 1,
                    [{"op": "replace_paragraph_text", "target": target, "text": "수정한 본문"}])
        second = result.structured_content
        self.assertEqual(second["revision"], 2)
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertEqual(hashlib.sha256(self.download(first["download_url"]).body).hexdigest(), first["sha256"])
        self.assertEqual(hashlib.sha256(self.download(second["download_url"]).body).hexdigest(), second["sha256"])
        with self.assertRaises(Exception):
            api.edit_document_and_deliver(first["document_id"], 1, [])
        self.assertEqual(self.store.load_current(first["document_id"])["revision"], 2)

    def test_link_tamper_expiry_deletion_and_owner(self):
        receipt = self.generate()
        url = receipt["download_url"]
        self.assertEqual(self.download(url.replace("rev=1", "rev=2")).status_code, 403)
        with patch("p333_file_delivery.time.time", return_value=time.time() + 1000):
            self.assertEqual(self.download(url).status_code, 410)
        with patch.object(core, "_caller_subject", return_value="other"):
            with self.assertRaises(PermissionError):
                api.deliver_document(receipt["document_id"])
        self.store.delete_document(receipt["document_id"])
        self.assertEqual(self.download(url).status_code, 404)

    def test_invalid_plan_and_edit_do_not_commit(self):
        with self.assertRaises(Exception):
            api.generate_document({"blocks": [{"type": "invented"}]})
        self.assertEqual(self.store.rows, {})
        receipt = self.generate()
        with self.assertRaises(Exception):
            api.edit_document_and_deliver(receipt["document_id"], 1, [{"op": "invented"}])
        self.assertEqual(self.store.load_current(receipt["document_id"])["sha256"], receipt["sha256"])

    def test_handoff_failure_retains_commit_and_can_recover(self):
        with patch.object(api, "export_revision", side_effect=RuntimeError("temporary")):
            result = api.generate_document(self.plan, request_id="recovery")
        self.assertTrue(result.is_error)
        receipt = result.structured_content
        self.assertEqual(receipt["transaction"], "COMMITTED")
        self.assertEqual(receipt["delivery_status"], "RETRY_DELIVERY_ONLY")
        recovered = api.deliver_document(receipt["document_id"], receipt["revision"])
        self.assertFalse(recovered.is_error)
        self.assertEqual(len(self.store.rows), 1)

    def test_integrity_and_configuration_fail_closed(self):
        with patch.object(core, "DOWNLOAD_SECRET", ""):
            with self.assertRaises(RuntimeError):
                self.generate()
        self.assertEqual(self.store.rows, {})
        receipt = self.generate()
        self.store.rows[(receipt["document_id"], 1)]["bytes"] = b"broken"
        with self.assertRaises(ValueError):
            api.deliver_document(receipt["document_id"])
        self.assertEqual(self.download(receipt["download_url"]).status_code, 409)

    def test_primary_workflow_does_not_promote_rare_or_visual_authority(self):
        gates = delivery_contract()["evidence_gates"]
        self.assertEqual(gates["rare_features"]["status"], "EVIDENCE_GATE_CLOSED")
        self.assertEqual(self.generate()["host_attachment_status"], "NOT_OBSERVED")


if __name__ == "__main__":
    unittest.main()
