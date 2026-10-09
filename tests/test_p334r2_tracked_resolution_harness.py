from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from p322_review_workflow import build_review_workflow_map


def _env_without_pythonpath():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def test_p334r2_materializer_builds_seven_direct_script_fixtures(tmp_path: Path):
    out = tmp_path / "pack"
    subprocess.run(
        [
            sys.executable,
            "scripts/p334r2_materialize_tracked_resolution_pack.py",
            "--out",
            str(out),
        ],
        check=True,
        env=_env_without_pythonpath(),
    )

    manifest = json.loads((out / "capture-manifest.json").read_text(encoding="utf-8"))
    assert [case["id"] for case in manifest["cases"]] == [
        "insert-accept",
        "insert-reject",
        "delete-accept",
        "delete-reject",
        "replace-accept",
        "replace-reject",
        "protection-enable",
    ]
    for case in manifest["cases"]:
        source = out / case["id"] / "source.hwpx"
        target = out / case["id"] / "target.hwpx"
        assert source.exists() and target.exists()
        assert source.read_bytes() == target.read_bytes()
        mapped = build_review_workflow_map(source)
        assert mapped["counts"]["track_change_authors"] == 1
        expected_changes = 2 if case["op"] == "tracked_replace" else 1
        assert mapped["counts"]["tracked_changes"] == expected_changes


def test_p334r2_analyzer_direct_script_fails_closed_on_untouched_targets(tmp_path: Path):
    out = tmp_path / "pack"
    env = _env_without_pythonpath()
    subprocess.run(
        [
            sys.executable,
            "scripts/p334r2_materialize_tracked_resolution_pack.py",
            "--out",
            str(out),
        ],
        check=True,
        env=env,
    )
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/p334r2_analyze_tracked_resolution.py",
            "--pack",
            str(out),
        ],
        check=False,
        env=env,
    )
    assert proc.returncode == 2
    summary = json.loads((out / "analysis-summary.json").read_text(encoding="utf-8"))
    assert summary["all_resolution_semantics_pass"] is False
    assert summary["protection_encoding_observed"] is False
    assert len(summary["failures"]) == 7
