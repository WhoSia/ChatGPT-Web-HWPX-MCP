from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from hwpx import HwpxDocument

from p2_document import build_document_map
from p22_formatting import apply_formatting_atomic, build_formatting_map
from p334r2_package_validation import validate_hwpx_package_light


def _env():
    env=dict(os.environ)
    for key in (
        "PYTHONPATH","P12_AUTH_DATABASE_URL","P12_STATE_SECRET",
        "P30_DOCUMENT_DATABASE_URL","P11_OAUTH_PASSPHRASE",
    ):
        env.pop(key,None)
    return env


def _single_paragraph(path:Path,text:str)->str:
    doc=HwpxDocument.new()
    doc.add_paragraph(text)
    doc.save_to_path(str(path))
    doc.close()
    return next(
        p["locator"] for p in build_document_map(path)["paragraphs"]
        if p["text"]==text
    )


def test_p335r1_formatting_map_exposes_letter_spacing(tmp_path:Path):
    path=tmp_path/"spacing.hwpx"
    loc=_single_paragraph(path,"자간 테스트 ABC 漢字")
    apply_formatting_atomic(
        path,
        [{"op":"set_run_format","target":loc,"format":{"letter_spacing":-20}}],
        expected_revision=1,current_revision=1,
        validator=validate_hwpx_package_light,
    )
    mapped=build_formatting_map(path)
    run=next(
        r for p in mapped["paragraphs"] for r in p["runs"]
        if r.get("text")=="자간 테스트 ABC 漢字"
    )
    spacing=(run["style"] or {}).get("letter_spacing_by_script") or {}
    assert spacing.get("hangul")=="-20"
    assert spacing.get("latin")=="-20"
    assert spacing.get("hanja")=="-20"


def test_p335r1_native_pack_direct_script_without_oauth_env(tmp_path:Path):
    out=tmp_path/"pack"
    subprocess.run(
        [
            sys.executable,
            "scripts/p335r1_materialize_native_typography_pack.py",
            "--out",str(out),
        ],
        check=True,
        env=_env(),
    )
    manifest=json.loads((out/"capture-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["cases"])==10
    assert [c["id"] for c in manifest["cases"][:5]]==[
        "spacing-neg50","spacing-neg20","spacing-zero","spacing-pos20","spacing-pos100"
    ]
    for case in manifest["cases"]:
        assert (out/case["id"]/"source.hwpx").exists()
        assert (out/case["id"]/"target.hwpx").exists()
