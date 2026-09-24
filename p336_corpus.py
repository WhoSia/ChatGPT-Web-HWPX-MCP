from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

SCHEMA = "chatgpt-web-hwpx-mcp/p3.36-r1/native-style-observation/v1"
CENSUS_SCHEMA = "chatgpt-web-hwpx-mcp/p3.36-r1/native-style-census/v1"
BLIND_RE = re.compile(r"^[A-Za-z0-9]{12}$")
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
_MASK64 = (1 << 64) - 1


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def canonical_pair_key(filename: str) -> str:
    name = re.sub(r"\.(?:hwpx|pdf)$", "", str(filename), flags=re.I)
    return re.sub(r"\s+", " ", name.replace("+", " ")).strip()


def blind_source_stem(label: str, *, namespace: str = "P3.36-R1") -> str:
    """Stable opaque 12-char identifier. It is a blinding pseudonym, not a secret."""
    key = f"{namespace}|{label}"
    h = 1469598103934665603
    for ch in key:
        h ^= ord(ch)
        h = (h * 1099511628211) & _MASK64
    x = h or 1
    chars = []
    for _ in range(12):
        x ^= x << 13
        x ^= x >> 7
        x ^= x << 17
        x &= _MASK64
        chars.append(_ALPHABET[x % len(_ALPHABET)])
    return "".join(chars)


