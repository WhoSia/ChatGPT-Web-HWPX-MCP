from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

PHASE = "P4.17"
PRODUCT = "0.42.0-p4.17"
SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/document-intelligence-record/v1"
DATASET_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/document-intelligence-dataset/v1"

_ARCHETYPE_RULES = [
    ("RFP_REQUIREMENT", ("과제제안요구서", "rfp")),
    ("RND_ANNOUNCEMENT", ("연구개발", "신규과제", "공고")),
    ("BID_NOTICE", ("입찰공고", "입찰에 부치는")),
    ("SPECIFICATION", ("시방서", "규격서", "공사개요서")),
    ("RFP", ("제안요청서",)),
    ("FORM", ("서식", "이력서", "자기소개서", "신청서")),
    ("GUIDE", ("안내서", "가이드", "매뉴얼")),
    ("ANNOUNCEMENT", ("공고문", "공개모집")),
]


def _stable(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value)).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _safe_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _zip_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_xml(raw: bytes) -> ET.Element | None:
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def _xml_feature_scan(path: Path) -> dict:
    element_counts: Counter[str] = Counter()
    attribute_counts: Counter[str] = Counter()
    namespaces: Counter[str] = Counter()
    text_fragments: list[str] = []
    xml_parts: list[str] = []
    binary_parts: list[str] = []
    part_sizes: dict[str, int] = {}

    with zipfile.ZipFile(path) as zf:
        names = sorted(zf.namelist())
        for name in names:
            info = zf.getinfo(name)
            part_sizes[name] = int(info.file_size)
            if name.lower().endswith(".xml"):
                xml_parts.append(name)
                raw = zf.read(name)
                root = _parse_xml(raw)
                if root is None:
                    continue
                for elem in root.iter():
                    element_counts[_local(elem.tag)] += 1
                    if elem.tag.startswith("{"):
                        namespaces[elem.tag[1:].split("}", 1)[0]] += 1
                    for key in elem.attrib:
                        attribute_counts[_local(key)] += 1
                    if elem.text and elem.text.strip() and len(text_fragments) < 5000:
                        text_fragments.append(_safe_text(elem.text))
            else:
                binary_parts.append(name)

    text = "\n".join(x for x in text_fragments if x)
    return {
        "part_count": len(part_sizes),
        "xml_part_count": len(xml_parts),
        "binary_part_count": len(binary_parts),
        "xml_parts": xml_parts,
        "part_size_total": sum(part_sizes.values()),
        "element_counts": dict(sorted(element_counts.items())),
        "attribute_counts": dict(sorted(attribute_counts.items())),
        "namespace_uris": sorted(namespaces),
        "paragraph_like_count": sum(element_counts[k] for k in ("p", "para", "paragraph")),
        "run_like_count": sum(element_counts[k] for k in ("run", "r")),
        "table_like_count": sum(element_counts[k] for k in ("tbl", "table")),
        "cell_like_count": sum(element_counts[k] for k in ("tc", "cell")),
        "equation_like_count": sum(element_counts[k] for k in ("equation", "eq", "script")),
        "picture_like_count": sum(element_counts[k] for k in ("pic", "picture", "img")),
        "shape_like_count": sum(element_counts[k] for k in ("shape", "rect", "ellipse", "line", "drawText")),
        "char_property_count": sum(element_counts[k] for k in ("charPr", "charProperties")),
        "para_property_count": sum(element_counts[k] for k in ("paraPr", "paraProperties")),
        "style_definition_count": element_counts.get("style", 0),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_sample": text[:4000],
    }


def infer_archetype(*, filename: str, source_title: str = "", text_sample: str = "", hints: Iterable[str] = ()) -> dict:
    haystack = " ".join([filename, source_title, text_sample[:2500], *[str(x) for x in hints]]).lower()
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    for archetype, needles in _ARCHETYPE_RULES:
        hits = [needle for needle in needles if needle.lower() in haystack]
        if hits:
            scores[archetype] = len(hits)
            evidence[archetype] = hits
    if not scores:
        return {"archetype": "UNKNOWN", "confidence": "LOW", "evidence": []}
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    winner, score = ordered[0]
    tied = [k for k, v in ordered if v == score]
    return {
        "archetype": winner if len(tied) == 1 else "MIXED",
        "candidates": tied,
        "confidence": "HIGH" if score >= 2 and len(tied) == 1 else "MEDIUM",
        "evidence": evidence,
    }


