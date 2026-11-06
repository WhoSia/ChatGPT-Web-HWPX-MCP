"""P4.24 opt-in HTTP PDF route and OAuth enforcement without live database."""
from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

from hwpx_mcp.delivery import p424_pdf_http as http

DOC = "doc_" + "a" * 24
EVIDENCE = "b" * 64
OWNER = "owner-test-001"
PDF = b"%PDF-1.7\n" + b"synthetic-pdf" * 14 + b"\n%%EOF\n"
SOURCE = b"PK" + b"synthetic-source" * 20
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()
SECRET = b"synthetic-test-secret-1234567890-long"
NOW = 1_800_000_000


class Documents:
    def load_revision(self, document_id, revision):
        if document_id != DOC or revision != 2:
            return None
        return {"document_id": DOC, "revision": 2, "owner_subject": OWNER,
                "sha256": SOURCE_SHA, "bytes": SOURCE,
                "expires_at_epoch": NOW + 100000}


class PDFs:
    def load_owned(self, *, evidence_id, authenticated_owner, document_store,
                   expected_document_id=None, expected_revision=None,
                   expected_source_sha256=None):
        if (evidence_id != EVIDENCE or authenticated_owner != OWNER
            or expected_document_id != DOC or expected_revision != 2
            or expected_source_sha256 != SOURCE_SHA):
            raise PermissionError("not-authorized")
        return PDF


class Auth:
    def __init__(self, subject=OWNER, scopes=("hwpx",), resource="https://example.test/mcp"):
        self.subject = subject
        self.scopes = scopes
        self.resource = resource


class Provider:
    def __init__(self, token=None):
        self.token = token
        self.seen = []

    async def load_access_token(self, credential):
        self.seen.append(credential)
        return self.token if credential == "test-authorized" else None


def core(token=None):
    provider = Provider(token)
    return SimpleNamespace(
        PUBLIC_BASE_URL="https://example.test",
        MCP_RESOURCE_URL="https://example.test/mcp",
        SUBJECT=OWNER,
        HWPX_SCOPE="hwpx",
        OAUTH_PROVIDER=provider,
        DOCUMENT_STORE=Documents(),
        _download_secret=lambda: SECRET,
        _caller_subject=lambda: OWNER,
        _paths=lambda identity: identity if identity == DOC else ValueError("wrong doc"),
    )


def request(url, authorization=None, document_id=DOC):
    parsed = urlsplit(url)
    qs = {key: value[0] for key, value in parse_qs(parsed.query).items()}
    return SimpleNamespace(
        headers={"authorization": authorization} if authorization is not None else {},
        path_params={"document_id": document_id},
        query_params=qs,
    )


class FeatureGateTests(TestCase):
    def test_disabled_tool_does_not_open_database(self):
        c = core()
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "NO"}), patch.object(http, "_store") as store:
            result = http.issue_authenticated_pdf_link(c, document_id=DOC, revision=2,
                                                       evidence_id=EVIDENCE)
            self.assertEqual(result["code"], "P424_NATIVE_PDF_DELIVERY_DISABLED")
            store.assert_not_called()

    def test_enabled_tool_issues_authenticated_link_not_bearer_only(self):
        c = core()
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "YES"}), patch.object(http, "_store", return_value=PDFs()), patch("hwpx_mcp.delivery.p424_pdf_delivery.time.time", return_value=NOW):
            result = http.issue_authenticated_pdf_link(
                c, document_id=DOC, revision=2, evidence_id=EVIDENCE
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["download_authentication"], "OAUTH_BEARER_HEADER_REQUIRED")
        self.assertFalse(result["browser_link_without_oauth_header_supported"])


class HttpRouteTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.token = Auth()
        self.c = core(self.token)
        from hwpx_mcp.delivery.p424_pdf_delivery import issue_pdf_delivery
        self.url = issue_pdf_delivery(
            pdf_store=PDFs(), document_store=self.c.DOCUMENT_STORE,
            authenticated_owner=OWNER, document_id=DOC, revision=2,
            evidence_id=EVIDENCE, secret=SECRET,
            public_base_url="https://example.test", now=NOW,
        )["download_url"]

    async def get(self, authorization=None, token=None, url=None):
        if token is not None:
            self.c.OAUTH_PROVIDER.token = token
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "YES"}), patch.object(http, "_store", return_value=PDFs()), patch("hwpx_mcp.delivery.p424_pdf_delivery.time.time", return_value=NOW + 2):
            return await http.download_authenticated_pdf(
                self.c, request(url or self.url, authorization),
            )

    async def test_missing_bearer_denied_without_db_query(self):
        with patch.object(http, "_store") as store:
            response = await self.get()
            self.assertEqual(response.status_code, 401)
            store.assert_not_called()

    async def test_invalid_bearer_denied(self):
        response = await self.get("Bearer invalid")
        self.assertEqual(response.status_code, 401)

    async def test_wrong_scope_subject_or_resource_denied(self):
        for token in [Auth(scopes=()), Auth(subject="other-owner"), Auth(resource="https://evil.test/mcp")]:
            response = await self.get("Bearer test-authorized", token=token)
            self.assertEqual(response.status_code, 401)

    async def test_valid_bearer_returns_pdf_and_no_store_headers(self):
        response = await self.get("Bearer test-authorized", token=Auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, PDF)
        self.assertEqual(response.headers.get("cache-control"), "private, no-store")
        self.assertEqual(response.headers.get("content-type"), "application/pdf")

    async def test_tampered_link_refused(self):
        response = await self.get("Bearer test-authorized", token=Auth(), url=self.url.replace("sha=", "sha=9"))
        self.assertEqual(response.status_code, 404)

    async def test_disabled_http_route_never_checks_auth(self):
        with patch.dict(os.environ, {"P424_NATIVE_PDF_DELIVERY_ENABLED": "NO"}):
            result = await http.download_authenticated_pdf(
                self.c, request(self.url, "Bearer test-authorized")
            )
            self.assertEqual(result.status_code, 503)
            self.assertFalse(self.c.OAUTH_PROVIDER.seen)
