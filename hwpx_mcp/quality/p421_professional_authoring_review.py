"""P4.21 product-facing professional document plan review.

Deterministic, advisory-only diagnostics: actionable edits to authoring plans
without changing text, inventing captions, or claiming native visual authority.
"""
from __future__ import annotations
import hashlib
import json
from typing import Any, Mapping

SCHEMA = "chatgpt-web-hwpx-mcp/p421/professional-authoring-review/v1"
VISUAL_KINDS = frozenset({"table", "picture", "equation", "chart"})
TEXT_KINDS = frozenset({"title", "heading", "paragraph", "caption"})


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def review_authoring_plan(plan: Mapping[str, Any]) -> dict:
    """Return explicit quality suggestions; leave the submitted plan unchanged."""
    if not isinstance(plan, Mapping):
        raise ValueError("plan must be a mapping")
    blocks = plan.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("plan.blocks must be a list")
    if any(not isinstance(x, Mapping) for x in blocks):
        raise ValueError("every block must be a mapping")

    diagnostics: list[dict] = []
    titles = [i for i, b in enumerate(blocks) if b.get("type") == "title"]
    headings = [i for i, b in enumerate(blocks) if b.get("type") == "heading"]
    if not titles and blocks:
        diagnostics.append({"code": "TITLE_HIERARCHY_MISSING", "block_index": None,
                            "suggestion": "Define a distinct native title block"})
    if len(titles) > 1:
        diagnostics.append({"code": "MULTIPLE_PRIMARY_TITLES", "block_index": titles[1],
                            "suggestion": "Keep one primary title; use headings for sections"})
    if headings:
        levels = []
        for i in headings:
            level = blocks[i].get("level", 1)
            if type(level) is not int or level < 1 or level > 6:
                diagnostics.append({"code": "INVALID_HEADING_LEVEL", "block_index": i,
                                    "suggestion": "Choose heading level 1 through 6"})
                continue
            if levels and level > levels[-1] + 1:
                diagnostics.append({"code": "HEADING_LEVEL_SKIP", "block_index": i,
                                    "suggestion": "Use contiguous heading levels"})
            levels.append(level)
    for i, block in enumerate(blocks):
        kind = str(block.get("type") or "")
        if kind in TEXT_KINDS and not str(block.get("text") or "").strip():
            diagnostics.append({"code": "EMPTY_TEXT_BLOCK", "block_index": i,
                                "suggestion": "Supply nonempty text or remove the placeholder"})
        if kind in VISUAL_KINDS:
            previous = blocks[i - 1] if i else {}
            following = blocks[i + 1] if i + 1 < len(blocks) else {}
            if not block.get("caption") and (
                previous.get("type") != "caption" and following.get("type") != "caption"
            ):
                diagnostics.append({"code": "UNLABELED_NATIVE_OBJECT", "block_index": i,
                                    "kind": kind,
                                    "suggestion": "Add a user-authored caption or explicit label"})
    summary = {
        "schema": SCHEMA,
        "status": "REVIEW_SUGGESTIONS" if diagnostics else "NO_STATIC_DESIGN_WARNINGS",
        "block_count": len(blocks),
        "diagnostics": diagnostics,
        "mutated_plan": False,
        "native_render_evidence": "NOT_OBSERVED",
        "professional_visual_acceptance": "NOT_ADJUDICATED",
        "authority": "STATIC_AUTHORING_ADVISORY_ONLY",
    }
    summary["receipt_sha256"] = _digest(summary)
    return summary
