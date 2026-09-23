#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hwpx import HwpxDocument

from p27_tables import _save_document
from p323_advanced_tables import build_advanced_table_map
from p334r1_column_insertion import apply_bounded_column_insertion


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_source(path: Path, *, prefix: str, widths: list[int] | None = None, merged: bool = False) -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(rows=3, cols=3, width=54000)
    for r in range(3):
        for c in range(3):
            table.set_cell_text(r, c, f"{prefix}-R{r+1}C{c+1}", logical=True)
    if widths:
        for r in range(3):
            for c, width in enumerate(widths):
                table.cell(r, c).set_size(width=width)
    if merged:
        table.merge_cells(0, 0, 0, 1)
        table.set_cell_text(0, 0, f"{prefix}-HEADER", logical=True)
    doc.save_to_path(path)


def apply_candidate(path: Path, *, direction: str) -> dict:
    mapped = build_advanced_table_map(path)
    payload = mapped["tables"][0]
    anchor = next(c for c in payload["cells"] if c["row"] == 1 and c["col"] == 1)
    doc = HwpxDocument.open(str(path))
    try:
        receipt = apply_bounded_column_insertion(
            doc.tables.all[0],
            payload,
            {
                "op": "insert_column_native_bounded",
                "cell": anchor["locator"],
                "direction": direction,
                "count": 1,
            },
        )
        _save_document(doc, path, path)
        return receipt
    finally:
        doc.close()


CASES = [
    {
        "id": "candidate-basic-left-1",
        "prefix": "IL",
        "direction": "LEFT",
        "widths": None,
        "merged": False,
    },
    {
        "id": "candidate-nonuniform-right-1",
        "prefix": "IR",
        "direction": "RIGHT",
        "widths": [12000, 18000, 24000],
        "merged": False,
    },
    {
        "id": "candidate-merged-left-1",
        "prefix": "IM",
        "direction": "LEFT",
        "widths": None,
        "merged": True,
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/p334r1-candidate-roundtrip-pack")
    args = ap.parse_args()
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r1/candidate-roundtrip/v1",
        "phase": "P3.34-R1",
        "purpose": "Hancom open-save acceptance of implementation-generated count=1 column insertion",
        "cases": [],
    }

    for spec in CASES:
        d = root / spec["id"]
        d.mkdir(parents=True, exist_ok=True)
        source = d / "candidate-before-hancom.hwpx"
        resaved = d / "candidate-after-hancom.hwpx"
        if resaved.exists():
            resaved.unlink()

        build_source(
            source,
            prefix=spec["prefix"],
            widths=spec["widths"],
            merged=spec["merged"],
        )
        receipt = apply_candidate(source, direction=spec["direction"])
        after_map = build_advanced_table_map(source)
        table = after_map["tables"][0]

        item = {
            "id": spec["id"],
            "direction": spec["direction"],
            "source": str(source),
            "source_sha256": sha256(source),
            "candidate_receipt": receipt,
            "candidate_table": {
                "rows": table["rows"],
                "cols": table["cols"],
                "cells": [
                    {
                        "row": c["row"],
                        "col": c["col"],
                        "row_span": c["row_span"],
                        "col_span": c["col_span"],
                        "width": c["width"],
                        "height": c["height"],
                        "text": c["text"],
                    }
                    for c in table["cells"]
                ],
            },
            "user_action_ko": "한컴에서 파일을 연 뒤 아무 내용도 수정하지 말고 Ctrl+S로 저장하고 창을 닫으세요.",
        }
        (d / "case.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest["cases"].append(item)

    (root / "roundtrip-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"P3.34-R1 materialized {len(manifest['cases'])} implementation-generated round-trip fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
