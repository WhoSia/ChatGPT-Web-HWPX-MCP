from __future__ import annotations

import hashlib
import json
import re
from typing import Any


FIDELITY_RANK = {
    "none": 0,
    "inventory": 1,
    "raw-preserved": 2,
    "structural": 3,
    "semantic": 4,
    "editable-native": 5,
}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _block(
    *,
    block_id: str,
    kind: str,
    fidelity: str,
    text: str = "",
    source: dict | None = None,
    data: dict | None = None,
) -> dict:
    payload = {
        "block_id": block_id,
        "kind": kind,
        "fidelity": fidelity,
        "text": text,
        "source": source or {},
        "data": data or {},
    }
    payload["block_sha256"] = _digest(payload)
    return payload


def hwp5_to_common_ir(parsed: dict, *, source_sha256: str, filename: str = "") -> dict:
    blocks: list[dict] = []
    for paragraph in parsed.get("paragraphs", []):
        source = {
            key: paragraph.get(key)
            for key in (
                "section_index",
                "section_stream",
                "record_index",
                "record_level",
                "tag_id",
            )
        }
        flow_kind = str(paragraph.get("flow_kind") or "body")
        block_kind = "paragraph" if flow_kind == "body" else flow_kind
        blocks.append(
            _block(
                block_id=f"hwp5:p:{paragraph.get('paragraph_index', len(blocks))}",
                kind=block_kind,
                fidelity="semantic",
                text=paragraph.get("text", ""),
                source={
                    **source,
                    "flow_kind": flow_kind,
                    "control_index": paragraph.get("control_index"),
                    "control_id": paragraph.get("control_id"),
                },
                data={
                    "paragraph_style": paragraph.get("paragraph_style", {}),
                    "runs": paragraph.get("runs", []),
                    "run_visible_span_fidelity": paragraph.get(
                        "run_visible_span_fidelity", "none"
                    ),
                },
            )
        )

    for index, table in enumerate(parsed.get("tables", [])):
        source = {
            key: table.get(key)
            for key in (
                "section_index",
                "section_stream",
                "record_index",
                "record_level",
                "tag_id",
            )
        }
        data = {
            key: value
            for key, value in table.items()
            if key not in source and key not in {"kind", "fidelity"}
        }
        blocks.append(
            _block(
                block_id=f"hwp5:table:{index}",
                kind="table",
                fidelity=table.get("fidelity", "inventory"),
                source=source,
                data=data,
            )
        )

    for index, equation in enumerate(parsed.get("equations", [])):
        source = {
            key: equation.get(key)
            for key in (
                "section_index",
                "section_stream",
                "record_index",
                "record_level",
                "tag_id",
            )
        }
        data = {
            key: value
            for key, value in equation.items()
            if key not in source and key not in {"kind", "fidelity", "script"}
        }
        blocks.append(
            _block(
                block_id=f"hwp5:eq:{index}",
                kind="equation",
                fidelity=equation.get("fidelity", "inventory"),
                text=equation.get("script", ""),
                source=source,
                data=data,
            )
        )

    for index, obj in enumerate(parsed.get("objects", [])):
        source = {
            key: obj.get(key)
            for key in (
                "section_index",
                "section_stream",
                "record_index",
                "record_level",
                "tag_id",
            )
        }
        data = {
            key: value
            for key, value in obj.items()
            if key not in source and key not in {"kind", "fidelity"}
        }
        blocks.append(
            _block(
                block_id=f"hwp5:obj:{index}",
                kind=obj.get("kind", "object"),
                fidelity=obj.get("fidelity", "inventory"),
                source=source,
                data=data,
            )
        )

    for index, binary in enumerate(parsed.get("binary_items", [])):
        blocks.append(
            _block(
                block_id=f"hwp5:bin:{index}",
                kind="binary",
                fidelity="inventory",
                source={"stream": binary.get("stream")},
                data={
                    "bytes": binary.get("bytes"),
                    "sha256": binary.get("sha256"),
                },
            )
        )

    inventory = {}
    for block in blocks:
        inventory[block["kind"]] = inventory.get(block["kind"], 0) + 1
    return {
        "schema": "who-common-document-ir/0.2",
        "source_format": "hwp5",
        "source_filename": filename,
        "source_sha256": source_sha256,
        "source_version": parsed.get("version"),
        "source_flags": parsed.get("flags", {}),
        "char_shapes": parsed.get("char_shapes", []),
        "readable": bool(parsed.get("readable")),
        "block_count": len(blocks),
        "inventory": inventory,
        "fidelity": parsed.get("fidelity", {}),
        "blocks": blocks,
        "ir_sha256": _digest(blocks),
        "warnings": parsed.get("warnings", []),
    }


