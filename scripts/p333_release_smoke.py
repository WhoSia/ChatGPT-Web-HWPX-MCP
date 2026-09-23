"""Database-independent image gate for composition-to-file handoff."""
import asyncio
import hashlib
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from p321_document_composer import compose_document_plan
from p333_file_delivery import export_revision, handoff, download_revision
from starlette.requests import Request

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "delivery.hwpx"
    compose_document_plan(path, {"blocks": [{"type": "paragraph", "text": "P3.33 file delivery"}]})
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    row = {"revision": 1, "bytes": raw, "sha256": digest, "owner_subject": "smoke",
           "expires_at_epoch": time.time() + 3600, "metadata": {"filename": "delivery.hwpx"}}
    core = SimpleNamespace(
        _paths=lambda doc: None, _caller_subject=lambda: "smoke", _download_secret=lambda: b"smoke-only",
        DOCUMENT_STORE=SimpleNamespace(load_current=lambda doc: row, load_revision=lambda doc, rev: row),
        validate_hwpx_package=lambda path, **kw: {"valid": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
        sanitize_filename=lambda name: name, _utc_iso=lambda epoch: str(epoch),
        PUBLIC_BASE_URL="http://127.0.0.1", DOC_ID_RE=__import__("re").compile(r"doc_[A-Za-z0-9_-]{20,64}"),
    )
    result = handoff(export_revision(core, "doc_" + "a" * 24))
    assert result.content[1].type == "resource_link"
    parsed = urlsplit(result.structured_content["download_url"])
    request = Request({"type": "http", "method": "GET", "path": parsed.path, "headers": [],
                       "query_string": parsed.query.encode(), "path_params": {"document_id": "doc_" + "a" * 24}})
    response = asyncio.run(download_revision(core, request))
    assert response.status_code == 200 and response.body == raw
print("P3.33 composition + resource_link + exact-byte HTTP attachment smoke PASS")
