"""Exercise registered MCP tools and the signed download handler on a supplied HWPX.

Run in a fresh process per file. Only authentication and database storage are
substituted. The source stays read-only. Pass two unique literals from distinct
paragraphs (for example, one body paragraph and one table cell).
"""
import argparse
import asyncio
import base64
import hashlib
import json
import resource
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from starlette.requests import Request

from hwpx_mcp.document.p2_document import build_document_map


class RevisionStore:
    mode = "benchmark-memory"

    def __init__(self):
        self.rows = {}

    def cleanup_expired(self):
        return 0

    def load_current(self, document_id, **kwargs):
        revisions = self.rows.get(document_id, {})
        return revisions.get(max(revisions)) if revisions else None

    def load_revision(self, document_id, revision):
        return self.rows.get(document_id, {}).get(revision)

    def put_revision(self, document_id, revision, expected_revision, data, **fields):
        revisions = self.rows.setdefault(document_id, {})
        assert max(revisions, default=0) == expected_revision == revision - 1
        revisions[revision] = dict(fields, revision=revision, bytes=data,
                                   sha256=hashlib.sha256(data).hexdigest())
        return {"revision": revision}


async def exercise(core, source, literals, directory):
    timings = {}

    async def call(name, **arguments):
        start = time.perf_counter()
        result = await core.mcp.call_tool(name, arguments)
        timings.setdefault(name, []).append(round(time.perf_counter() - start, 3))
        assert not result.is_error
        return result

    def payload(result):
        return result.structured_content or json.loads(result.content[0].text)

    raw = source.read_bytes()
    before = build_document_map(source)["paragraphs"]
    assert len({p["locator"] for p in before}) == len(before)
    admitted = await call("ingest_document", filename="benchmark.hwpx",
                          content_base64=base64.b64encode(raw).decode("ascii"))
    admission = payload(admitted)
    doc = admission["document_id"]
    ingress_bytes = core.DOCUMENT_STORE.load_revision(doc, 1)["bytes"]
    normalization = admission.get("ingress_normalization")
    if normalization:
        assert normalization["submitted_sha256"] == hashlib.sha256(raw).hexdigest()
        assert hashlib.sha256(ingress_bytes).hexdigest() == admission["sha256"]
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(core._paths(doc)[0]) as normalized:
            assert original.namelist() == normalized.namelist()
            assert normalized.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
            for name in original.namelist():
                assert original.read(name) == normalized.read(name)
    else:
        assert ingress_bytes == raw
    page = await call("read_document_structure", document_id=doc, expected_revision=1,
                      offset=max(len(before) - 10, 0), limit=10, include_section_locators=False)
    page_data = payload(page)
    assert page_data["paragraph_count"] == len(before) and page_data["next_offset"] is None
    assert [p["locator"] for p in page_data["paragraphs"]] == [p["locator"] for p in before[-10:]]
    values = {literal: f"기록수정{index}" for index, literal in enumerate(literals)}
    targets = []
    for literal in literals:
        search = await call("find_document_text", document_id=doc, query=literal,
                            inline_coordinates=True, expected_revision=1)
        hit, = payload(search)["matches"]
        assert hit["inline_range_editable"]
        targets.append(hit["locator"])
    assert len(set(targets)) == len(literals)
    preview = await call("preview_template_fill", document_id=doc, values=values, require_unique=True)
    result = await call("fill_template_and_deliver", document_id=doc, expected_revision=1,
                        values=values, require_unique=True,
                        expected_plan_sha256=payload(preview)["plan_sha256"])
    link, = [item for item in result.content if item.type == "resource_link"]
    url = urlsplit(str(link.uri))
    request = Request({"type": "http", "method": "GET", "path": url.path,
                       "query_string": url.query.encode(), "headers": [],
                       "path_params": {"document_id": doc}})
    response = await core.download_delivery(request)
    assert response.status_code == 200 and response.headers["x-hwpx-revision"] == "2"
    assert hashlib.sha256(response.body).hexdigest() == result.structured_content["sha256"]
    output = directory / "downloaded.hwpx"
    output.write_bytes(response.body)
    after = build_document_map(output)["paragraphs"]
    assert len(before) == len(after)
    replacements = dict(zip(targets, literals))
    for old, new in zip(before, after):
        assert old["locator"] == new["locator"]
        literal = replacements.get(old["locator"])
        expected = old["text"] if literal is None else old["text"].replace(literal, values[literal])
        assert new["text"] == expected
    sections = {p["section"] for p in before if p["locator"] in replacements}
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(output) as edited:
        assert original.namelist() == edited.namelist()
        for name in original.namelist():
            if name not in sections:
                assert original.read(name) == edited.read(name)
    assert core.DOCUMENT_STORE.load_revision(doc, 1)["bytes"] == ingress_bytes
    assert source.read_bytes() == raw
    return {"source_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "ingress_normalization": normalization, "admitted_sha256": admission["sha256"],
            "paragraphs": len(before), "edited": len(targets), "seconds": timings,
            "compact_page_bytes": len(json.dumps(page_data, ensure_ascii=False).encode()),
            "process_peak_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("literals", nargs=2)
    args = parser.parse_args()
    with patch("hwpx_mcp.security.auth_store.DurableOAuthStore"), \
         patch("hwpx_mcp.storage.document_store.DurableDocumentStore"), \
         patch("hwpx_mcp.evidence.p414_evidence_store.P414EvidenceStore"):
        import server as core

    with tempfile.TemporaryDirectory() as tmp, \
         patch.object(core, "OBJECT_DIR", Path(tmp)), \
         patch.object(core, "_caller_subject", return_value="local-benchmark"), \
         patch.object(core, "DOWNLOAD_SECRET", "isolated-benchmark-only"), \
         patch.object(core, "DOCUMENT_STORE", RevisionStore()):
        result = asyncio.run(exercise(core, args.source, args.literals, Path(tmp)))
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
