#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx import HwpxDocument


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fill_table(table, rows: int, cols: int, prefix: str) -> None:
    for r in range(rows):
        for c in range(cols):
            table.set_cell_text(r, c, f"{prefix}-R{r+1}C{c+1}", logical=True)


def set_column_widths(table, widths: list[int], rows: int) -> None:
    for r in range(rows):
        for c, width in enumerate(widths):
            table.cell(r, c).set_size(width=width)


def build_basic(path: Path, *, prefix: str, widths: list[int] | None = None) -> None:
    doc = HwpxDocument.new()
    section = doc.sections[0]
    table = doc.add_table(rows=3, cols=3, section=section, width=54000)
    fill_table(table, 3, 3, prefix)
    if widths:
        set_column_widths(table, widths, 3)
    doc.save_to_path(path)


def build_merged(path: Path) -> None:
    doc = HwpxDocument.new()
    section = doc.sections[0]
    table = doc.add_table(rows=3, cols=3, section=section, width=54000)
    fill_table(table, 3, 3, "M")
    table.merge_cells(0, 0, 0, 1)
    table.set_cell_text(0, 0, "M-HEADER-C1C2", logical=True)
    doc.save_to_path(path)


CASES = [
    {
        "id": "basic-left-1",
        "builder": "basic",
        "manual": {
            "anchor_text": "A-R2C2",
            "direction": "left",
            "count": 1,
            "instruction_ko": "A-R2C2 셀에 커서를 놓고 Alt+Insert → 왼쪽에 칸 추가하기 → 줄/칸 수 1 → 추가",
        },
    },
    {
        "id": "basic-right-2",
        "builder": "basic2",
        "manual": {
            "anchor_text": "B-R2C2",
            "direction": "right",
            "count": 2,
            "instruction_ko": "B-R2C2 셀에 커서를 놓고 Alt+Insert → 오른쪽에 칸 추가하기 → 줄/칸 수 2 → 추가",
        },
    },
    {
        "id": "merged-header-left-1",
        "builder": "merged",
        "manual": {
            "anchor_text": "M-R2C2",
            "direction": "left",
            "count": 1,
            "instruction_ko": "M-R2C2 셀에 커서를 놓고 Alt+Insert → 왼쪽에 칸 추가하기 → 줄/칸 수 1 → 추가",
        },
    },
    {
        "id": "nonuniform-right-1",
        "builder": "nonuniform",
        "manual": {
            "anchor_text": "W-R2C2",
            "direction": "right",
            "count": 1,
            "instruction_ko": "W-R2C2 셀에 커서를 놓고 Alt+Insert → 오른쪽에 칸 추가하기 → 줄/칸 수 1 → 추가",
        },
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/p334r1-column-insertion-pack")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from capture_runtime import attach_capture_runtime
    attach_capture_runtime(out)

    manifest = {
        "schema": "chatgpt-web-hwpx-mcp/p3.34-r1/column-insertion-capture/v1",
        "phase": "P3.34-R1",
        "purpose": "Hancom-native column insertion before/after evidence",
        "cases": [],
    }

    for case in CASES:
        d = out / case["id"]
        d.mkdir(parents=True, exist_ok=True)
        source = d / "source.hwpx"
        target = d / "target.hwpx"
        if target.exists():
            target.unlink()

        if case["builder"] == "basic":
            build_basic(source, prefix="A")
        elif case["builder"] == "basic2":
            build_basic(source, prefix="B")
        elif case["builder"] == "merged":
            build_merged(source)
        elif case["builder"] == "nonuniform":
            build_basic(source, prefix="W", widths=[12000, 18000, 24000])
        else:
            raise RuntimeError(case["builder"])

        item = {
            "id": case["id"],
            "source": str(source),
            "source_sha256": sha256(source),
            "manual": case["manual"],
            "expected_observation_only": True,
        }
        (d / "case.json").write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["cases"].append(item)

    (out / "capture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"P3.34-R1 materialized {len(manifest['cases'])} source fixtures at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
