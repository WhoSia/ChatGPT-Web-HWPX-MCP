from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from hwpx import HwpxDocument

import server
from p2_document import build_document_map
from p322_review_workflow import apply_review_workflow_atomic, build_review_workflow_map


HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
CONFIG_NS = "urn:oasis:names:tc:opendocument:xmlns:config:1.0"
HH = f"{{{HH_NS}}}"
CONFIG = f"{{{CONFIG_NS}}"


def _make(path: Path, text: str) -> str:
    doc = HwpxDocument.new()
    doc.add_paragraph("P3.34-R2 implementation candidate")
    doc.add_paragraph(text)
    doc.save_to_path(str(path))
    doc.close()
    return next(
        item["locator"]
        for item in build_document_map(path)["paragraphs"]
        if item["text"] == text
    )


def _body_texts(path: Path) -> list[str]:
    return [
        item["text"]
        for item in build_document_map(path)["paragraphs"]
        if item.get("body_paragraph_index") is not None
    ]


def _protect_synthetically_for_refusal_test(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as zf:
        infos = zf.infolist()
        data = {info.filename: zf.read(info.filename) for info in infos}

    root = etree.fromstring(data["Contents/header.xml"])
    config = root.find(f".//{HH}trackchageConfig")
    assert config is not None
    node = etree.SubElement(config, f"{CONFIG}config-item-set")
    node.set("name", "TrackChangePasswordInfo")
    child = etree.SubElement(node, f"{CONFIG}config-item")
    child.set("name", "algorithm-name")
    child.set("type", "string")
    child.text = "SHA1"
    data["Contents/header.xml"] = etree.tostring(root, encoding="utf-8", xml_declaration=False)

    tmp = path.with_suffix(".rewrite.hwpx")
    with zipfile.ZipFile(tmp, "w") as zf:
        for info in infos:
            zf.writestr(info, data[info.filename])
    os.replace(tmp, path)


@pytest.mark.parametrize(
    ("author_op", "resolution_op", "expected"),
    [
        (
            {"op": "tracked_insert", "text": " +inserted"},
            "accept_all_tracked_changes",
            "alpha base +inserted",
        ),
        (
            {"op": "tracked_insert", "text": " +inserted"},
            "reject_all_tracked_changes",
            "alpha base",
        ),
        (
            {"op": "tracked_delete", "match": "remove "},
            "accept_all_tracked_changes",
            "beta target",
        ),
        (
            {"op": "tracked_delete", "match": "remove "},
            "reject_all_tracked_changes",
            "beta remove target",
        ),
        (
            {"op": "tracked_replace", "old": "old", "new": "new"},
            "accept_all_tracked_changes",
            "gamma new value",
        ),
        (
            {"op": "tracked_replace", "old": "old", "new": "new"},
            "reject_all_tracked_changes",
            "gamma old value",
        ),
    ],
)
def test_unprotected_accept_reject_all_matches_native_semantics(
    tmp_path: Path,
    author_op: dict,
    resolution_op: str,
    expected: str,
):
    if "insert" in author_op["op"]:
        base = "alpha base"
    elif "delete" in author_op["op"]:
        base = "beta remove target"
    else:
        base = "gamma old value"

    path = tmp_path / "doc.hwpx"
    locator = _make(path, base)
    op = {
        **author_op,
        "paragraph": locator,
        "author": "P3.34-R2 Test",
        "date": "2026-09-23T12:00:00Z",
    }
    apply_review_workflow_atomic(
        path,
        [op],
        expected_revision=1,
        current_revision=1,
        validator=server.validate_hwpx_package,
    )
    tracked = build_review_workflow_map(path)
    assert tracked["counts"]["tracked_changes"] in {1, 2}

    result = apply_review_workflow_atomic(
        path,
        [{"op": resolution_op}],
        expected_revision=2,
        current_revision=2,
        validator=server.validate_hwpx_package,
    )
    assert result["authority"] == "P3.34-R2_CANDIDATE_UNPROTECTED_ACCEPT_REJECT_ALL"
    assert result["after_counts"]["tracked_changes"] == 0
    assert result["after_counts"]["track_change_authors"] == 0
    assert expected in _body_texts(path)
    assert server.validate_hwpx_package(path)["ok"] is True


def test_protected_resolution_fails_closed_without_mutating_bytes(tmp_path: Path):
    path = tmp_path / "protected.hwpx"
    locator = _make(path, "delta protected base")
    apply_review_workflow_atomic(
        path,
        [{
            "op": "tracked_insert",
            "paragraph": locator,
            "text": " +protected",
            "author": "P3.34-R2 Test",
        }],
        expected_revision=1,
        current_revision=1,
    )
    _protect_synthetically_for_refusal_test(path)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="protection is active"):
        apply_review_workflow_atomic(
            path,
            [{"op": "accept_all_tracked_changes"}],
            expected_revision=2,
            current_revision=2,
        )
    assert path.read_bytes() == before


def test_resolution_cannot_be_mixed_with_other_review_operations(tmp_path: Path):
    path = tmp_path / "mixed.hwpx"
    locator = _make(path, "alpha base")
    apply_review_workflow_atomic(
        path,
        [{
            "op": "tracked_insert",
            "paragraph": locator,
            "text": " +inserted",
        }],
        expected_revision=1,
        current_revision=1,
    )
    before = path.read_bytes()
    with pytest.raises(ValueError, match="only operation"):
        apply_review_workflow_atomic(
            path,
            [
                {"op": "accept_all_tracked_changes"},
                {"op": "set_document_metadata", "title": "should not happen"},
            ],
            expected_revision=2,
            current_revision=2,
        )
    assert path.read_bytes() == before