def validate_blind_ledger(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("EMPTY_BLIND_LEDGER")
    ids = []
    filenames = []
    for row in rows:
        blind_id = str(row.get("blind_id") or "")
        if not BLIND_RE.fullmatch(blind_id):
            raise ValueError("INVALID_BLIND_ID")
        filename = str(row.get("blind_filename") or "")
        if filename != f"{blind_id}.hwpx":
            raise ValueError("BLIND_FILENAME_MISMATCH")
        if not row.get("source_group") or not row.get("split"):
            raise ValueError("MISSING_SPLIT_METADATA")
        ids.append(blind_id)
        filenames.append(filename)
    if len(ids) != len(set(ids)) or len(filenames) != len(set(filenames)):
        raise ValueError("DUPLICATE_BLIND_ID")
    return {
        "sources": len(rows),
        "splits": dict(sorted(Counter(str(row["split"]) for row in rows).items())),
        "groups": len({str(row["source_group"]) for row in rows}),
        "authority": "PROVENANCE_PRESERVING_BLINDING_NOT_ANONYMITY_GUARANTEE",
    }


def source_stratified_split(rows: list[dict], *, discovery: float = 0.6,
                            calibration: float = 0.2, holdout: float = 0.2,
                            group_field: str = "source_group",
                            namespace: str = "P3.36-R1-split") -> dict:
    if not rows or abs((discovery + calibration + holdout) - 1.0) > 1e-9:
        raise ValueError("INVALID_SPLIT_RATIOS")
    groups = sorted({str(row.get(group_field) or "") for row in rows})
    if "" in groups:
        raise ValueError("MISSING_SOURCE_GROUP")
    ranked = sorted(
        groups,
        key=lambda group: hashlib.sha256(f"{namespace}|{group}".encode()).hexdigest(),
    )
    n = len(ranked)
    n_discovery = round(n * discovery)
    n_calibration = round(n * calibration)
    mapping = {}
    for index, group in enumerate(ranked):
        mapping[group] = (
            "DISCOVERY" if index < n_discovery
            else "CALIBRATION" if index < n_discovery + n_calibration
            else "HOLDOUT"
        )
    assignments = [{**row, "split": mapping[str(row[group_field])]} for row in rows]
    return {
        "assignments": assignments,
        "group_assignments": mapping,
        "document_counts": dict(sorted(Counter(row["split"] for row in assignments).items())),
        "group_counts": dict(sorted(Counter(mapping.values()).items())),
        "leakage_policy": "SOURCE_GROUPS_ARE_INDIVISIBLE_ACROSS_SPLITS",
    }


def _child(element, name: str):
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _text(element) -> str:
    return "".join(node.text or "" for node in element.iter() if _local(node.tag) == "t")


def _opaque_or_parse_error(raw: bytes) -> str:
    prefix = raw.lstrip(b"\xef\xbb\xbf\xff\xfe\x00 \t\r\n")[:1]
    return "PARSER_HOLD_XML_PARSE_ERROR" if prefix == b"<" else "PARSER_HOLD_OPAQUE_XML_PAYLOAD"


def inspect_native_style(path: Path | str, *, blind_id: str | None = None) -> dict:
    path = Path(path)
    source_id = blind_id or blind_source_stem(canonical_pair_key(path.name))
    if not BLIND_RE.fullmatch(source_id):
        raise ValueError("INVALID_BLIND_ID")
    raw_file = path.read_bytes()
    base = {
        "schema": SCHEMA,
        "blind_id": source_id,
        "sha256": hashlib.sha256(raw_file).hexdigest(),
        "bytes": len(raw_file),
        "authority": "OBSERVED_NATIVE_STRUCTURE_NOT_AESTHETIC_GROUND_TRUTH",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            header_raw = archive.read("Contents/header.xml")
            section_names = sorted(name for name in names if re.fullmatch(r"Contents/section\d+\.xml", name))
            if not section_names:
                return {**base, "status": "PARSER_HOLD_NO_SECTION_XML"}
            try:
                header = ET.fromstring(header_raw)
                sections = [(name, ET.fromstring(archive.read(name))) for name in section_names]
            except ET.ParseError:
                suspects = [header_raw] + [archive.read(name) for name in section_names[:1]]
                status = (
                    "PARSER_HOLD_OPAQUE_XML_PAYLOAD"
                    if any(_opaque_or_parse_error(blob) == "PARSER_HOLD_OPAQUE_XML_PAYLOAD" for blob in suspects)
                    else "PARSER_HOLD_XML_PARSE_ERROR"
                )
                return {**base, "status": status, "sections": len(section_names)}
    except (zipfile.BadZipFile, KeyError, OSError):
        return {**base, "status": "PARSER_HOLD_INVALID_HWPX_PACKAGE"}

    fontmaps = {}
    declared_fonts = set()
    for face_group in header.iter():
        if _local(face_group.tag) != "fontface":
            continue
        lang = face_group.attrib.get("lang", "")
        mapping = {}
        for font in face_group:
            if _local(font.tag) == "font":
                font_id = int(font.attrib.get("id", "0"))
                face = font.attrib.get("face", "")
                mapping[font_id] = face
                if face:
                    declared_fonts.add(face)
        fontmaps[lang] = mapping

    char_properties = {}
    for node in header.iter():
        if _local(node.tag) != "charPr":
            continue
        ref = _child(node, "fontRef")
        spacing = _child(node, "spacing")
        ratio = _child(node, "ratio")
        rel_size = _child(node, "relSz")
        offset = _child(node, "offset")
        font_ref = int(ref.attrib.get("hangul", "0")) if ref is not None else 0
        char_properties[str(node.attrib.get("id"))] = {
            "height": int(node.attrib.get("height", "0") or 0),
            "bold": any(_local(child.tag) == "bold" for child in node),
            "font": fontmaps.get("HANGUL", {}).get(font_ref, f"REF:{font_ref}"),
            "spacing": int(spacing.attrib.get("hangul", "0")) if spacing is not None else 0,
            "ratio": int(ratio.attrib.get("hangul", "100")) if ratio is not None else 100,
            "relative_size": int(rel_size.attrib.get("hangul", "100")) if rel_size is not None else 100,
            "offset": int(offset.attrib.get("hangul", "0")) if offset is not None else 0,
        }

    paragraph_properties = {}
    for node in header.iter():
        if _local(node.tag) != "paraPr":
            continue
        align = _child(node, "align")
        heading = _child(node, "heading")
        paragraph_properties[str(node.attrib.get("id"))] = {
            "alignment": align.attrib.get("horizontal") if align is not None else None,
            "heading_type": heading.attrib.get("type") if heading is not None else None,
            "heading_level": int(heading.attrib.get("level", "0")) if heading is not None else None,
        }

    char_weights = Counter()
    alignment_weights = Counter()
    heading_weight = 0
    total_text = 0
    paragraph_count = 0
    nonempty_paragraphs = 0
    table_count = 0
    cell_count = 0
    image_count = 0
    table_text = 0

    def walk(element, in_table: bool = False):
        nonlocal total_text, paragraph_count, nonempty_paragraphs
        nonlocal table_count, cell_count, image_count, table_text, heading_weight
        tag = _local(element.tag)
        if tag == "tbl":
            table_count += 1
            in_table = True
        elif tag == "tc":
            cell_count += 1
        elif tag in {"pic", "img"}:
            image_count += 1

        if tag == "p":
            paragraph_count += 1
            text = _text(element).strip()
            weight = max(len(text), 1)
            total_text += len(text)
            if text:
                nonempty_paragraphs += 1
            if in_table:
                table_text += len(text)
            para = paragraph_properties.get(element.attrib.get("paraPrIDRef", ""), {})
            alignment_weights[para.get("alignment") or "UNKNOWN"] += weight
            if para.get("heading_type") not in {None, "NONE"}:
                heading_weight += weight
            for run in element.iter():
                if _local(run.tag) == "run":
                    run_text = _text(run).strip()
                    if run_text:
                        char_weights[run.attrib.get("charPrIDRef", "")] += len(run_text)

        for child in element:
            walk(child, in_table)

    for _, section in sections:
        walk(section)

    total_char_weight = sum(char_weights.values())
    font_weights = Counter()
    size_weights = Counter()
    spacing_weights = Counter()
    bold_weight = 0
    for char_id, weight in char_weights.items():
        prop = char_properties.get(char_id, {})
        font_weights[prop.get("font", "UNKNOWN")] += weight
        if prop.get("height"):
            size_weights[prop["height"] / 100] += weight
        spacing_weights[prop.get("spacing", 0)] += weight
        if prop.get("bold"):
            bold_weight += weight

    total_para_weight = sum(alignment_weights.values())
    return {
        **base,
        "status": "PASS",
        "sections": len(sections),
        "declared_font_count": len(declared_fonts),
        "text_characters": total_text,
        "paragraphs": paragraph_count,
        "nonempty_paragraphs": nonempty_paragraphs,
        "tables": table_count,
        "cells": cell_count,
        "images": image_count,
        "table_text_share": round(table_text / max(1, total_text), 6),
        "bold_text_share": round(bold_weight / max(1, total_char_weight), 6),
        "heading_metadata_share": round(heading_weight / max(1, total_para_weight), 6),
        "alignment_shares": {
            key: round(value / max(1, total_para_weight), 6)
            for key, value in sorted(alignment_weights.items())
        },
        "dominant_fonts": [
            {"value": key, "share": round(value / max(1, total_char_weight), 6)}
            for key, value in font_weights.most_common(8)
        ],
        "dominant_sizes_pt": [
            {"value": key, "share": round(value / max(1, total_char_weight), 6)}
            for key, value in size_weights.most_common(8)
        ],
        "dominant_letter_spacing": [
            {"value": key, "share": round(value / max(1, total_char_weight), 6)}
            for key, value in spacing_weights.most_common(8)
        ],
    }


def build_native_style_census(observations: list[dict]) -> dict:
    if not observations:
        raise ValueError("EMPTY_CENSUS")
    passing = [row for row in observations if row.get("status") == "PASS"]
    holds = [row for row in observations if row.get("status") != "PASS"]
    font_docs = Counter()
    size_docs = Counter()
    spacing_docs = Counter()
    alignment = Counter()
    for row in passing:
        for item in row.get("dominant_fonts", []):
            if float(item["share"]) >= 0.10:
                font_docs[str(item["value"])] += 1
        for item in row.get("dominant_sizes_pt", []):
            if float(item["share"]) >= 0.10:
                size_docs[str(item["value"])] += 1
        for item in row.get("dominant_letter_spacing", []):
            if float(item["share"]) >= 0.10:
                spacing_docs[str(item["value"])] += 1
        for key, value in row.get("alignment_shares", {}).items():
            alignment[key] += float(value)

    def median(field):
        values = sorted(float(row.get(field, 0.0)) for row in passing)
        if not values:
            return None
        mid = len(values) // 2
        return round(values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2, 6)

    census = {
        "schema": CENSUS_SCHEMA,
        "phase": "P3.36-R1",
        "source_count": len(observations),
        "parseable_sources": len(passing),
        "parser_holds": [
            {"blind_id": row.get("blind_id"), "status": row.get("status")}
            for row in holds
        ],
        "documents_with_tables": sum(int(row.get("tables", 0) > 0) for row in passing),
        "documents_with_images": sum(int(row.get("images", 0) > 0) for row in passing),
        "median_table_text_share": median("table_text_share"),
        "median_bold_text_share": median("bold_text_share"),
        "median_heading_metadata_share": median("heading_metadata_share"),
        "median_nonempty_paragraphs": median("nonempty_paragraphs"),
        "median_text_characters": median("text_characters"),
        "mean_alignment_share": {
            key: round(value / max(1, len(passing)), 6)
            for key, value in sorted(alignment.items())
        },
        "fonts_with_at_least_10pct_text_share": font_docs.most_common(20),
        "sizes_with_at_least_10pct_text_share": size_docs.most_common(20),
        "letter_spacing_with_at_least_10pct_text_share": spacing_docs.most_common(20),
        "authority": "EMPIRICAL_CONVENTION_CENSUS_NOT_AESTHETIC_NORM",
        "selection_policy": "NO_AUTOMATIC_STYLE_WINNER",
    }
    census["census_sha256"] = hashlib.sha256(
        json.dumps(census, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return census


def derive_engineering_priorities(census: dict) -> dict:
    parseable = int(census.get("parseable_sources") or 0)
    priorities = []
    if parseable and int(census.get("documents_with_tables") or 0) / parseable >= 0.5:
        priorities.append({
            "priority": "TABLE_AUTHORING_AND_LAYOUT_ROBUSTNESS",
            "reason": "Tables occur in a majority of observed public HWPX sources.",
            "non_inference": "Do not conclude that more tables are aesthetically better.",
        })
    if float(census.get("median_heading_metadata_share") or 0.0) < 0.05:
        priorities.append({
            "priority": "PRESENTATION_ROLE_HYPOTHESIS_LAYER",
            "reason": "Visible hierarchy frequently lacks native heading metadata.",
            "non_inference": "Keep native semantic role and presentation-role hypothesis separate.",
        })
    if census.get("parser_holds"):
        priorities.append({
            "priority": "OPAQUE_NATIVE_PAYLOAD_COMPATIBILITY",
            "reason": "At least one otherwise collected HWPX source could not be read as plain XML.",
            "non_inference": "Treat this as a compatibility gap, not malformed-document proof.",
        })
    priorities.append({
        "priority": "DUAL_DESIGN_AUTHORITY",
        "reason": "Observed Korean public-document conventions describe prevalence, not beauty.",
        "non_inference": "Word/PDF-like polished design targets require separate visual controls or explicit user intent.",
    })
    return {
        "phase": "P3.36-R1",
        "priorities": priorities,
        "design_authority_ladder": [
            "NATIVE_STRUCTURE_FACT",
            "OBSERVED_PUBLIC_DOCUMENT_CONVENTION",
            "PAIRED_VISUAL_CONTROL",
            "EXPLICIT_HUMAN_DESIGN_TARGET",
        ],
        "rule": "Never promote prevalence into an aesthetic default without independent visual or human evidence.",
    }