def mine_style_grammar(features: dict) -> dict:
    counts = features.get("element_counts") or {}
    grammar = {
        "has_tables": features.get("table_like_count", 0) > 0,
        "table_density": round(features.get("table_like_count", 0) / max(features.get("paragraph_like_count", 0), 1), 6),
        "has_equations": features.get("equation_like_count", 0) > 0,
        "has_pictures": features.get("picture_like_count", 0) > 0,
        "has_shapes": features.get("shape_like_count", 0) > 0,
        "char_property_count": features.get("char_property_count", 0),
        "para_property_count": features.get("para_property_count", 0),
        "style_definition_count": features.get("style_definition_count", 0),
        "header_footer_signal": int(counts.get("header", 0)) + int(counts.get("footer", 0)),
        "section_signal": int(counts.get("section", 0)) + int(counts.get("sec", 0)),
    }
    grammar["grammar_sha256"] = _sha(grammar)
    return grammar


def analyze_hwpx(path: str | Path, *, source: dict | None = None) -> dict:
    p = Path(path)
    if not zipfile.is_zipfile(p):
        raise ValueError("not a ZIP-based HWPX package")
    features = _xml_feature_scan(p)
    source = dict(source or {})
    archetype = infer_archetype(
        filename=p.name,
        source_title=str(source.get("title") or ""),
        text_sample=features["text_sample"],
        hints=source.get("archetype_hints") or [],
    )
    record = {
        "schema": SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "document_sha256": _zip_sha(p),
        "filename": p.name,
        "source": {
            "source_id": source.get("source_id"),
            "institution": source.get("institution"),
            "source_page": source.get("source_page"),
            "attachment_url": source.get("attachment_url"),
            "source_date": source.get("source_date"),
            "license_state": source.get("license_state", "SOURCE_TERMS_REVIEW_REQUIRED"),
            "raw_bytes_persisted": False,
        },
        "package_features": features,
        "archetype": archetype,
        "style_grammar": mine_style_grammar(features),
        "render_pair": {
            "status": "ABSENT",
            "native_visual_authority": False,
        },
    }
    record["record_sha256"] = _sha(record)
    return record


def attach_render_pair(record: dict, *, pdf_sha256: str, source: str = "USER_OR_OFFICIAL_PAIR") -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", pdf_sha256):
        raise ValueError("pdf_sha256 must be lowercase sha256")
    out = json.loads(json.dumps(record))
    out["render_pair"] = {
        "status": "PAIRED_UNADJUDICATED",
        "pdf_sha256": pdf_sha256,
        "source": source,
        "native_visual_authority": False,
    }
    out.pop("record_sha256", None)
    out["record_sha256"] = _sha(out)
    return out


def build_dataset(records: Iterable[dict]) -> dict:
    by_sha: dict[str, dict] = {}
    duplicates: list[dict] = []
    for record in records:
        sha = str(record.get("document_sha256") or "")
        if not sha:
            raise ValueError("record missing document_sha256")
        if sha in by_sha:
            duplicates.append({
                "document_sha256": sha,
                "kept_record_sha256": by_sha[sha].get("record_sha256"),
                "duplicate_record_sha256": record.get("record_sha256"),
            })
            continue
        by_sha[sha] = record
    rows = [by_sha[k] for k in sorted(by_sha)]
    archetypes = Counter((r.get("archetype") or {}).get("archetype", "UNKNOWN") for r in rows)
    institutions = Counter((r.get("source") or {}).get("institution") or "UNKNOWN" for r in rows)
    payload = {
        "schema": DATASET_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "record_count": len(rows),
        "duplicate_count": len(duplicates),
        "institution_count": len(institutions),
        "archetype_counts": dict(sorted(archetypes.items())),
        "institution_counts": dict(sorted(institutions.items())),
        "render_pair_count": sum(1 for r in rows if (r.get("render_pair") or {}).get("status") != "ABSENT"),
        "raw_document_bytes_persisted": False,
        "records": rows,
        "duplicates": duplicates,
        "authority": "STRUCTURAL_CORPUS_FEATURE_DATASET_NOT_NATIVE_VISUAL_GROUND_TRUTH",
    }
    payload["dataset_sha256"] = _sha(payload)
    return payload


def corpus_contract() -> dict:
    body = {
        "phase": PHASE,
        "product": PRODUCT,
        "raw_bytes_policy": "EPHEMERAL_ONLY_BY_DEFAULT",
        "persistent_dataset": "HASHES_FEATURES_PROVENANCE_ARCHETYPES_STYLE_GRAMMAR",
        "render_pair_policy": "PAIR_RECEIPT_DOES_NOT_IMPLY_NATIVE_VISUAL_AUTHORITY",
        "deduplication": "DOCUMENT_SHA256",
        "ground_truth_layers": [
            "PACKAGE_OBSERVED",
            "XML_DERIVED",
            "SOURCE_METADATA",
            "ARCHETYPE_HEURISTIC",
            "RENDER_PAIR_UNADJUDICATED",
        ],
    }
    return {**body, "contract_sha256": _sha(body)}
