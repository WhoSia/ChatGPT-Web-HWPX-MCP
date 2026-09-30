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

from p47_native_authoring import capture_pack_contract, equation_render_frontier


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


def main(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    frontier = equation_render_frontier()
    rows = []
    for spec in frontier["candidates"]:
        row = {"candidate_id": spec["candidate_id"], "fixtures": {}}
        for variant in ("control", "candidate"):
            filename = f"p47-{spec['candidate_id']}-{variant}.hwpx"
            row["fixtures"][variant] = _save_fixture(
                out / filename,
                f"P4.7 {spec['candidate_id']} {variant}",
                spec[f"{variant}_script"],
            )
        rows.append(row)
    result = {
        "phase": "P4.7",
        "product": "0.33.0-p4.7",
        "frontier_sha256": frontier["frontier_sha256"],
        "capture_contract": capture_pack_contract(),
        "candidates": rows,
        "authority": "STRUCTURAL_CAPTURE_PACKET_ONLY_NO_HANCOM_RENDER_CLAIM",
    }
    (out / "p47-capture-manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/p47-equation-capture-pack"))
    args = parser.parse_args()
    main(args.out)
