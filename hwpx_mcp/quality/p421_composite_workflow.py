"""P4.21 real composite authoring and bounded, revisioned editing.

Reuses the proven P3.21 native composer and P4.20 quality court. No
AI-generated repair text, silent document mutation or claimed visual authority.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

from hwpx_mcp.document.p2_document import apply_text_edits_atomic
from hwpx_mcp.document.p321_document_composer import compose_document_plan
from hwpx_mcp.document.p334r2_package_validation import validate_hwpx_package_light
from hwpx_mcp.quality.p420_document_quality import judge_document_quality
from hwpx_mcp.quality.p421_professional_authoring_review import review_authoring_plan


def _object_minima(plan: Mapping) -> dict[str, int]:
    kinds = {"table": "tables", "equation": "equations", "picture": "pictures"}
    minimums: dict[str, int] = {}
    for block in plan.get("blocks", []):
        k = kinds.get(block.get("type"))
        if k:
            minimums[k] = minimums.get(k, 0) + 1
    footnotes = sum(x.get("op") == "add_footnote"
                    for x in (plan.get("annotations") or []))
    if footnotes:
        minimums["footnotes"] = footnotes
    return minimums


def compose_reviewed_document(path: Path, plan: dict) -> dict:
    """Create native composite HWPX and demand preservation of requested objects."""
    review = review_authoring_plan(plan)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.stem + ".p421-", suffix=".hwpx",
                                dir=str(path.parent))
    os.close(fd)
    candidate = Path(name)
    try:
        composition = compose_document_plan(
            candidate, plan, validator=validate_hwpx_package_light
        )
        quality = judge_document_quality(
            candidate, minimum_counts=_object_minima(plan)
        )
        if quality["issues"]:
            raise ValueError("COMPOSITE_QUALITY_REQUIREMENTS_FAILED: " +
                             str(quality["issues"]))
        os.replace(candidate, path)
        return {"composition": composition, "professional_review": review,
                "quality": quality, "native_visual_authority": "NOT_OBSERVED"}
    finally:
        candidate.unlink(missing_ok=True)


def edit_reviewed_document(
    path: Path,
    edits: Sequence[dict],
    *,
    expected_revision: int,
    current_revision: int,
    minimum_counts: Mapping[str, int],
) -> dict:
    """Text-only edits, preserving source and native component counts.

    Caller must author every replacement string. A failed quality court reports
    the defect but does not rewrite content or assert native visualization.
    """
    if not edits or len(edits) > 2:
        raise ValueError("1 or 2 explicit text edits required")
    if any(x.get("op") != "replace_paragraph_text" or
           not isinstance(x.get("text"), str) or
           not x["text"].strip() for x in edits):
        raise ValueError("only explicit nonempty paragraph replacements allowed")
    path = Path(path)
    before = judge_document_quality(path, minimum_counts=minimum_counts)
    if before["issues"]:
        raise ValueError("BASELINE_QUALITY_FAILED")
    fd, name = tempfile.mkstemp(prefix=path.stem + ".p421-edit-",
                                suffix=".hwpx", dir=str(path.parent))
    os.close(fd)
    candidate = Path(name)
    try:
        shutil.copy2(path, candidate)
        mutation = apply_text_edits_atomic(
            candidate, list(edits),
            expected_revision=expected_revision,
            current_revision=current_revision,
            validator=validate_hwpx_package_light,
        )
        after = judge_document_quality(candidate, minimum_counts=minimum_counts,
                                       baseline_path=path)
        if after["issues"]:
            raise ValueError("EDIT_QUALITY_REQUIREMENTS_FAILED: " +
                             str(after["issues"]))
        os.replace(candidate, path)
        return {
            "mutation": mutation, "before": before, "after": after,
            "semantic_preservation": "USER_AUTHORED_TEXT_CHANGE_ONLY",
            "native_visual_authority": "NOT_OBSERVED",
            "status": "PASS_STRUCTURE_HOLD_VISUAL",
        }
    finally:
        candidate.unlink(missing_ok=True)
