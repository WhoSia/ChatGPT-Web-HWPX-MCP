"""P4.26 real HWPX bytes -> MCP ResourceLink -> signed HTTP download.

Runs without importing server.py or requiring PostgreSQL: synthetic native
documents, mock revision store, actual p333 handoff and HTTP handler.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from starlette.requests import Request

from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.delivery.p333_file_delivery import (
    MIME, download_revision, export_revision, handoff,
)

DOC = "doc_" + "a" * 24
OWNER = "owner-synthetic-p426"


class NativeDownloadRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p426-native-download-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "original.hwpx"
        compose_document_plan(self.path, {
            "preset": "academic-report",
            "blocks": [
                {"type": "title", "text": "실제 한글 첨부 시험"},
                {"type": "paragraph", "text": "전달 후 원래 문서와 같아야 한다."},
                {"type": "equation", "latex": "V=IR"},
            ],
        })
        self.raw = self.path.read_bytes()
        sha = hashlib.sha256(self.raw).hexdigest()
        self.row = {
            "owner_subject": OWNER, "revision": 1,
            "sha256": sha, "bytes": self.raw,
            "metadata": {"filename": "전기회로 실험 결과.hwpx"},
            "expires_at_epoch": int(time.time()) + 3600,
        }
        self.core = SimpleNamespace(
            _paths=lambda document_id: (document_id, None),
            _caller_subject=lambda: OWNER,
            _download_secret=lambda: b"synthetic-test-secret" * 3,
            _utc_iso=lambda epoch: datetime.fromtimestamp(
                epoch, tz=timezone.utc).isoformat(),
            sanitize_filename=lambda name: name,
            validate_hwpx_package=lambda path, ingress=False: {
                "valid": True,
                "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            },
            PUBLIC_BASE_URL="https://files.example.invalid",
            DOC_ID_RE=re.compile(r"doc_[a-f0-9]{24}"),
            DOCUMENT_STORE=SimpleNamespace(
                load_current=lambda doc: self.row,
                load_revision=lambda doc, rev: self.row if rev == 1 else None,
            ),
        )

    def _download(self, url):
        parsed = urlsplit(url)
        request = Request({
            "type": "http", "method": "GET", "path": parsed.path,
            "query_string": parsed.query.encode(),
            "headers": [],
            "path_params": {"document_id": DOC},
        })
        return asyncio.run(download_revision(self.core, request))

    def test_real_native_hwpx_handoff_http_and_byte_for_byte_reingest(self):
        receipt = export_revision(self.core, DOC)
        output = handoff(receipt)
        self.assertFalse(output.is_error)
        resource = [c for c in output.content if c.type == "resource_link"]
        self.assertEqual(len(resource), 1)
        self.assertEqual(resource[0].mimeType, MIME)
        self.assertEqual(resource[0].name, "전기회로 실험 결과.hwpx")
        self.assertEqual(resource[0].uri, receipt["download_url"])
        self.assertEqual(output.structured_content["host_attachment_status"], "NOT_OBSERVED")
        resp = self._download(resource[0].uri)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.body, self.raw)
        self.assertIn("attachment; filename*=UTF-8''", resp.headers["content-disposition"])
        self.assertEqual(resp.media_type, MIME)
        self.assertEqual(hashlib.sha256(resp.body).hexdigest(), receipt["sha256"])

    def test_reissued_download_preserves_document_revision_and_bytes(self):
        first = export_revision(self.core, DOC)
        second = export_revision(self.core, DOC)
        self.assertEqual(first["document_id"], second["document_id"])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(self._download(second["download_url"]).body, self.raw)

    def test_corrupted_link_does_not_turn_into_attachment(self):
        receipt = export_revision(self.core, DOC)
        response = self._download(receipt["download_url"].replace("rev=1", "rev=2"))
        self.assertNotEqual(response.status_code, 200)

    def test_host_display_remains_unverified_even_if_http_download_passes(self):
        result = handoff(export_revision(self.core, DOC))
        self.assertEqual(result.structured_content["host_attachment_status"], "NOT_OBSERVED")


if __name__ == "__main__":
    unittest.main()
