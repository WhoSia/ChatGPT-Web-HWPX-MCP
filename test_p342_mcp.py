from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from p335_registry import intake_source
from p342_mcp import register_p342_tools


def _zip_bytes(section: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("mimetype", b"application/hwp+zip")
        archive.writestr("Contents/header.xml", b"<header/>")
        archive.writestr("Contents/section0.xml", section)
    return stream.getvalue()


class FakeMCP:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self, *args, **kwargs):
        if args and callable(args[0]):
            fn = args[0]
            self.tools[fn.__name__] = fn
            return fn

        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def load_revision(self, document_id, revision):
        return self.rows.get((document_id, int(revision)))


class FakeRegistry:
    def __init__(self, rows):
        self._rows = rows

    def records(self, owner_subject):
        assert owner_subject == "owner-a"
        return list(self._rows)


class FakeCore:
    def __init__(self, store):
        self.mcp = FakeMCP()
        self.DOCUMENT_STORE = store

    def _caller_subject(self):
        return "owner-a"


def _metadata():
    return {
        "source_id": "metadata-only",
        "original_filename": "metadata-only.hwpx",
        "institution": "기관",
        "source_family": "test",
        "retrieved_at": "2026-09-26T00:00:00Z",
        "access_status": "PUBLICLY_ACCESSIBLE",
        "source_url": "https://example.org/source",
        "provenance_notes": "Metadata-only test record.",
    }


def _register(owner_after: str = "owner-a"):
    before = _zip_bytes(b"<section><p>a</p></section>")
    after = _zip_bytes(b"<section><p>b</p></section>")
    store = FakeStore(
        {
            ("doc", 1): {
                "owner_subject": "owner-a",
                "bytes": before,
                "sha256": "unused",
            },
            ("doc", 2): {
                "owner_subject": owner_after,
                "bytes": after,
                "sha256": "unused",
            },
        }
    )
    core = FakeCore(store)
    corpus = FakeRegistry([intake_source(_metadata())])

    def owned(document_id):
        assert document_id == "doc"
        return {"revision": 2}, Path("unused.hwpx")

    register_p342_tools(core, owned, corpus)
    return core


def test_p342_contracts_and_owner_scoped_ledger_are_registered():
    core = _register()
    names = set(core.mcp.tools)
    assert {
        "get_mutation_footprint_contract",
        "certify_document_revision_mutation_footprint",
        "get_corpus_evidence_contract",
        "query_corpus_coverage_ledger",
        "query_evidence_grounded_design_generalizations",
    } <= names

    mutation = core.mcp.tools["get_mutation_footprint_contract"]()
    assert mutation["phase"] == "P3.42"
    assert mutation["scope_policy"]["exact_paths_only"] is True

    ledger = core.mcp.tools["query_corpus_coverage_ledger"]()
    assert ledger["total"] == 1
    assert ledger["items"][0]["source_id"] == "metadata-only"
    assert ledger["items"][0]["verdicts"]["BYTES_ACQUIRED"]["status"] == "WITHHELD"


def test_durable_revision_auditor_measures_exact_scope():
    core = _register()
    result = core.mcp.tools["certify_document_revision_mutation_footprint"](
        "doc",
        1,
        2,
        {
            "changed_parts": ["Contents/section0.xml"],
            "required_changed_parts": ["Contents/section0.xml"],
        },
    )
    assert result["enforcement"]["passed"] is True
    cert = result["certificate"]
    assert cert["preservation"]["actual_grade"] == "TARGETED_PARTS_ONLY"
    assert cert["observed"]["changed_parts"] == ["Contents/section0.xml"]


def test_durable_revision_auditor_rejects_cross_owner_history():
    core = _register(owner_after="owner-b")
    with pytest.raises(PermissionError, match="OWNER_MISMATCH"):
        core.mcp.tools["certify_document_revision_mutation_footprint"](
            "doc",
            1,
            2,
            {"changed_parts": ["Contents/section0.xml"]},
        )
