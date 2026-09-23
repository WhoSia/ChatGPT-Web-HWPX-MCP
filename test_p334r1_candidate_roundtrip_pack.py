from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from p323_advanced_tables import build_advanced_table_map


def test_candidate_roundtrip_materializer_builds_three_structurally_valid_outputs(tmp_path: Path):
    out = tmp_path / "pack"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    subprocess.run(
        [
            sys.executable,
            "scripts/p334r1_materialize_candidate_roundtrip_pack.py",
            "--out",
            str(out),
        ],
        check=True,
        env=env,
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


def test_candidate_roundtrip_analyzer_runs_by_direct_script_path_without_pythonpath(tmp_path: Path):
    out = tmp_path / "pack"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    subprocess.run(
        [
            sys.executable,
            "scripts/p334r1_materialize_candidate_roundtrip_pack.py",
            "--out",
            str(out),
        ],
        check=True,
        env=env,
    )

    manifest = json.loads((out / "roundtrip-manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        case_dir = out / case["id"]
        before = case_dir / "candidate-before-hancom.hwpx"
        after = case_dir / "candidate-after-hancom.hwpx"
        after.write_bytes(before.read_bytes())

    subprocess.run(
        [
            sys.executable,
            "scripts/p334r1_analyze_candidate_roundtrip.py",
            "--pack",
            str(out),
        ],
        check=True,
        env=env,
    )
    summary = json.loads((out / "roundtrip-analysis-summary.json").read_text(encoding="utf-8"))
    assert summary["pass"] is True
    assert summary["cases_missing"] == []
    assert summary["cases_structure_failed"] == []
