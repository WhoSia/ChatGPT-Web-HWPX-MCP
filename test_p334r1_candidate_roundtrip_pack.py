from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from p323_advanced_tables import build_advanced_table_map


def test_candidate_roundtrip_materializer_builds_three_structurally_valid_outputs(tmp_path: Path):
    out = tmp_path / "pack"
    subprocess.run(
        [
            sys.executable,
            "scripts/p334r1_materialize_candidate_roundtrip_pack.py",
            "--out",
            str(out),
        ],
        check=True,
    )
    manifest = json.loads((out / "roundtrip-manifest.json").read_text(encoding="utf-8"))
    assert [case["id"] for case in manifest["cases"]] == [
        "candidate-basic-left-1",
        "candidate-nonuniform-right-1",
        "candidate-merged-left-1",
    ]

    for case in manifest["cases"]:
        path = out / case["id"] / "candidate-before-hancom.hwpx"
        assert path.exists()
        mapped = build_advanced_table_map(path)
        table = mapped["tables"][0]
        assert table["rows"] == 3
        assert table["cols"] == 4

    nonuniform = build_advanced_table_map(
        out / "candidate-nonuniform-right-1" / "candidate-before-hancom.hwpx"
    )["tables"][0]
    row1 = [c for c in nonuniform["cells"] if c["row"] == 1]
    assert [c["width"] for c in row1] == [12000, 18000, 18000, 24000]

    merged = build_advanced_table_map(
        out / "candidate-merged-left-1" / "candidate-before-hancom.hwpx"
    )["tables"][0]
    header = next(c for c in merged["cells"] if c["row"] == 0 and c["col"] == 0)
    assert header["col_span"] == 3
    assert header["width"] == 36000