def hwpx_to_common_ir(
    *,
    document_id: str,
    revision: int,
    semantic_sha256: str,
    paragraphs: list[dict],
    tables: list[dict],
    equations: list[dict],
    pictures: list[dict],
    media_items: list[dict],
) -> dict:
    blocks: list[dict] = []
    for index, paragraph in enumerate(paragraphs):
        blocks.append(
            _block(
                block_id=f"hwpx:p:{index}",
                kind="paragraph",
                fidelity="editable-native",
                text=paragraph.get("text", ""),
                source={
                    "document_id": document_id,
                    "revision": revision,
                    "locator": paragraph.get("locator"),
                    "address_stability": paragraph.get("address_stability"),
                },
                data={
                    "text_sha256": paragraph.get("text_sha256"),
                    "section_index": paragraph.get("section_index"),
                    "paragraph_index": paragraph.get("paragraph_index"),
                },
            )
        )

    for index, table in enumerate(tables):
        cells = table.get("cells", [])
        text_parts = [
            str(cell.get("text", ""))
            for cell in cells
            if str(cell.get("text", "")).strip()
        ]
        blocks.append(
            _block(
                block_id=f"hwpx:table:{index}",
                kind="table",
                fidelity="editable-native",
                text="\n".join(text_parts),
                source={
                    "document_id": document_id,
                    "revision": revision,
                    "locator": table.get("locator"),
                },
                data={
                    "rows": table.get("rows"),
                    "cols": table.get("cols"),
                    "cell_count": len(cells),
                    "cells": cells[:400],
                    "cells_truncated": len(cells) > 400,
                },
            )
        )

    for index, equation in enumerate(equations):
        blocks.append(
            _block(
                block_id=f"hwpx:eq:{index}",
                kind="equation",
                fidelity="editable-native",
                text=equation.get("script", ""),
                source={
                    "document_id": document_id,
                    "revision": revision,
                    "locator": equation.get("locator"),
                    "paragraph_locator": equation.get("paragraph_locator"),
                },
                data={
                    "script_sha256": equation.get("script_sha256"),
                    "width": equation.get("width"),
                    "height": equation.get("height"),
                    "base_unit": equation.get("base_unit"),
                },
            )
        )

    for index, picture in enumerate(pictures):
        blocks.append(
            _block(
                block_id=f"hwpx:pic:{index}",
                kind="picture",
                fidelity="editable-native",
                source={
                    "document_id": document_id,
                    "revision": revision,
                    "locator": picture.get("locator"),
                    "paragraph_locator": picture.get("paragraph_locator"),
                },
                data={
                    "binary_item_id_ref": picture.get("binary_item_id_ref"),
                    "width": picture.get("width"),
                    "height": picture.get("height"),
                    "placement": picture.get("placement"),
                },
            )
        )

    for index, media in enumerate(media_items):
        blocks.append(
            _block(
                block_id=f"hwpx:media:{index}",
                kind="binary",
                fidelity="editable-native",
                source={
                    "document_id": document_id,
                    "revision": revision,
                    "item_id": media.get("item_id"),
                },
                data={
                    "format": media.get("format"),
                    "bytes": media.get("bytes"),
                    "sha256": media.get("sha256"),
                    "picture_reference_count": media.get("picture_reference_count"),
                },
            )
        )

    inventory = {}
    for block in blocks:
        inventory[block["kind"]] = inventory.get(block["kind"], 0) + 1
    return {
        "schema": "who-common-document-ir/0.2",
        "source_format": "hwpx",
        "document_id": document_id,
        "revision": revision,
        "semantic_sha256": semantic_sha256,
        "block_count": len(blocks),
        "inventory": inventory,
        "fidelity": {
            "paragraph_text": "editable-native",
            "tables": "editable-native",
            "equations": "editable-native",
            "pictures": "editable-native",
        },
        "blocks": blocks,
        "ir_sha256": _digest(blocks),
        "warnings": [],
    }


