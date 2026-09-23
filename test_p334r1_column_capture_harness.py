from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from hwpx import HwpxDocument


def test_p334r1_materializer_builds_four_editor_safe_sources(tmp_path: Path):
    out = tmp_path / "pack"
    subprocess.run(
        [
            sys.executable,
            "scripts/p334r1_materialize_column_insertion_pack.py",
            "--out",
            str(out),
        ],
        check=True,
    )

    manifest = json.loads((out / "capture-manifest.json").read_text(encoding="utf-8"))
    assert [case["id"] for case in manifest["cases"]] == [
        "basic-left-1",
        "basic-right-2",
        "merged-header-left-1",
        "nonuniform-right-1",
    ]

    for case in manifest["cases"]:
        source = out / case["id"] / "source.hwpx"
        assert source.exists()
        assert source.stat().st_size > 0
        doc = HwpxDocument.open(source)
        tables = list(doc.tables)
        assert len(tables) == 1
        assert tables[0].row_count == 3
        assert tables[0].column_count == 3

    merged = HwpxDocument.open(out / "merged-header-left-1" / "source.hwpx")
    first_table = list(merged.tables)[0]
    header = first_table.get_cell_map()[0]
    assert header[0].span[1] == 2
