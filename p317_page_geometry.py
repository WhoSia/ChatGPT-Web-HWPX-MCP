from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from lxml import etree


PAGE_SCHEMA = "chatgpt-web-hwpx-mcp/page-geometry/p3.17/v1"
MARGIN_KEYS = {"left", "right", "top", "bottom", "header", "footer", "gutter"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _section_names(archive: zipfile.ZipFile) -> list[str]:
    names = [
        name for name in archive.namelist()
        if name.startswith("Contents/section") and name.endswith(".xml")
    ]
    return sorted(
        names,
        key=lambda name: int(name.rsplit("section", 1)[1].split(".xml", 1)[0])
        if name.rsplit("section", 1)[1].split(".xml", 1)[0].isdigit()
        else 10**9,
    )


def _page_nodes(root: etree._Element) -> tuple[etree._Element, etree._Element]:
    page_pr = next((node for node in root.iter() if _local(node.tag) == "pagePr"), None)
    if page_pr is None:
        raise ValueError("section has no pagePr")
    margin = next(
        (
            node for node in page_pr.iter()
            if node is not page_pr and _local(node.tag) in {"margin", "pageMargin"}
        ),
        None,
    )
    if margin is None:
        raise ValueError("section pagePr has no margin")
    return page_pr, margin


def build_page_geometry_map(path: Path) -> dict:
    sections = []
    with zipfile.ZipFile(path, "r") as archive:
        for section_index, name in enumerate(_section_names(archive)):
            root = etree.fromstring(archive.read(name))
            page_pr, margin = _page_nodes(root)
            sections.append({
                "section_index": section_index,
                "section": name,
                "page_pr": dict(sorted(page_pr.attrib.items())),
                "margin": dict(sorted(margin.attrib.items())),
            })
    result = {
        "schema": PAGE_SCHEMA,
        "sections": sections,
        "section_count": len(sections),
    }
    result["page_geometry_sha256"] = _sha(sections)
    return result


def _bounded(value: Any, name: str) -> int:
    number = int(value)
    if number < 0 or number > 10_000_000:
        raise ValueError(f"{name} is outside admitted HWPUNIT bounds")
    return number


def apply_page_geometry_edits_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if expected_revision != current_revision:
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations or len(operations) > 32:
        raise ValueError("Page-geometry transaction requires 1..32 operations")

    before = build_page_geometry_map(path)
    section_count = before["section_count"]
    normalized: list[dict] = []
    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each page-geometry operation must be an object")
        if raw.get("op") != "set_page_margin":
            raise ValueError(f"Unsupported page-geometry operation: {raw.get('op')}")
        section_index = int(raw.get("section_index", 0))
        if section_index < 0 or section_index >= section_count:
            raise ValueError("section_index is outside the document")
        values = {
            key: _bounded(raw[key], f"margin {key}")
            for key in MARGIN_KEYS
            if key in raw
        }
        if not values:
            raise ValueError("set_page_margin requires at least one margin field")
        normalized.append({
            "op": "set_page_margin",
            "section_index": section_index,
            "values": values,
        })

    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p317-page-",
        suffix=".hwpx",
        dir=str(path.parent),
    )
    os.close(fd)
    candidate = Path(tmp_name)
    validation = None
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(candidate, "w") as target:
            sections = _section_names(source)
            by_name: dict[str, list[dict]] = {}
            for op in normalized:
                by_name.setdefault(sections[op["section_index"]], []).append(op)
            for info in source.infolist():
                payload = source.read(info.filename)
                edits = by_name.get(info.filename)
                if edits:
                    root = etree.fromstring(payload)
                    _page_pr, margin = _page_nodes(root)
                    for op in edits:
                        for key, value in op["values"].items():
                            margin.set(key, str(value))
                    payload = etree.tostring(
                        root, encoding="UTF-8", xml_declaration=True, standalone=True
                    )
                target.writestr(info, payload)

        after = build_page_geometry_map(candidate)
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    changed_sections = []
    for old, new in zip(before["sections"], after["sections"]):
        if old != new:
            changed_sections.append({
                "section_index": old["section_index"],
                "before_margin": old["margin"],
                "after_margin": new["margin"],
            })
    return {
        "before_page_geometry_sha256": before["page_geometry_sha256"],
        "after_page_geometry_sha256": after["page_geometry_sha256"],
        "page_geometry_changed": before["page_geometry_sha256"] != after["page_geometry_sha256"],
        "changed_sections": changed_sections,
        "operations": normalized,
        "validation": validation,
        "authority_ceiling": "VERSION_INDEXED_BOUNDARY",
        "renderer_scope": "Hancom Hangul 13.0.0.3622",
    }
