"""P4.25 everyday HWPX editing tools: exposed from existing P3.37 engine.

Inspired by template filling and plan/preview/apply UX offered by MIT
HWPX MCP peers. No upstream source code is copied. Reuses existing native
inline editing and the P3.0 durable revision store, not a new XML engine.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile

from hwpx_mcp.orchestration.p337_product_workflow import (
    fill_template_atomic,
    plan_literal_placeholder_fill,
)


def register_competitive_workflows(core):
    """Register practical tools on the same authenticated Streamable HTTP host."""

    def _owned(document_id: str):
        subject = core._caller_subject()
        metadata = core._load_metadata(document_id)
        if metadata["owner_subject"] != subject:
            raise PermissionError("DOCUMENT_NOT_OWNED")
        row = core.DOCUMENT_STORE.load_current(document_id)
        if row is None or row["owner_subject"] != subject:
            raise FileNotFoundError("DOCUMENT_REVISION_NOT_AVAILABLE")
        return metadata, row

    @core.mcp.tool()
    def discover_hwpx_workflows(
        task: str = "",
        limit: int = 5,
    ) -> dict:
        """Find the smallest useful user-facing HWPX MCP workflow.

        This is a lightweight gateway inspired by peer tool-search
        patterns. It describes real, registered actions, not imaginary
        capabilities and never executes document modifications.
        """
        core._caller_subject()
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("WORKFLOW_LIMIT_INVALID")
        if not isinstance(task, str) or len(task) > 500:
            raise ValueError("WORKFLOW_QUERY_INVALID")
        workflows = [
            ("create_and_deliver_document", "create",
             "Create a simple HWPX and return a file attachment in one call.",
             "text; optional title, filename, request_id"),
            ("create_rich_document_and_deliver", "create rich report",
             "Create a native multi-section HWPX with tables, equations and images.",
             "rich_plan; optional filename"),
            ("read_document_structure", "read inspect outline paragraphs",
             "Read structured sections and nested paragraph text.",
             "document_id; optional offset, limit, include_text"),
            ("find_document_text", "search find text",
             "Search normal and table-cell text with exact locators.",
             "document_id, query; optional max_matches, case_sensitive"),
            ("preview_template_fill", "preview template fill",
             "Preview placeholder replacements without modifying the document.",
             "document_id, values; optional require_each, require_unique"),
            ("fill_template_and_deliver", "fill template apply",
             "Fill HWPX placeholders and return the revised attachment.",
             "document_id, values, expected_revision"),
            ("replace_text_and_deliver", "replace batch find",
             "Replace multiple literal strings in one durable revision.",
             "document_id, replacements, expected_revision"),
            ("list_document_tables", "table list inspect cells",
             "Inspect grids, merged cells and captions.",
             "document_id; optional offset, limit"),
            ("edit_table_and_deliver", "table edit merge cell row column",
             "Edit HWPX table cells/structure and return revised attachment.",
             "document_id, expected_revision, operations"),
            ("inspect_document_formatting", "format style inspect font paragraph",
             "Inspect native paragraph and run formatting before editing.",
             "document_id; optional offset, limit, include_runs"),
            ("preview_document_formatting", "preview format style font paragraph",
             "Validate formatting changes without writing a new revision.",
             "document_id, operations"),
            ("format_document_and_deliver", "format edit font paragraph style",
             "Change native font and paragraph styles and deliver an updated HWPX.",
             "document_id, expected_revision, operations"),
            ("export_document_markdown", "markdown export text read convert",
             "Extract semantic HWPX text to Markdown, including nested paragraphs.",
             "document_id; optional include_table_cells, max_chars"),
        ]
        tokens = {word.casefold() for word in task.split() if word.strip()}
        synonyms = {
            "표": "table", "셀": "cell", "병합": "merge", "읽기": "read",
            "검색": "search", "찾기": "find", "치환": "replace",
            "수정": "edit", "작성": "create", "생성": "create",
            "템플릿": "template", "미리보기": "preview",
            "수식": "equations", "보고서": "report",
            "글꼴": "font", "서식": "format", "스타일": "style",
            "문단": "paragraph", "마크다운": "markdown",
            "변환": "convert", "추출": "export",
        }
        tokens |= {synonyms[word] for word in tokens if word in synonyms}
        ranked = []
        for index, (name, keywords, description, inputs) in enumerate(workflows):
            hay = (name + " " + keywords).casefold()
            score = sum(1 for token in tokens if token in hay)
            ranked.append((score, index, {
                "tool": name, "purpose": description, "inputs": inputs,
            }))
        if tokens:
            ranked = [row for row in ranked if row[0] > 0]
        ranked.sort(key=lambda row: (-row[0], row[1]))
        selected = [row[2] for row in ranked[:limit]]
        return {
            "ok": True, "phase": "P4.25",
            "matching_workflows": selected,
            "matching_count": len(ranked),
            "no_matches": not bool(selected),
            "executes_mutations": False,
            "next_step": "Call the suggested MCP tool with its required arguments.",
        }

    @core.mcp.tool()
    def create_and_deliver_document(
        text: str,
        title: str = "",
        filename: str = "document.hwpx",
        request_id: str = "",
    ) -> dict:
        """Create a real HWPX and provide its download in one MCP call.

        Uses the existing replay-safe create_document and P3.33 file
        delivery. There is no second document format or extra database.
        If a previous creation succeeded but the response was lost,
        repeat the same request_id with identical content.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("DOCUMENT_TEXT_REQUIRED")
        created = core.create_document(
            text=text, title=title, filename=filename,
            request_id=request_id,
        )
        from hwpx_mcp.delivery.p333_file_delivery import export_revision, handoff
        delivered = export_revision(
            core, document_id=created["document_id"],
            link_ttl_seconds=900,
        )
        attachment = handoff(delivered)
        attachment.structuredContent = {
            **delivered,
            "created": True,
            "idempotent_replay": created.get("idempotent_replay", False),
            "request_id": request_id or None,
            "native_pdf_created": False,
        }
        return attachment

    @core.mcp.tool()
    def create_rich_document_and_deliver(
        rich_plan: dict,
        filename: str = "report.hwpx",
    ):
        """Author a real multi-section HWPX with headings/tables/equations.

        Reuses the P3.38 rich-plan compiler and P3.21 native composer.
        A new owned revision is committed and returned as an MCP attachment.
        No Windows Hancom process, local validation folder or raw XML
        authorship is required.
        """
        from hwpx_mcp.orchestration.p338_rich_builder import compile_rich_document_plan
        from hwpx_mcp.document.p321_document_composer import compose_document_plan
        from hwpx_mcp.delivery.p333_file_delivery import export_revision, handoff

        owner = core._caller_subject()
        compiled = compile_rich_document_plan(rich_plan)
        with tempfile.TemporaryDirectory(prefix="p425-rich-") as tmp:
            destination = Path(tmp) / "report.hwpx"
            composition = compose_document_plan(
                destination, compiled["plan"],
                validator=lambda path: core.validate_hwpx_package(path, ingress=False),
            )
            data = destination.read_bytes()
        document_id = core._new_document_id()
        filename = core.sanitize_filename(filename)
        hwpx_path, _metadata_path = core._paths(document_id)
        hwpx_path.write_bytes(data)
        try:
            validated = core.validate_hwpx_package(hwpx_path, ingress=False)
            if validated.get("valid") is not True:
                raise ValueError("COMPOSED_HWPX_FAILED_VALIDATION")
            metadata = core._metadata(
                document_id, filename=filename, owner_subject=owner,
                validation=validated, title=str(rich_plan.get("title") or ""),
                source="p425-rich-composer",
            )
            committed = core._write_metadata(document_id, metadata)
        except Exception:
            # The canonical durable commit handles rollback/re-hydration.
            # Before a first successful commit, prevent orphaned local bytes.
            if core.DOCUMENT_STORE.load_current(document_id, allow_expired=True) is None:
                hwpx_path.unlink(missing_ok=True)
            raise
        delivered = export_revision(core, document_id, link_ttl_seconds=900)
        result = handoff(delivered)
        result.structuredContent = {
            **delivered, "ok": True, "created": True,
            "rich_plan_sha256": compiled["plan_sha256"],
            "rich_block_count": compiled["block_count"],
            "rich_sections": compiled["section_count"],
            "composer_receipt": composition,
            "commit_receipt": committed,
            "native_pdf_created": False,
        }
        return result

    @core.mcp.tool()
    def list_document_tables(
        document_id: str, offset: int = 0, limit: int = 10,
    ) -> dict:
        """Read real HWPX table grids, merged-cell anchors and cell text."""
        if type(offset) is not int or offset < 0:
            raise ValueError("OFFSET_INVALID")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("LIMIT_INVALID")
        _metadata, row = _owned(document_id)
        from hwpx_mcp.document.p27_tables import build_table_map
        with tempfile.TemporaryDirectory(prefix="p425-tables-") as tmp:
            path = Path(tmp) / "owned.hwpx"
            path.write_bytes(row["bytes"])
            mapped = build_table_map(path)
        tables = mapped["tables"]
        return {
            "ok": True, "document_id": document_id,
            "revision": row["revision"],
            "table_count": len(tables),
            "tables": [{
                "locator": table["locator"],
                "table_index": table["table_index"],
                "rows": table["rows"], "cols": table["cols"],
                "caption_text": table["caption_text"],
                "cells": [{
                    "locator": cell["locator"],
                    "row": cell["row"], "col": cell["col"],
                    "row_span": cell["row_span"], "col_span": cell["col_span"],
                    "text": cell["text"],
                } for cell in table["cells"]],
            } for table in tables[offset:offset + limit]],
            "next_offset": offset + limit if offset + limit < len(tables) else None,
        }

    @core.mcp.tool()
    def edit_table_and_deliver(
        document_id: str,
        expected_revision: int,
        operations: list[dict],
    ):
        """Change table cells, merged cells, rows and columns in one call.

        Operations use the existing P2.7 table/cell locators returned by
        list_document_tables. Applies the established atomic HWPX table
        editor, commits one owned revision and returns an MCP ResourceLink.
        """
        _metadata, row = _owned(document_id)
        if type(expected_revision) is not int or row["revision"] != expected_revision:
            raise RuntimeError("REVISION_CONFLICT_REFRESH_AND_LIST_TABLES")
        from hwpx_mcp.document.p27_tables import apply_table_edits_atomic
        from hwpx_mcp.delivery.p333_file_delivery import export_revision, handoff
        with tempfile.TemporaryDirectory(prefix="p425-edit-table-") as tmp:
            path = Path(tmp) / "owned.hwpx"
            path.write_bytes(row["bytes"])
            receipt = apply_table_edits_atomic(
                path, operations, expected_revision=expected_revision,
                current_revision=expected_revision,
                validator=lambda item: core.validate_hwpx_package(item, ingress=False),
            )
            modified = path.read_bytes()
        digest = hashlib.sha256(modified).hexdigest()
        metadata = dict(_metadata)
        metadata["revision"] = expected_revision + 1
        metadata["sha256"] = digest
        metadata["bytes"] = len(modified)
        metadata["last_table_operation_count"] = receipt["operation_count"]
        commit = core.DOCUMENT_STORE.put_revision(
            document_id=document_id, owner_subject=row["owner_subject"],
            revision=expected_revision + 1, expected_revision=expected_revision,
            data=modified, metadata=metadata,
            expires_at_epoch=row["expires_at_epoch"],
        )
        core._load_metadata(document_id)
        delivered = export_revision(core, document_id, link_ttl_seconds=900)
        result = handoff(delivered)
        result.structuredContent = {
            **delivered, "ok": True,
            "operation_count": receipt["operation_count"],
            "table_structure_changed": receipt["table_structure_changed"],
            "table_format_changed": receipt["table_format_changed"],
            "commit_receipt": commit,
        }
        return result

    @core.mcp.tool()
    def read_document_structure(
        document_id: str,
        offset: int = 0,
        limit: int = 50,
        include_text: bool = True,
    ) -> dict:
        """Read ordered HWPX paragraphs, including text inside table cells.

        Returns section/paragraph coordinates for follow-up edits. Pages
        are not inferred from XML structure; a native renderer is required
        for actual page layout.
        """
        if type(offset) is not int or offset < 0:
            raise ValueError("OFFSET_INVALID")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("LIMIT_INVALID")
        _metadata, row = _owned(document_id)
        from hwpx_mcp.document.p2_document import build_document_map
        with tempfile.TemporaryDirectory(prefix="p425-read-") as tmp:
            source = Path(tmp) / "owned.hwpx"
            source.write_bytes(row["bytes"])
            document = build_document_map(source)
        page = document["paragraphs"][offset:offset + limit]
        return {
            "ok": True, "document_id": document_id,
            "revision": row["revision"],
            "section_count": len(document["sections"]),
            "sections": document["sections"],
            "paragraph_count": document["paragraph_count"],
            "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < document["paragraph_count"] else None,
            "paragraphs": [
                {key: item[key] for key in (
                    "locator", "section_index", "paragraph_index",
                    "container", "text_sha256"
                )} | ({"text": item["text"]} if include_text else {})
                for item in page
            ],
            "semantic_sha256": document["semantic_sha256"],
            "pagination": "PARAGRAPH_OFFSET_NOT_NATIVE_PAGE_NUMBER",
        }

    @core.mcp.tool()
    def preview_template_fill(
        document_id: str,
        values: dict[str, str],
        require_each: bool = True,
        require_unique: bool = False,
    ) -> dict:
        """Preview {{placeholder}}/literal replacements before modifying an HWPX.

        Supports text in the existing inline editor's coordinate map,
        including any table-cell text represented there. Returns an edit
        count and match counts, not the entire original document.
        """
        metadata, row = _owned(document_id)
        with tempfile.TemporaryDirectory(prefix="p425-preview-") as tmp:
            template = Path(tmp) / "source.hwpx"
            template.write_bytes(row["bytes"])
            plan = plan_literal_placeholder_fill(
                template, values, require_each=require_each,
                require_unique=require_unique,
            )
        return {
            "ok": True, "document_id": document_id,
            "revision": row["revision"],
            "source_sha256": row["sha256"],
            "operation_count": plan["operation_count"],
            "matches": plan["matches"],
            "plan_sha256": plan["plan_sha256"],
            "committed": False,
        }

    @core.mcp.tool()
    def find_document_text(
        document_id: str, query: str,
        max_matches: int = 50,
        case_sensitive: bool = True,
    ) -> dict:
        """Search text across body and table-cell paragraphs in one call."""
        if not isinstance(query, str) or not query or len(query) > 256:
            raise ValueError("QUERY_MUST_BE_1_TO_256_CHARS")
        if type(max_matches) is not int or not 1 <= max_matches <= 100:
            raise ValueError("MATCH_LIMIT_INVALID")
        _metadata, row = _owned(document_id)
        from hwpx_mcp.document.p2_document import build_document_map
        with tempfile.TemporaryDirectory(prefix="p425-search-") as tmp:
            source = Path(tmp) / "owned.hwpx"
            source.write_bytes(row["bytes"])
            paragraphs = build_document_map(source)["paragraphs"]
        matches = []
        found = 0
        target = query if case_sensitive else query.casefold()
        for para in paragraphs:
            raw_text = para["text"]
            haystack = raw_text if case_sensitive else raw_text.casefold()
            start = 0
            while True:
                at = haystack.find(target, start)
                if at < 0:
                    break
                found += 1
                if len(matches) < max_matches:
                    matches.append({
                        "locator": para["locator"],
                        "section_index": para["section_index"],
                        "paragraph_index": para["paragraph_index"],
                        "container": para["container"],
                        "offset": at,
                        "context": raw_text[max(0, at - 60):at + len(query) + 60],
                    })
                start = at + len(target)
        return {
            "ok": True, "document_id": document_id,
            "revision": row["revision"], "query": query,
            "total_matches": found, "matches": matches,
            "truncated": found > len(matches),
            "includes_nested_paragraphs": True,
        }

    @core.mcp.tool()
    def fill_template_and_deliver(
        document_id: str,
        values: dict[str, str],
        expected_revision: int,
        require_each: bool = True,
        require_unique: bool = False,
    ) -> dict:
        """Fill placeholders, save one durable HWPX revision, return its download.

        No external file path required. The prior revision is retained.
        If another editor commits first, P3.0 revision CAS rejects this edit.
        An unchanged existing HWPX can be exported again without repeating
        a mutation.
        """
        metadata, row = _owned(document_id)
        if type(expected_revision) is not int or row["revision"] != expected_revision:
            raise RuntimeError("REVISION_CONFLICT_REFRESH_AND_PREVIEW")
        with tempfile.TemporaryDirectory(prefix="p425-fill-") as tmp:
            source = Path(tmp) / "template.hwpx"
            output = Path(tmp) / "filled.hwpx"
            source.write_bytes(row["bytes"])
            receipt = fill_template_atomic(
                source, output, values,
                require_each=require_each, require_unique=require_unique,
                validator=lambda path: core.validate_hwpx_package(path, ingress=False),
            )
            changed = output.read_bytes()
        digest = hashlib.sha256(changed).hexdigest()
        # Commit into the existing owner-specific durable document, never
        # produce a second anonymous file or write a user-supplied path.
        new_metadata = dict(metadata)
        new_metadata["revision"] = expected_revision + 1
        new_metadata["sha256"] = digest
        new_metadata["bytes"] = len(changed)
        new_metadata["last_template_fill_sha256"] = receipt["fill_sha256"]
        commit = core.DOCUMENT_STORE.put_revision(
            document_id=document_id,
            owner_subject=row["owner_subject"],
            revision=expected_revision + 1,
            expected_revision=expected_revision,
            data=changed,
            metadata=new_metadata,
            expires_at_epoch=row["expires_at_epoch"],
        )
        # Hydrate via the canonical document cache read path; a future
        # operation never sees stale cached bytes after an edit.
        core._load_metadata(document_id)
        from hwpx_mcp.delivery.p333_file_delivery import export_revision
        export = export_revision(core, document_id, link_ttl_seconds=900)
        from hwpx_mcp.delivery.p333_file_delivery import handoff
        attachment = handoff(export)
        attachment.structuredContent = {
            **export,
            "ok": True, "document_id": document_id,
            "revision": expected_revision + 1,
            "sha256": digest, "bytes": len(changed),
            "matches": receipt["matches"],
            "operation_count": receipt["operation_count"],
            "fill_receipt_sha256": receipt["fill_sha256"],
            "commit_receipt": commit,
            "source_template_mutated": False,
        }
        return attachment

    @core.mcp.tool()
    def replace_text_and_deliver(
        document_id: str,
        replacements: dict[str, str],
        expected_revision: int,
        require_each: bool = True,
    ) -> dict:
        """Batch search/replace in HWPX, commit one revision and deliver.

        Exact literal matching preserves the source inline run structure.
        This is the same verified engine as template filling; placeholders
        need not use any special braces.
        """
        return fill_template_and_deliver(
            document_id=document_id, values=replacements,
            expected_revision=expected_revision,
            require_each=require_each, require_unique=False,
        )
