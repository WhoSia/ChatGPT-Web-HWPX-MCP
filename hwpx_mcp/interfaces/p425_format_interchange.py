"""P4.25 user-facing native HWPX formatting and Markdown interchange.

Built on the existing P2.2 formatting and P2 document maps. Markdown is
semantic text interchange, NOT pixel-identical page rendering. No Hancom
installation and no user-supplied filesystem path are required.
"""
from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path


def document_to_markdown(document: dict, *, include_table_cells: bool = True) -> dict:
    """Convert the existing ordered paragraph map to conservative Markdown.

    Nested table-cell paragraphs are emitted as quoted annotated lines,
    never falsely reconstructed as a rectangular table. Non-text objects
    (images, equations, floating shapes) require a separate object export.
    """
    sections = document.get("sections", [])
    paragraphs = document.get("paragraphs", [])
    lines: list[str] = []
    current_section = None
    included = 0
    for paragraph in paragraphs:
        section = paragraph.get("section_index", 0)
        if current_section is not None and section != current_section:
            lines.extend(["", "---", ""])
        current_section = section
        text = str(paragraph.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            continue
        container = paragraph.get("container", "section-body")
        if container != "section-body":
            # Only table cells are suppressed when exporting structured
            # tables separately. Captions and other nested text remain
            # available even when a document includes at least one table.
            if container == "tc" and not include_table_cells:
                continue
            text = f"> [nested {container}; paragraph {paragraph.get('paragraph_index', '?')}] " + text.replace("\n", " ")
        else:
            # Escape Markdown metacharacters: a literal HWPX paragraph must
            # not become an accidental heading/list/code block.
            text = re.sub(r"([\\`*_{}\[\]<>#+!|])", r"\\\1", text)
            if re.match(r"^(?:\d+[.)]|[-+*])\s", text):
                text = "\\" + text
        lines.append(text)
        lines.append("")
        included += 1
    md = "\n".join(lines).strip()
    return {
        "markdown": md,
        "paragraphs_emitted": included,
        "section_count": len(sections),
        "semantic_sha256": document.get("semantic_sha256"),
        "representation": "TEXT_SEMANTIC_NOT_NATIVE_PAGINATION",
        "nontext_objects_included": False,
        "nested_table_cells_annotated": bool(include_table_cells),
    }


def tables_to_markdown(table_map: dict) -> dict:
    """Render actual HWPX table anchors into conservative Markdown grids.

    Markdown has no native cell spans: merged anchors are shown once and
    spanned positions stay empty. The loss of span semantics is reported.
    The caller appends these tables after body text; positional interleave
    with paragraphs is not represented here.
    """
    chunks = []
    span_warnings = []
    for index, table in enumerate(table_map.get("tables", [])):
        rows, cols = int(table["rows"]), int(table["cols"])
        if not 1 <= rows <= 200 or not 1 <= cols <= 100:
            raise ValueError("TABLE_DIMENSIONS_INVALID")
        grid = [["" for _ in range(cols)] for _ in range(rows)]
        for cell in table.get("cells", []):
            row, col = int(cell["row"]), int(cell["col"])
            rs, cs = int(cell.get("row_span", 1)), int(cell.get("col_span", 1))
            if not (0 <= row < rows and 0 <= col < cols and
                    1 <= rs <= rows-row and 1 <= cs <= cols-col):
                raise ValueError("TABLE_CELL_ANCHOR_INVALID")
            text = str(cell.get("text") or "").replace("|", r"\\|")
            text = " ".join(text.splitlines()).strip()
            grid[row][col] = text
            if rs > 1 or cs > 1:
                span_warnings.append({
                    "table_index": index, "row": row, "col": col,
                    "row_span": rs, "col_span": cs,
                })
        header = [f"열 {col + 1}" for col in range(cols)]
        # Synthetic column names prevent falsely treating first data row
        # as a header when the HWPX table has no header property.
        lines = [
            f"### 표 {index + 1}",
            "",
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * cols) + " |",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in grid)
        chunks.append("\n".join(lines))
    return {
        "markdown": "\n\n".join(chunks),
        "table_count": len(chunks),
        "merged_cell_warnings": span_warnings,
        "table_position": "APPENDED_AFTER_PARAGRAPHS",
    }


