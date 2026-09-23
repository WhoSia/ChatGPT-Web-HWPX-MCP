from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from p327_diagram_composition import build_diagram_composition_map


def _env():
    env=dict(os.environ)
    env.pop("PYTHONPATH",None)
    return env


def test_p334r3_materializer_direct_script(tmp_path: Path):
    out=tmp_path/"pack"
    subprocess.run([
        sys.executable,
        "scripts/p334r3_materialize_group_ungroup_pack.py",
        "--out",str(out),
    ],check=True,env=_env())
    manifest=json.loads((out/"capture-manifest.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in manifest["cases"]]==[
        "group-two-rectangles",
        "ungroup-existing-group",
        "ungroup-translated-group",
    ]
    group_src=out/"group-two-rectangles"/"source.hwpx"
    grouped=build_diagram_composition_map(group_src)
    assert grouped["group_count"]==0
    assert grouped["top_level_count"]==2
    for cid in ("ungroup-existing-group","ungroup-translated-group"):
        mapped=build_diagram_composition_map(out/cid/"source.hwpx")
        assert mapped["group_count"]==1
        assert mapped["top_level_count"]==1
        assert len(mapped["groups"][0]["members"])==2
