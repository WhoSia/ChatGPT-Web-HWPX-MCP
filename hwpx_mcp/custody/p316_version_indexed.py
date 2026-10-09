from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree


SCHEMA = "chatgpt-web-hwpx-mcp/version-indexed-stability/p3.16/v1"
STRUCTURAL_SCHEMA = "chatgpt-web-hwpx-mcp/structural-oracle/p3.16/v1"


def _canon(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _section_names(archive: zipfile.ZipFile) -> list[str]:
    names = [
        name
        for name in archive.namelist()
        if name.startswith("Contents/section") and name.endswith(".xml")
    ]

    def key(name: str) -> tuple[int, str]:
        tail = name.rsplit("section", 1)[-1].split(".xml", 1)[0]
        try:
            return int(tail), name
        except ValueError:
            return 10**9, name

    return sorted(names, key=key)


def _page_geometry(root: etree._Element) -> dict:
    page_pr = next((n for n in root.iter() if _local(n.tag) == "pagePr"), None)
    if page_pr is None:
        return {"page_pr": {}, "margin": {}}

    margin = next(
        (
            n
            for n in page_pr.iter()
            if n is not page_pr and _local(n.tag) in {"margin", "pageMargin"}
        ),
        None,
    )
    return {
        "page_pr": dict(sorted(page_pr.attrib.items())),
        "margin": {} if margin is None else dict(sorted(margin.attrib.items())),
    }


def _section_structure(root: etree._Element) -> dict:
    paragraphs = 0
    hard_line_breaks = 0
    page_breaks = 0
    column_breaks = 0
    object_counts: dict[str, int] = {}
    paragraph_text_hashes: list[str] = []

    for node in root.iter():
        local = _local(node.tag)
        if local == "p":
            paragraphs += 1
            if str(node.get("pageBreak", "0")).lower() in {"1", "true"}:
                page_breaks += 1
            if str(node.get("columnBreak", "0")).lower() in {"1", "true"}:
                column_breaks += 1
            text = "".join(node.itertext())
            paragraph_text_hashes.append(
                hashlib.sha256(text.encode("utf-8")).hexdigest()
            )
        elif local == "lineBreak":
            hard_line_breaks += 1
        elif local in {
            "tbl",
            "table",
            "pic",
            "picture",
            "equation",
            "ole",
            "container",
            "rect",
            "ellipse",
            "line",
        }:
            object_counts[local] = object_counts.get(local, 0) + 1

    return {
        "page_geometry": _page_geometry(root),
        "paragraph_count": paragraphs,
        "hard_line_break_count": hard_line_breaks,
        "explicit_page_break_count": page_breaks,
        "explicit_column_break_count": column_breaks,
        "paragraph_text_sha256": paragraph_text_hashes,
        "object_counts": dict(sorted(object_counts.items())),
    }


def build_structural_oracle(path: Path) -> dict:
    path = Path(path)
    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())
        required = {
            "mimetype",
            "version.xml",
            "META-INF/container.xml",
            "Contents/content.hpf",
            "Contents/header.xml",
        }
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"HWPX missing structural members: {missing}")

        header_root = etree.fromstring(archive.read("Contents/header.xml"))
        char_pr = []
        font_faces = []
        for node in header_root.iter():
            local = _local(node.tag)
            if local == "charPr":
                char_pr.append(dict(sorted(node.attrib.items())))
            elif local in {"fontface", "font"} and node.attrib:
                font_faces.append(dict(sorted(node.attrib.items())))

        sections = []
        for name in _section_names(archive):
            root = etree.fromstring(archive.read(name))
            sections.append(
                {
                    "section": name,
                    **_section_structure(root),
                }
            )

    header_style = {
        "char_pr": char_pr,
        "font_faces": font_faces,
    }
    text_content = [
        item["paragraph_text_sha256"]
        for section in sections
        for item in [{"paragraph_text_sha256": section["paragraph_text_sha256"]}]
    ]
    oracle = {
        "schema": STRUCTURAL_SCHEMA,
        "header_style_sha256": _sha(header_style),
        "page_geometry_sha256": _sha(
            [section["page_geometry"] for section in sections]
        ),
        "text_content_sha256": _sha(text_content),
        "explicit_break_sha256": _sha(
            [
                {
                    "hard_line_break_count": section["hard_line_break_count"],
                    "explicit_page_break_count": section["explicit_page_break_count"],
                    "explicit_column_break_count": section[
                        "explicit_column_break_count"
                    ],
                }
                for section in sections
            ]
        ),
        "object_topology_sha256": _sha(
            [section["object_counts"] for section in sections]
        ),
        "section_count": len(sections),
        "sections": sections,
        "authority": "RENDERER_INDEPENDENT_HWPX_STRUCTURAL_ORACLE",
    }
    oracle["structural_oracle_sha256"] = _sha(oracle)
    return oracle