def register_format_interchange_tools(core):
    def _owned(document_id: str):
        owner = core._caller_subject()
        core._paths(document_id)
        row = core.DOCUMENT_STORE.load_current(document_id)
        if row is None or row.get("owner_subject") != owner:
            raise FileNotFoundError("DOCUMENT_NOT_AVAILABLE_TO_OWNER")
        return row

    @core.mcp.tool()
    def inspect_document_formatting(
        document_id: str, offset: int = 0, limit: int = 30,
        include_runs: bool = True,
    ) -> dict:
        """Inspect native paragraph style and font/run properties by locator."""
        if type(offset) is not int or offset < 0:
            raise ValueError("OFFSET_INVALID")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("LIMIT_INVALID")
        from hwpx_mcp.document.p22_formatting import build_formatting_map
        row = _owned(document_id)
        with tempfile.TemporaryDirectory(prefix="p425-format-read-") as tmp:
            path = Path(tmp) / "document.hwpx"
            path.write_bytes(row["bytes"])
            fmt = build_formatting_map(path)
        total = len(fmt["paragraphs"])
        page = fmt["paragraphs"][offset:offset + limit]
        return {
            "ok": True, "document_id": document_id, "revision": row["revision"],
            "formatting_sha256": fmt["formatting_sha256"],
            "property_counts": fmt["property_counts"],
            "total_paragraphs": total,
            "paragraphs": [
                {
                    "locator": p["locator"], "container": p["container"],
                    "section_index": p["section_index"],
                    "paragraph_index": p["paragraph_index"],
                    "paragraph_property": p["paragraph_property"],
                    "style_property": p["style_property"],
                    "runs": p["runs"] if include_runs else [],
                } for p in page
            ],
            "next_offset": offset + limit if offset + limit < total else None,
        }

    @core.mcp.tool()
    def preview_document_formatting(
        document_id: str, operations: list[dict],
    ) -> dict:
        """Validate native font/paragraph operations without modifying HWPX.

        The preview uses the exact same P2.2 operation normalizer as the
        actual formatting engine, so invalid paragraph and run locators
        are caught before the next mutation tool call.
        """
        if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
            raise ValueError("OPERATIONS_INVALID")
        from hwpx_mcp.document.p22_formatting import (
            build_formatting_map, _normalize_formatting_operations,
        )
        row = _owned(document_id)
        with tempfile.TemporaryDirectory(prefix="p425-format-preview-") as tmp:
            path = Path(tmp) / "document.hwpx"
            path.write_bytes(row["bytes"])
            current = build_formatting_map(path)
            normalized = _normalize_formatting_operations(operations, current)
        return {
            "ok": True, "document_id": document_id,
            "revision": row["revision"],
            "formatting_sha256": current["formatting_sha256"],
            "operation_count": len(normalized),
            "targets": [
                {"target": operation["target"], "op": operation["op"],
                 "format": operation["format"]}
                for operation in normalized
            ],
            "committed": False,
            "next_tool": "format_document_and_deliver",
        }

    @core.mcp.tool()
    def format_document_and_deliver(
        document_id: str, expected_revision: int, operations: list[dict],
    ):
        """Apply native font, run and paragraph styles, then deliver HWPX.

        Obtain exact paragraph locators from inspect_document_formatting;
        operations are the existing P2.2 set_run_format and
        set_paragraph_format schema. One durable CAS revision is committed.
        """
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("REVISION_INVALID")
        if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
            raise ValueError("OPERATIONS_INVALID")
        row = _owned(document_id)
        if row["revision"] != expected_revision:
            raise RuntimeError("REVISION_CONFLICT_REFRESH_FORMATTING")
        from hwpx_mcp.document.p22_formatting import apply_formatting_atomic
        from hwpx_mcp.delivery.p333_file_delivery import export_revision, handoff
        with tempfile.TemporaryDirectory(prefix="p425-format-write-") as tmp:
            path = Path(tmp) / "document.hwpx"
            path.write_bytes(row["bytes"])
            receipt = apply_formatting_atomic(
                path, operations, expected_revision=expected_revision,
                current_revision=expected_revision,
                validator=lambda p: core.validate_hwpx_package(p, ingress=False),
            )
            modified = path.read_bytes()
        digest = hashlib.sha256(modified).hexdigest()
        metadata = dict(row["metadata"])
        metadata.update(revision=expected_revision + 1, sha256=digest,
                        bytes=len(modified),
                        last_formatting_sha256=receipt["after"]["formatting_sha256"])
        core.DOCUMENT_STORE.put_revision(
            document_id=document_id, owner_subject=row["owner_subject"],
            revision=expected_revision + 1, expected_revision=expected_revision,
            data=modified, metadata=metadata,
            expires_at_epoch=row["expires_at_epoch"],
        )
        exported = export_revision(core, document_id, link_ttl_seconds=900)
        attachment = handoff(exported)
        attachment.structuredContent = {
            **exported, "ok": True,
            "formatting_changed": receipt["formatting_changed"],
            "text_changed": receipt["semantic_changed"],
            "operation_count": receipt["operation_count"],
            "formatting_sha256": receipt["after"]["formatting_sha256"],
        }
        return attachment

    @core.mcp.tool()
    def export_document_markdown(
        document_id: str,
        include_table_cells: bool = True,
        max_chars: int = 100000,
        include_tables: bool = True,
    ) -> dict:
        """Extract semantic HWPX text as Markdown; no fake page layout."""
        if type(max_chars) is not int or not 1 <= max_chars <= 200000:
            raise ValueError("MAX_CHARS_INVALID")
        from hwpx_mcp.document.p2_document import build_document_map
        row = _owned(document_id)
        with tempfile.TemporaryDirectory(prefix="p425-markdown-") as tmp:
            path = Path(tmp) / "document.hwpx"
            path.write_bytes(row["bytes"])
            document = build_document_map(path)
            table_data = None
            if include_tables:
                from hwpx_mcp.document.p27_tables import build_table_map
                table_data = tables_to_markdown(build_table_map(path))
        result = document_to_markdown(
            document, include_table_cells=(
                include_table_cells and not (include_tables and table_data and table_data["table_count"])
            )
        )
        md = result.pop("markdown")
        if table_data is not None and table_data["table_count"]:
            md = (md + "\n\n" + table_data["markdown"]).strip()
        return {
            "ok": True, "document_id": document_id, "revision": row["revision"],
            **result, "markdown": md[:max_chars],
            "total_markdown_chars": len(md),
            "truncated": len(md) > max_chars,
            "table_count": table_data["table_count"] if table_data else 0,
            "merged_cell_warnings": table_data["merged_cell_warnings"] if table_data else [],
            "table_position": table_data["table_position"] if table_data else "NOT_EXPORTED",
        }
