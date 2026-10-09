"""P4.20 document quality court: inspect measurable native HWPX requirements.

No scalar beauty score, no implied Hancom rendering, no automatic release.
A package can be structurally excellent and still lack native visual evidence.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping, Sequence
from xml.etree.ElementTree import ParseError

from hwpx_mcp.document.p2_document import build_document_map
from hwpx_mcp.document.p28_tables import build_table_map
from hwpx_mcp.document.p29_objects import build_object_map
from hwpx_mcp.document.p210_equations import build_equation_map
from hwpx_mcp.document.p320_annotation_apparatus import build_annotation_apparatus_map
from hwpx_mcp.document.p334r2_package_validation import validate_hwpx_package_light
from hwpx_mcp.quality.p420_render_readiness import assess_render_readiness


MEASURABLE = frozenset({
    "sections", "paragraphs", "tables", "equations", "pictures", "footnotes",
})
SCHEMA = "chatgpt-web-hwpx-mcp/p420/document-quality-court/v1"


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _measure(path: Path) -> dict:
    validation = validate_hwpx_package_light(path)
    doc = build_document_map(path)
    annotations = build_annotation_apparatus_map(path)
    return {
        "package": validation,
        "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "structure_sha256": doc["structure_sha256"],
        "semantic_sha256": doc["semantic_sha256"],
        "paragraph_texts": [row["text"] for row in doc["paragraphs"]],
        "counts": {
            "sections": len(doc["sections"]),
            "paragraphs": len(doc["paragraphs"]),
            "tables": len(build_table_map(path)["tables"]),
            "equations": len(build_equation_map(path)["equations"]),
            "pictures": len(build_object_map(path)["pictures"]),
            "footnotes": int(annotations["counts"]["footnotes"]),
        },
    }


def judge_document_quality(
    path: Path, *,
    minimum_counts: Mapping[str, int] | None = None,
    required_texts: Sequence[str] = (),
    baseline_path: Path | None = None,
    capture: dict | None = None,
    observation: dict | None = None,
) -> dict:
    """Evaluate independent content/structure/native-evidence axes.

    When baseline_path is supplied, *exact structure digest* and all native
    object counts must survive editing. This is a strict text-only-edit test,
    not a general-purpose layout equivalence theorem.
    """
    path = Path(path)
    minimums = dict(minimum_counts or {})
    if set(minimums) - MEASURABLE:
        raise ValueError(f"unsupported measured count: {sorted(set(minimums) - MEASURABLE)}")
    if any(type(v) is not int or v < 0 for v in minimums.values()):
        raise ValueError("minimum counts must be nonnegative integers")
    if any(not isinstance(text, str) or not text for text in required_texts):
        raise ValueError("required_texts must contain nonempty strings")

    try:
        observed = _measure(path)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ParseError) as exc:
        result = {
            "schema": SCHEMA, "status": "FAIL_PACKAGE",
            "release_eligible": False,
            "issues": [{"code": "PACKAGE_INVALID", "detail": str(exc)}],
            "authority": "STRUCTURAL_INSPECTION_ONLY",
        }
        result["receipt_sha256"] = _sha(result)
        return result

    issues = []
    for name, threshold in sorted(minimums.items()):
        if observed["counts"][name] < threshold:
            issues.append({
                "code": "MISSING_REQUIRED_OBJECT",
                "kind": name, "minimum": threshold,
                "observed": observed["counts"][name],
            })
    for text in required_texts:
        if not any(text in paragraph for paragraph in observed["paragraph_texts"]):
            issues.append({
                "code": "MISSING_REQUIRED_TEXT",
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })

    baseline_sha256 = None
    if baseline_path is not None:
        baseline = _measure(Path(baseline_path))
        baseline_sha256 = baseline["document_sha256"]
        if baseline["structure_sha256"] != observed["structure_sha256"]:
            issues.append({"code": "STRUCTURE_DIGEST_DRIFT"})
        for name in ("tables", "equations", "pictures", "footnotes", "sections"):
            if baseline["counts"][name] != observed["counts"][name]:
                issues.append({
                    "code": "NATIVE_COMPONENT_COUNT_DRIFT", "kind": name,
                    "before": baseline["counts"][name],
                    "after": observed["counts"][name],
                })

    evidence = None
    if not issues:
        evidence = assess_render_readiness(
            artifact_sha256=observed["document_sha256"],
            structural_valid=True,
            capture=capture, observation=observation,
        )

    result = {
        "schema": SCHEMA,
        "status": "FAIL_REQUIREMENTS" if issues else "PASS_STRUCTURE_HOLD_RELEASE",
        "release_eligible": False,
        "document_sha256": observed["document_sha256"],
        "baseline_sha256": baseline_sha256,
        "semantic_sha256": observed["semantic_sha256"],
        "structure_sha256": observed["structure_sha256"],
        "counts": observed["counts"],
        "issues": issues,
        "native_render": evidence,
        "authority": "MEASURED_HWPX_STRUCTURAL_QUALITY_NOT_NATIVE_VISUAL_CERTIFICATION",
    }
    result["receipt_sha256"] = _sha(result)
    return result
