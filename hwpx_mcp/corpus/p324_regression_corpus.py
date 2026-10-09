from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from p313r1_fixture_pack import _validate_minimal_hwpx
from p324_story_layer import apply_story_layer_atomic, build_story_layer_map


SCHEMA = "chatgpt-web-hwpx-mcp/story-layer-regression/p3.24/v1"


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _base(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.24 story-layer regression")
    doc.add_paragraph("alpha")
    doc.add_paragraph("beta")
    doc.save_to_path(str(path))
    doc.close()
    _validate_minimal_hwpx(path)


def _fixture(out: Path, fixture_id: str, operations: list[dict]) -> dict:
    root = out / fixture_id
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.hwpx"
    target = root / "target.hwpx"
    _base(source)
    target.write_bytes(source.read_bytes())

    before = build_story_layer_map(source)
    result = apply_story_layer_atomic(
        target,
        operations,
        expected_revision=1,
        current_revision=1,
        validator=None,
    )
    _validate_minimal_hwpx(target)
    after = build_story_layer_map(target)

    return {
        "fixture_id": fixture_id,
        "operations": operations,
        "source_sha256": _sha_file(source),
        "target_sha256": _sha_file(target),
        "source_story_sha256": before["story_layer_sha256"],
        "target_story_sha256": after["story_layer_sha256"],
        "section_count_before": before["section_count"],
        "section_count_after": after["section_count"],
        "story_layer_changed": result["story_layer_changed"],
    }


def materialize_p324_regression_corpus(out_dir: Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixtures = [
        _fixture(
            out,
            "odd-even-header",
            [
                {"op": "set_story_variant", "section_index": 0, "kind": "header", "page_type": "ODD", "text": "Odd Header"},
                {"op": "set_story_variant", "section_index": 0, "kind": "header", "page_type": "EVEN", "text": "Even Header"},
            ],
        ),
        _fixture(
            out,
            "odd-even-footer",
            [
                {"op": "set_story_variant", "section_index": 0, "kind": "footer", "page_type": "ODD", "text": "Odd Footer"},
                {"op": "set_story_variant", "section_index": 0, "kind": "footer", "page_type": "EVEN", "text": "Even Footer"},
            ],
        ),
        _fixture(
            out,
            "first-page-policy",
            [{
                "op": "set_first_page_policy",
                "section_index": 0,
                "hide_header": True,
                "hide_footer": True,
                "hide_page_number": True,
            }],
        ),
        _fixture(
            out,
            "page-number-variants",
            [
                {"op": "set_page_number_variant", "section_index": 0, "target": "footer", "page_type": "ODD", "prefix": "O-"},
                {"op": "set_page_number_variant", "section_index": 0, "target": "footer", "page_type": "EVEN", "prefix": "E-"},
            ],
        ),
        _fixture(
            out,
            "section-story-boundary",
            [{
                "op": "add_section_boundary",
                "after": 0,
                "text": "section two",
                "first_page_policy": {"hide_header": True},
                "stories": [
                    {"kind": "header", "page_type": "BOTH", "text": "Section 2 Header"},
                    {"kind": "footer", "page_type": "ODD", "text": "Section 2 Odd Footer"},
                ],
            }],
        ),
        _fixture(
            out,
            "section-page-start",
            [{
                "op": "set_section_page_start",
                "section_index": 0,
                "number": 7,
                "page_starts_on": "ODD",
            }],
        ),
    ]

    manifest = {
        "schema": SCHEMA,
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "purpose": "PRODUCT_STORY_LAYER_REGRESSION",
        "authority": "STRUCTURAL_STORY_LAYER_AUTHORITY_ONLY",
        "native_batch_status": "DEFERRED_BY_DESIGN",
        "ancestry": "P3.18 document-setup primitives -> P3.24 production story-layer contract",
        "explicit_gate": "synthetic FIRST header/footer story remains EVIDENCE_GATE_CLOSED",
    }
    manifest["corpus_sha256"] = _sha(manifest)
    (out / "p324-regression-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