def extract_common_ir(
    ir: dict,
    *,
    kinds: list[str] | None = None,
    minimum_fidelity: str = "inventory",
    include_text: bool = True,
    include_data: bool = True,
    max_blocks: int = 200,
) -> dict:
    """Return only blocks whose object family and fidelity meet an explicit extraction threshold."""
    threshold = str(minimum_fidelity or "inventory")
    if threshold not in FIDELITY_RANK:
        raise ValueError(f"Unknown fidelity threshold: {threshold}")
    allowed = None if not kinds else {str(item) for item in kinds}
    limit = max(1, min(int(max_blocks), 1000))
    blocks = []
    rejected = {}
    eligible_total = 0
    for block in ir.get("blocks", []):
        kind = str(block.get("kind", ""))
        fidelity = str(block.get("fidelity", "none"))
        if allowed is not None and kind not in allowed:
            continue
        if FIDELITY_RANK.get(fidelity, -1) < FIDELITY_RANK[threshold]:
            rejected[fidelity] = rejected.get(fidelity, 0) + 1
            continue
        eligible_total += 1
        if len(blocks) >= limit:
            continue
        item = {
            "block_id": block.get("block_id"),
            "kind": kind,
            "fidelity": fidelity,
            "source": block.get("source", {}),
            "block_sha256": block.get("block_sha256"),
        }
        if include_text:
            item["text"] = block.get("text", "")
        if include_data:
            item["data"] = block.get("data", {})
        blocks.append(item)
    return {
        "minimum_fidelity": threshold,
        "requested_kinds": sorted(allowed) if allowed is not None else None,
        "eligible_block_count": eligible_total,
        "returned_blocks": len(blocks),
        "truncated": eligible_total > len(blocks),
        "rejected_by_fidelity": rejected,
        "blocks": blocks,
    }


def search_common_ir(
    ir: dict,
    query: str,
    *,
    case_sensitive: bool = False,
    kinds: list[str] | None = None,
    max_results: int = 100,
) -> dict:
    needle = str(query)
    if not needle:
        raise ValueError("query must not be empty")
    limit = max(1, min(int(max_results), 500))
    allowed = None if not kinds else {str(item) for item in kinds}
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(needle), flags)
    hits = []
    for block in ir.get("blocks", []):
        if allowed is not None and block.get("kind") not in allowed:
            continue
        text = str(block.get("text", ""))
        for match in pattern.finditer(text):
            left = max(0, match.start() - 120)
            right = min(len(text), match.end() + 120)
            hits.append({
                "block_id": block.get("block_id"),
                "kind": block.get("kind"),
                "fidelity": block.get("fidelity"),
                "match_start": match.start(),
                "match_end": match.end(),
                "context": text[left:right],
                "context_start": left,
                "source": block.get("source", {}),
            })
            if len(hits) >= limit:
                return {
                    "query": needle,
                    "case_sensitive": case_sensitive,
                    "match_count": len(hits),
                    "truncated": True,
                    "hits": hits,
                }
    return {
        "query": needle,
        "case_sensitive": case_sensitive,
        "match_count": len(hits),
        "truncated": False,
        "hits": hits,
    }


def slice_common_ir(
    ir: dict,
    *,
    start_block: int = 0,
    block_count: int = 50,
    kinds: list[str] | None = None,
) -> dict:
    allowed = None if not kinds else {str(item) for item in kinds}
    filtered = [
        block for block in ir.get("blocks", [])
        if allowed is None or block.get("kind") in allowed
    ]
    start = max(0, int(start_block))
    count = max(1, min(int(block_count), 200))
    end = min(len(filtered), start + count)
    return {
        "start_block": start,
        "end_block_exclusive": end,
        "returned_blocks": end - start,
        "total_blocks": len(filtered),
        "has_more": end < len(filtered),
        "next_start_block": end if end < len(filtered) else None,
        "blocks": filtered[start:end],
    }
