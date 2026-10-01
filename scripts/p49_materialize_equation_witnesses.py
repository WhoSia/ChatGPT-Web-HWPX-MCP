from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

from p49_equation_witnesses import alignment_witness_contract


def _save_fixture(path: Path, label: str, script: str) -> dict:
    doc = HwpxDocument.new()
    anchor = doc.add_paragraph(label, inherit_style=False)
    doc.shapes.add_equation(script, paragraph=anchor, base_unit=1100)
    buf = io.BytesIO()
    doc.save_to_stream(buf)
    raw = buf.getvalue()
    safety = validate_editor_open_safety(raw)
    if not safety.ok:
        raise RuntimeError(f"editor-open safety failed for {path.name}: {safety.issues}")
    path.write_bytes(raw)
    return {
        "filename": path.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "script": script,
        "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        "editor_open_safety": True,
    }


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    contract = alignment_witness_contract()
    rows = []
    for spec in contract["variants"]:
        filename = f"p49-{spec['variant_id']}-alignment-witness.hwpx"
        fixture = _save_fixture(
            out / filename,
            f"P4.9 {spec['variant_id']} {spec['expected_alignment']} witness",
            spec["eqedit_script"],
        )
        rows.append({
            "variant_id": spec["variant_id"],
            "expected_alignment": spec["expected_alignment"],
            "fixture": fixture,
        })

    result = {
        "phase": "P4.9",
        "schema": contract["schema"],
        "witness_sha256": contract["witness_sha256"],
        "witness_count": len(rows),
        "rows": rows,
        "authority": "STRUCTURAL_WITNESS_PACKET_ONLY_NATIVE_HANCOM_VISUAL_ADJUDICATION_PENDING",
    }
    (out / "p49-equation-alignment-witness.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/p49-equation-alignment-witness"))
    args = parser.parse_args()
    run(args.out)