def compare_structural_oracles(source: dict, target: dict) -> dict:
    dimensions = {
        "header_style": source.get("header_style_sha256")
        == target.get("header_style_sha256"),
        "page_geometry": source.get("page_geometry_sha256")
        == target.get("page_geometry_sha256"),
        "text_content": source.get("text_content_sha256")
        == target.get("text_content_sha256"),
        "explicit_breaks": source.get("explicit_break_sha256")
        == target.get("explicit_break_sha256"),
        "object_topology": source.get("object_topology_sha256")
        == target.get("object_topology_sha256"),
    }
    changed = sorted(key for key, equal in dimensions.items() if not equal)
    return {
        "equal_dimensions": dimensions,
        "changed_dimensions": changed,
        "structurally_identical": not changed,
        "authority": "RENDERER_INDEPENDENT_STRUCTURAL_DIFF",
    }


def adjudicate_version_indexed_stability(packet: dict) -> dict:
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise ValueError("unsupported P3.16 stability schema")

    repetitions = packet.get("repetitions")
    if not isinstance(repetitions, list) or len(repetitions) < 3:
        raise ValueError("P3.16 requires at least three fresh repetitions")

    first = repetitions[0]
    required_identity = (
        "renderer_version",
        "renderer_executable_sha256",
        "fixture_set_sha256",
        "font_file_custody_sha256",
        "os_name",
        "os_version",
        "machine_id",
        "locale",
        "dpi",
        "rasterizer",
        "rasterizer_version",
    )
    identity_mismatches: dict[str, list[Any]] = {}
    for key in required_identity:
        values = [item.get(key) for item in repetitions]
        if not values[0] or any(value != values[0] for value in values[1:]):
            identity_mismatches[key] = values

    for index, item in enumerate(repetitions):
        _require(
            item.get("world_contact_pass") is True,
            f"repetition {index} world-contact must pass",
        )
        _require(
            item.get("baseline_exact_pixel_pass") is True,
            f"repetition {index} baseline exact-pixel must pass",
        )
        _require(
            item.get("positive_sensitivity_pass") is True,
            f"repetition {index} sensitivity must pass",
        )

    def boundary_signature(item: dict, family: str) -> tuple[str, float, str]:
        b = (item.get("boundaries") or {}).get(family) or {}
        _require(
            b.get("predecessor_line_break_equal") is True,
            f"{family} predecessor must remain equal",
        )
        _require(
            b.get("selected_line_break_equal") is False,
            f"{family} selected boundary must diverge",
        )
        return (
            str(b.get("candidate_id") or ""),
            float(b.get("magnitude", 0) or 0),
            str(b.get("predecessor_candidate_id") or ""),
        )

    advance = [boundary_signature(item, "advance") for item in repetitions]
    frame = [boundary_signature(item, "frame") for item in repetitions]
    advance_stable = all(value == advance[0] for value in advance[1:])
    frame_stable = all(value == frame[0] for value in frame[1:])

    source_rasters = [
        str(item.get("baseline_source_raster_sha256") or "") for item in repetitions
    ]
    target_rasters = [
        str(item.get("baseline_target_raster_sha256") or "") for item in repetitions
    ]
    baseline_raster_stable = bool(
        source_rasters[0]
        and target_rasters[0]
        and all(value == source_rasters[0] for value in source_rasters[1:])
        and all(value == target_rasters[0] for value in target_rasters[1:])
    )

    structural = packet.get("structural_oracle") or {}
    structural_pass = bool(
        structural.get("baseline_structurally_identical") is True
        and structural.get("advance_changed_dimensions") == ["header_style"]
        and structural.get("frame_changed_dimensions") == ["page_geometry"]
    )

    environment_stable = not identity_mismatches
    boundary_stable = advance_stable and frame_stable

    if environment_stable and boundary_stable and baseline_raster_stable and structural_pass:
        verdict = "VERSION_INDEXED_EXACT_FIDELITY_AUTHORITY"
        authority = "HANCOM_VERSION_INDEXED_EXACT_RENDER_AUTHORITY"
    elif environment_stable and boundary_stable and structural_pass:
        verdict = "VERSION_INDEXED_BOUNDARY_STABILITY_AUTHORITY"
        authority = "HANCOM_VERSION_INDEXED_BOUNDARY_AUTHORITY"
    else:
        verdict = "SINGLE_VERSION_STABILITY_HOLD"
        authority = "VERSION_INDEXED_AUTHORITY_HOLD"

    result = {
        "renderer_version": str(first.get("renderer_version") or ""),
        "renderer_executable_sha256": str(
            first.get("renderer_executable_sha256") or ""
        ),
        "repetition_count": len(repetitions),
        "environment_stable": environment_stable,
        "identity_mismatches": identity_mismatches,
        "advance_boundary_stable": advance_stable,
        "frame_boundary_stable": frame_stable,
        "baseline_raster_stable": baseline_raster_stable,
        "renderer_independent_structural_oracle_pass": structural_pass,
        "verdict": verdict,
        "authority": authority,
        "cross_version_state": "DEFERRED_REOPENING_AVAILABLE",
        "cross_version_required_for_global_authority": True,
    }
    result["adjudication_sha256"] = _sha(result)
    return result
