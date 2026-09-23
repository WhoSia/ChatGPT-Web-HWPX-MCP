from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from p2_document import build_document_map
from p322_review_workflow import build_review_workflow_map


def _env():
    env = dict(os.environ)
    for key in (
        "PYTHONPATH",
        "P12_AUTH_DATABASE_URL",
        "P12_STATE_SECRET",
        "P30_DOCUMENT_DATABASE_URL",
        "P11_OAUTH_PASSPHRASE",
    ):
        env.pop(key, None)
    return env


def test_p334r2_candidate_roundtrip_materializer_direct_script(tmp_path: Path):
    out = tmp_path / "pack"
    subprocess.run(
        [
            sys.executable,
            "scripts/p334r2_materialize_candidate_roundtrip_pack.py",
            "--out",
            str(out),
        ],
        check=True,
        env=_env(),
    )
    manifest = json.loads((out / "roundtrip-manifest.json").read_text(encoding="utf-8"))
    assert [case["id"] for case in manifest["cases"]] == [
        "candidate-insert-accept",
        "candidate-delete-reject",
        "candidate-replace-accept",
        "candidate-replace-reject",
    ]
    for case in manifest["cases"]:
        path = out / case["id"] / "candidate-before-hancom.hwpx"
        assert path.exists()
        review = build_review_workflow_map(path)
        assert review["counts"]["tracked_changes"] == 0
        assert review["counts"]["track_change_authors"] == 0
        body = [
            item["text"]
            for item in build_document_map(path)["paragraphs"]
            if item.get("body_paragraph_index") is not None
        ]
        assert case["expected"] in body


def test_p334r2_candidate_roundtrip_analyzer_direct_script_on_unchanged_copies(tmp_path: Path):
    out = tmp_path / "pack"
    env = _env()
    subprocess.run(
        [
            sys.executable,
            "scripts/p334r2_materialize_candidate_roundtrip_pack.py",
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
            "scripts/p334r2_analyze_candidate_roundtrip.py",
            "--pack",
            str(out),
        ],
        check=True,
        env=env,
    )
    summary = json.loads((out / "analysis-summary.json").read_text(encoding="utf-8"))
    assert summary["pass"] is True
    assert summary["failures"] == []
