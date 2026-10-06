from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree as ET

PHASE = "P4.17"
PRODUCT = "0.42.0-p4.17"
GRAPH_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/semantic-document-graph/v1"
ALIGNMENT_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/cross-document-alignment/v1"
SCHEMA_INFERENCE_SCHEMA = "chatgpt-web-hwpx-mcp/p4.17/corpus-document-schema/v1"

ROLE_ORDER = (
    "TITLE", "HEADING", "BODY", "CAPTION", "FORM_FIELD", "LIST_ITEM",
    "TABLE_HEADER", "TABLE_CELL", "EQUATION", "PICTURE", "SHAPE", "EMPTY"
)
COMPONENT_KINDS = {"PARAGRAPH", "TABLE", "EQUATION", "PICTURE", "SHAPE"}


def _stable(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value)).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(elem: ET.Element) -> str:
    parts = []
    for node in elem.iter():
        if node.text and node.text.strip():
            parts.append(node.text.strip())
    return " ".join(" ".join(parts).split())


def _attrs(elem: ET.Element) -> dict[str, str]:
    return {_local(k): str(v) for k, v in elem.attrib.items()}


def classify_paragraph_role(text: str, *, index: int, total: int, in_table: bool = False, first_table_row: bool = False) -> dict:
    raw = " ".join(str(text or "").split())
    if in_table:
        role = "TABLE_HEADER" if first_table_row else "TABLE_CELL"
        return {"role": role, "confidence": "HIGH", "evidence": ["TABLE_CONTEXT"]}
    if not raw:
        return {"role": "EMPTY", "confidence": "HIGH", "evidence": ["NO_VISIBLE_TEXT"]}

    evidence: list[str] = []
    role = "BODY"
    confidence = "MEDIUM"

    if re.match(r"^\s*(표|그림|figure|table)\s*[\dⅠⅡⅢⅣⅤ가-힣]*[\.\-:：]?\s+", raw, re.I):
        role, confidence = "CAPTION", "HIGH"
        evidence.append("CAPTION_PREFIX")
    elif len(raw) <= 100 and re.match(r"^(제?\s*\d+\s*[장절항]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*[\.\-]|[0-9]+(?:\.[0-9]+){0,3}\s+|[가-힣]\.\s+)", raw):
        role, confidence = "HEADING", "HIGH"
        evidence.append("NUMBERED_HEADING_PATTERN")
    elif len(raw) <= 80 and re.match(r"^[■□●○▶▷◆◇※\-•]\s*", raw):
        role, confidence = "LIST_ITEM", "HIGH"
        evidence.append("BULLET_PREFIX")
    elif index <= 2 and len(raw) <= 120 and not raw.endswith((".", "다.", "요.", "함.")):
        role, confidence = "TITLE", "MEDIUM"
        evidence.append("EARLY_SHORT_BLOCK")
    elif len(raw) <= 80 and re.search(r"[:：]\s*$", raw):
        role, confidence = "FORM_FIELD", "MEDIUM"
        evidence.append("FIELD_LABEL_SUFFIX")
    elif len(raw) <= 80 and re.match(r"^(성명|주소|연락처|전화|이메일|소속|직위|작성일|신청인|담당자)\s*[:：]", raw):
        role, confidence = "FORM_FIELD", "HIGH"
        evidence.append("KNOWN_FIELD_LABEL")
    elif len(raw) <= 80 and not re.search(r"[.!?。다요함]$", raw) and index < max(4, total // 2):
        role, confidence = "HEADING", "LOW"
        evidence.append("SHORT_NON_SENTENCE_EARLY_BLOCK")
    else:
        evidence.append("DEFAULT_BODY")

    return {"role": role, "confidence": confidence, "evidence": evidence}


def _heading_level(text: str) -> int:
    raw = " ".join(str(text or "").split())
    if re.match(r"^제?\s*\d+\s*장", raw):
        return 1
    if re.match(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*[\.\-]", raw):
        return 1
    if re.match(r"^\d+\.\s+", raw):
        return 2
    m = re.match(r"^(\d+(?:\.\d+){1,3})\s+", raw)
    if m:
        return min(4, m.group(1).count(".") + 2)
    if re.match(r"^[가-힣]\.\s+", raw):
        return 3
    return 2


def _component_kind(local: str) -> str | None:
    l = local.lower()
    if l in {"p", "para", "paragraph"}:
        return "PARAGRAPH"
    if l in {"tbl", "table"}:
        return "TABLE"
    if l in {"equation", "eq"}:
        return "EQUATION"
    if l in {"pic", "picture", "img"}:
        return "PICTURE"
    if l in {"shape", "rect", "ellipse", "line", "drawtext", "textbox"}:
        return "SHAPE"
    return None


def _section_xml_names(names: Sequence[str]) -> list[str]:
    preferred = [n for n in names if n.lower().endswith(".xml") and ("section" in n.lower() or "/bodytext/" in n.lower())]
    return sorted(preferred)


def recover_semantic_structure(path: str | Path) -> dict:
    p = Path(path)
    if not zipfile.is_zipfile(p):
        raise ValueError("not a ZIP-based HWPX package")

    raw_blocks: list[dict] = []
    with zipfile.ZipFile(p) as zf:
        section_names = _section_xml_names(zf.namelist())
        for section_index, name in enumerate(section_names):
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue
            paragraphs = [e for e in root.iter() if _component_kind(_local(e.tag)) == "PARAGRAPH"]
            para_position = {id(e): i for i, e in enumerate(paragraphs)}
            table_depth: dict[int, tuple[bool, bool]] = {}

            def walk(elem: ET.Element, *, in_table: bool = False, first_table_row: bool = False) -> None:
                local = _local(elem.tag)
                kind = _component_kind(local)
                now_in_table = in_table or kind == "TABLE"
                row_first = first_table_row
                if local.lower() in {"tr", "row"}:
                    parent_table_rows = [c for c in list(elem.getparent())] if hasattr(elem, "getparent") else []
                    row_first = False
                if kind == "PARAGRAPH":
                    idx = para_position.get(id(elem), len(raw_blocks))
                    raw_blocks.append({
                        "kind": "PARAGRAPH",
                        "section_index": section_index,
                        "source_part": name,
                        "text": _text(elem),
                        "attrs": _attrs(elem),
                        "paragraph_index": idx,
                        "in_table": in_table,
                        "first_table_row": first_table_row,
                    })
                    return
                if kind in {"TABLE", "EQUATION", "PICTURE", "SHAPE"}:
                    raw_blocks.append({
                        "kind": kind,
                        "section_index": section_index,
                        "source_part": name,
                        "text": _text(elem) if kind in {"TABLE", "EQUATION", "SHAPE"} else "",
                        "attrs": _attrs(elem),
                    })
                children = list(elem)
                if kind == "TABLE":
                    rows = [c for c in children if _local(c.tag).lower() in {"tr", "row"}]
                    if rows:
                        for ri, row in enumerate(rows):
                            walk(row, in_table=True, first_table_row=(ri == 0))
                        for child in children:
                            if child not in rows:
                                walk(child, in_table=True, first_table_row=False)
                        return
                for child in children:
                    walk(child, in_table=now_in_table, first_table_row=first_table_row)

            walk(root)

    total_paragraphs = sum(1 for b in raw_blocks if b["kind"] == "PARAGRAPH")
    blocks: list[dict] = []
    para_seen = 0
    heading_stack: list[tuple[int, str]] = []

    for ordinal, raw in enumerate(raw_blocks):
        kind = raw["kind"]
        if kind == "PARAGRAPH":
            role = classify_paragraph_role(
                raw.get("text", ""),
                index=para_seen,
                total=total_paragraphs,
                in_table=bool(raw.get("in_table")),
                first_table_row=bool(raw.get("first_table_row")),
            )
            para_seen += 1
        else:
            role = {
                "role": {
                    "TABLE": "TABLE_CELL",
                    "EQUATION": "EQUATION",
                    "PICTURE": "PICTURE",
                    "SHAPE": "SHAPE",
                }[kind],
                "confidence": "HIGH",
                "evidence": ["NATIVE_COMPONENT_TAG"],
            }

        level = _heading_level(raw.get("text", "")) if role["role"] == "HEADING" else None
        parent_heading_id = None
        if role["role"] == "HEADING":
            while heading_stack and heading_stack[-1][0] >= int(level):
                heading_stack.pop()
            parent_heading_id = heading_stack[-1][1] if heading_stack else None
        elif heading_stack:
            parent_heading_id = heading_stack[-1][1]

        block = {
            "block_id": f"s{raw['section_index']}:b{ordinal}",
            "ordinal": ordinal,
            "section_index": raw["section_index"],
            "source_part": raw["source_part"],
            "kind": kind,
            "role": role["role"],
            "role_confidence": role["confidence"],
            "role_evidence": role["evidence"],
            "heading_level": level,
            "parent_heading_id": parent_heading_id,
            "text": raw.get("text", "")[:4000],
            "text_sha256": hashlib.sha256(raw.get("text", "").encode("utf-8")).hexdigest(),
            "native_attrs_sha256": _sha(raw.get("attrs") or {}),
        }
        block["block_sha256"] = _sha(block)
        blocks.append(block)
        if role["role"] == "HEADING":
            heading_stack.append((int(level), block["block_id"]))

    hierarchy_edges = [
        {"parent": b["parent_heading_id"], "child": b["block_id"]}
        for b in blocks if b.get("parent_heading_id")
    ]
    role_counts = Counter(b["role"] for b in blocks)
    kind_counts = Counter(b["kind"] for b in blocks)
    layout = discover_repeated_layout_grammar(blocks)
    graph = {
        "schema": GRAPH_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "document_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "block_count": len(blocks),
        "role_counts": dict(sorted(role_counts.items())),
        "component_counts": dict(sorted(kind_counts.items())),
        "blocks": blocks,
        "hierarchy_edges": hierarchy_edges,
        "repeated_layout_grammar": layout,
        "authority": "XML_DERIVED_SEMANTIC_STRUCTURE_WITH_HEURISTIC_ROLE_LABELS",
        "native_visual_authority": False,
    }
    graph["graph_sha256"] = _sha(graph)
    return graph


def discover_repeated_layout_grammar(blocks: Sequence[Mapping[str, Any]], *, min_window: int = 2, max_window: int = 5, min_occurrences: int = 2) -> dict:
    tokens = [f"{b.get('kind')}:{b.get('role')}" for b in blocks]
    patterns: list[dict] = []
    for width in range(max(2, int(min_window)), min(int(max_window), len(tokens)) + 1):
        positions: defaultdict[tuple[str, ...], list[int]] = defaultdict(list)
        for i in range(0, len(tokens) - width + 1):
            key = tuple(tokens[i:i + width])
            positions[key].append(i)
        for key, starts in positions.items():
            if len(starts) < min_occurrences:
                continue
            patterns.append({
                "width": width,
                "signature": list(key),
                "occurrences": len(starts),
                "start_ordinals": starts,
                "pattern_sha256": _sha({"signature": key}),
            })
    patterns.sort(key=lambda x: (-x["occurrences"], -x["width"], x["pattern_sha256"]))
    payload = {
        "token_count": len(tokens),
        "pattern_count": len(patterns),
        "patterns": patterns[:100],
        "authority": "ROLE_COMPONENT_SEQUENCE_REPETITION",
    }
    payload["grammar_sha256"] = _sha(payload)
    return payload


def classify_native_components(graph: Mapping[str, Any]) -> dict:
    rows = []
    for block in graph.get("blocks", []):
        kind = str(block.get("kind") or "")
        if kind not in COMPONENT_KINDS:
            continue
        rows.append({
            "block_id": block.get("block_id"),
            "native_kind": kind,
            "semantic_role": block.get("role"),
            "section_index": block.get("section_index"),
            "heading_parent": block.get("parent_heading_id"),
            "classification": f"{kind}:{block.get('role')}",
        })
    payload = {
        "component_count": len(rows),
        "components": rows,
        "native_kinds": dict(sorted(Counter(x["native_kind"] for x in rows).items())),
        "semantic_roles": dict(sorted(Counter(x["semantic_role"] for x in rows).items())),
        "authority": "XML_NATIVE_COMPONENT_PLUS_SEMANTIC_ROLE_CLASSIFICATION",
    }
    payload["classification_sha256"] = _sha(payload)
    return payload


def _sequence(graph: Mapping[str, Any]) -> list[str]:
    return [f"{b.get('kind')}:{b.get('role')}" for b in graph.get("blocks", []) if b.get("role") != "EMPTY"]


def _lcs(a: Sequence[str], b: Sequence[str]) -> list[tuple[int, int, str]]:
    if not a or not b:
        return []
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            dp[i][j] = 1 + dp[i + 1][j + 1] if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    i = j = 0
    out = []
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            out.append((i, j, a[i])); i += 1; j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def align_semantic_graphs(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict:
    a, b = _sequence(left), _sequence(right)
    matches = _lcs(a, b)
    denom = max(len(a), len(b), 1)
    score = round(len(matches) / denom, 6)
    payload = {
        "schema": ALIGNMENT_SCHEMA,
        "phase": PHASE,
        "left_graph_sha256": left.get("graph_sha256"),
        "right_graph_sha256": right.get("graph_sha256"),
        "left_sequence_length": len(a),
        "right_sequence_length": len(b),
        "matched_token_count": len(matches),
        "structural_similarity": score,
        "matched_tokens": [{"left": i, "right": j, "token": token} for i, j, token in matches[:500]],
        "authority": "ROLE_COMPONENT_SEQUENCE_ALIGNMENT_NOT_VISUAL_EQUIVALENCE",
        "native_visual_equivalence_claimed": False,
    }
    payload["alignment_sha256"] = _sha(payload)
    return payload


def infer_corpus_schema(graphs: Sequence[Mapping[str, Any]], *, support_threshold: float = 0.6) -> dict:
    if not graphs:
        raise ValueError("at least one semantic graph is required")
    threshold = float(support_threshold)
    if threshold <= 0 or threshold > 1:
        raise ValueError("support_threshold must be in (0,1]")
    document_count = len(graphs)
    role_support = Counter()
    kind_support = Counter()
    pattern_support = Counter()
    for graph in graphs:
        role_support.update(set((graph.get("role_counts") or {}).keys()))
        kind_support.update(set((graph.get("component_counts") or {}).keys()))
        for p in (graph.get("repeated_layout_grammar") or {}).get("patterns", []):
            pattern_support.update([tuple(p.get("signature") or [])])

    def rows(counter: Counter) -> list[dict]:
        out = []
        for key, count in counter.items():
            support = count / document_count
            if support >= threshold:
                out.append({"value": list(key) if isinstance(key, tuple) else key, "document_count": count, "support": round(support, 6)})
        return sorted(out, key=lambda x: (-x["support"], str(x["value"])))

    payload = {
        "schema": SCHEMA_INFERENCE_SCHEMA,
        "phase": PHASE,
        "product": PRODUCT,
        "document_count": document_count,
        "support_threshold": threshold,
        "required_roles": rows(role_support),
        "required_component_kinds": rows(kind_support),
        "recurrent_layout_patterns": rows(pattern_support),
        "authority": "CORPUS_SUPPORT_SCHEMA_INFERENCE_NOT_UNIVERSAL_HWPX_SCHEMA",
        "generalization_status": "MULTI_INSTITUTION_REQUIRED_FOR_CROSS_INSTITUTION_AUTHORITY",
    }
    payload["schema_sha256"] = _sha(payload)
    return payload


def semantic_structure_contract() -> dict:
    body = {
        "phase": PHASE,
        "product": PRODUCT,
        "graph_schema": GRAPH_SCHEMA,
        "roles": list(ROLE_ORDER),
        "native_component_kinds": sorted(COMPONENT_KINDS),
        "hierarchy": "NUMBERING_AND_LOCAL_TEXT_HEURISTICS_WITH_EVIDENCE",
        "layout_grammar": "REPEATED_ROLE_COMPONENT_NGRAMS",
        "cross_document_alignment": "LCS_OVER_ROLE_COMPONENT_SEQUENCE",
        "schema_inference": "DOCUMENT_SUPPORT_THRESHOLD",
        "authority_ceiling": "STRUCTURAL_SEMANTIC_HEURISTICS_NOT_NATIVE_VISUAL_TRUTH",
    }
    return {**body, "contract_sha256": _sha(body)}
