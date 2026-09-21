from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from hwpx import HwpxDocument

from p27_tables import _save_document

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SCHEMA = "chatgpt-web-hwpx-mcp/story-layer/p3.24/v1"
PAGE_TYPES = {"BOTH", "EVEN", "ODD"}
STORY_KINDS = {"header", "footer"}

DEFERRED_OPERATIONS = {
    "set_first_page_story": (
        "EVIDENCE_GATE_CLOSED: HWPX header/footer story applyPageType is BOTH/EVEN/ODD; "
        "first-page behavior is represented through section visibility, not an invented FIRST story."
    ),
    "clone_story_xml_raw": (
        "EVIDENCE_GATE_CLOSED: arbitrary raw story cloning is not admitted without measured "
        "cross-section reference/linkage custody."
    ),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def story_layer_contract() -> dict:
    return {
        "phase": "P3.24",
        "authority": "STRUCTURAL_STORY_LAYER_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
        "ancestry": {
            "P3.18": "page setup, BOTH/EVEN/ODD header/footer, page number, section add/remove",
            "P3.24": "story ownership/read-back, first-page visibility policy, variant composition, boundary-safe story transactions",
        },
        "native_page_types": sorted(PAGE_TYPES),
        "first_page_semantics": (
            "section hp:visibility hideFirstHeader/hideFirstFooter/hideFirstPageNum; "
            "no synthetic FIRST applyPageType is admitted"
        ),
        "admitted_operations": [
            "set_story_variant",
            "remove_story_variant",
            "set_first_page_policy",
            "set_page_number_variant",
            "set_section_page_start",
            "add_section_boundary",
            "remove_section_boundary",
        ],
        "deferred_operations": dict(DEFERRED_OPERATIONS),
    }


def _bool_attr(node, name: str, default: bool = False) -> bool:
    value = node.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes"}


def _apply_reference(node, kind: str) -> str | None:
    candidates = {
        "header": {"idref", "headeridref", "headerref"},
        "footer": {"idref", "footeridref", "footerref"},
    }[kind]
    for key, value in node.attrib.items():
        if key.lower() in candidates and value:
            return value
    return None


def _story_payload(sec_pr, node, kind: str) -> dict:
    story_id = node.get("id")
    page_type = node.get("applyPageType", "BOTH")
    applies = []
    for apply in sec_pr.findall(f"{HP}{kind}Apply"):
        ref = _apply_reference(apply, kind)
        if (story_id and ref == story_id) or apply.get("applyPageType", "BOTH") == page_type:
            applies.append({
                "page_type": apply.get("applyPageType", "BOTH"),
                "id_ref": ref,
                "attrs": dict(sorted(apply.attrib.items())),
            })

    text = "".join(
        child.text or ""
        for child in node.iter()
        if _local(child.tag) == "t"
    )
    page_fields = []
    for child in node.iter():
        local = _local(child.tag)
        if local in {"autoNum", "newNum"}:
            page_fields.append({
                "tag": local,
                "attrs": dict(sorted(child.attrib.items())),
            })

    return {
        "kind": kind,
        "id": story_id,
        "page_type": page_type,
        "text": text,
        "page_number_fields": page_fields,
        "apply_links": applies,
        "linkage_exact": (
            len(applies) == 1
            and applies[0]["page_type"] == page_type
            and (not story_id or applies[0]["id_ref"] in {None, story_id})
        ),
    }


def build_story_layer_map(path: Path) -> dict:
    document = HwpxDocument.open(str(path))
    try:
        sections = []
        for section_index, section in enumerate(document.sections):
            sec_pr = next((n for n in section.element.iter() if _local(n.tag) == "secPr"), None)
            if sec_pr is None:
                raise ValueError(f"section {section_index} has no secPr")

            visibility = next((n for n in sec_pr if _local(n.tag) == "visibility"), None)
            if visibility is None:
                first_page = {
                    "hide_header": False,
                    "hide_footer": False,
                    "hide_page_number": False,
                }
            else:
                first_page = {
                    "hide_header": _bool_attr(visibility, "hideFirstHeader"),
                    "hide_footer": _bool_attr(visibility, "hideFirstFooter"),
                    "hide_page_number": _bool_attr(visibility, "hideFirstPageNum"),
                }

            stories = []
            for kind in ("header", "footer"):
                for node in sec_pr.findall(f"{HP}{kind}"):
                    stories.append(_story_payload(sec_pr, node, kind))

            sections.append({
                "section_index": section_index,
                "part_name": section.part_name,
                "first_page_policy": first_page,
                "stories": stories,
                "story_count": len(stories),
                "story_page_types": sorted({s["page_type"] for s in stories}),
                "linkage_exact": all(s["linkage_exact"] for s in stories),
            })
    finally:
        document.close()

    result = {
        "schema": SCHEMA,
        "section_count": len(sections),
        "sections": sections,
        "contract": story_layer_contract(),
    }
    result["story_layer_sha256"] = _sha(sections)
    return result


def _section_index(value: Any, count: int) -> int:
    index = int(value)
    if index < 0 or index >= count:
        raise ValueError(f"section_index {index} is outside admitted range")
    return index


def _page_type(value: Any) -> str:
    page_type = str(value or "BOTH").upper()
    if page_type not in PAGE_TYPES:
        raise ValueError("page_type must be BOTH, EVEN, or ODD")
    return page_type


def _kind(value: Any) -> str:
    kind = str(value or "").lower()
    if kind not in STORY_KINDS:
        raise ValueError("kind must be header or footer")
    return kind


def _set_story(section, kind: str, page_type: str, op: dict):
    props = section.properties
    if "text" in op:
        text = str(op.get("text") or "")
        return (
            props.set_header_text(text, page_type=page_type)
            if kind == "header"
            else props.set_footer_text(text, page_type=page_type)
        )
    if "content" in op:
        content = op["content"]
        if not isinstance(content, list):
            raise ValueError("story content must be a list")
        return (
            props.set_header_content(content, page_type=page_type)
            if kind == "header"
            else props.set_footer_content(content, page_type=page_type)
        )
    raise ValueError("set_story_variant requires text or content")


def _apply_first_page_policy(section, op: dict) -> dict:
    keys = {
        "hide_header": "hide_first_header",
        "hide_footer": "hide_first_footer",
        "hide_page_number": "hide_first_page_num",
    }
    kwargs = {
        target: bool(op[source])
        for source, target in keys.items()
        if source in op
    }
    if not kwargs:
        raise ValueError("set_first_page_policy requires at least one visibility field")
    section.properties.set_visibility(**kwargs)
    return kwargs


def _configure_new_section(document, section, spec: dict) -> dict:
    applied: list[dict] = []
    policy = spec.get("first_page_policy")
    if policy is not None:
        if not isinstance(policy, dict):
            raise ValueError("first_page_policy must be an object")
        applied.append({"first_page_policy": _apply_first_page_policy(section, policy)})

    stories = spec.get("stories", [])
    if not isinstance(stories, list):
        raise ValueError("stories must be a list")
    for story_spec in stories:
        if not isinstance(story_spec, dict):
            raise ValueError("each story spec must be an object")
        kind = _kind(story_spec.get("kind"))
        page_type = _page_type(story_spec.get("page_type", "BOTH"))
        story = _set_story(section, kind, page_type, story_spec)
        applied.append({
            "story": kind,
            "page_type": page_type,
            "story_id": story.id,
        })

    page_numbers = spec.get("page_numbers", [])
    if not isinstance(page_numbers, list):
        raise ValueError("page_numbers must be a list")
    section_index = list(document.sections).index(section)
    for number_spec in page_numbers:
        if not isinstance(number_spec, dict):
            raise ValueError("each page-number spec must be an object")
        target = _kind(number_spec.get("target", "footer"))
        page_type = _page_type(number_spec.get("page_type", "BOTH"))
        kwargs = {
            "section": section_index,
            "target": target,
            "page_type": page_type,
            "format": str(number_spec.get("format", "page")),
            "align": str(number_spec.get("align", "CENTER")).upper(),
            "position": str(number_spec.get("position", "BOTTOM_CENTER")).upper(),
            "prefix": str(number_spec.get("prefix", "")),
            "suffix": str(number_spec.get("suffix", "")),
        }
        if number_spec.get("format_type") is not None:
            kwargs["format_type"] = str(number_spec["format_type"])
        story = document.page.set_page_number(**kwargs)
        applied.append({
            "page_number": target,
            "page_type": page_type,
            "story_id": story.id,
        })
    return {"applied": applied}


def _apply_one(document: HwpxDocument, op: dict) -> dict:
    name = str(op.get("op") or "")
    if name in DEFERRED_OPERATIONS:
        raise ValueError(DEFERRED_OPERATIONS[name])

    section_count = len(document.sections)

    if name == "set_story_variant":
        section_index = _section_index(op.get("section_index", 0), section_count)
        section = document.sections[section_index]
        kind = _kind(op.get("kind"))
        page_type = _page_type(op.get("page_type", "BOTH"))
        story = _set_story(section, kind, page_type, op)
        return {
            "op": name,
            "section_index": section_index,
            "kind": kind,
            "page_type": page_type,
            "story_id": story.id,
        }

    if name == "remove_story_variant":
        section_index = _section_index(op.get("section_index", 0), section_count)
        section = document.sections[section_index]
        kind = _kind(op.get("kind"))
        page_type = _page_type(op.get("page_type", "BOTH"))
        if kind == "header":
            section.properties.remove_header(page_type=page_type)
        else:
            section.properties.remove_footer(page_type=page_type)
        return {
            "op": name,
            "section_index": section_index,
            "kind": kind,
            "page_type": page_type,
        }

    if name == "set_first_page_policy":
        section_index = _section_index(op.get("section_index", 0), section_count)
        section = document.sections[section_index]
        values = _apply_first_page_policy(section, op)
        return {"op": name, "section_index": section_index, "values": values}

    if name == "set_page_number_variant":
        section_index = _section_index(op.get("section_index", 0), section_count)
        target = _kind(op.get("target", "footer"))
        page_type = _page_type(op.get("page_type", "BOTH"))
        kwargs = {
            "section": section_index,
            "target": target,
            "page_type": page_type,
            "format": str(op.get("format", "page")),
            "align": str(op.get("align", "CENTER")).upper(),
            "position": str(op.get("position", "BOTTOM_CENTER")).upper(),
            "prefix": str(op.get("prefix", "")),
            "suffix": str(op.get("suffix", "")),
        }
        if op.get("format_type") is not None:
            kwargs["format_type"] = str(op["format_type"])
        story = document.page.set_page_number(**kwargs)
        return {
            "op": name,
            "section_index": section_index,
            "target": target,
            "page_type": page_type,
            "story_id": story.id,
        }

    if name == "set_section_page_start":
        section_index = _section_index(op.get("section_index", 0), section_count)
        number = int(op.get("number", 1))
        if number < 1:
            raise ValueError("section page start must be positive")
        page_starts_on = str(op.get("page_starts_on", "BOTH")).upper()
        if page_starts_on not in {"BOTH", "EVEN", "ODD"}:
            raise ValueError("page_starts_on must be BOTH, EVEN, or ODD")
        document.sections[section_index].properties.set_start_numbering(
            page_starts_on=page_starts_on,
            page=number,
        )
        return {
            "op": name,
            "section_index": section_index,
            "number": number,
            "page_starts_on": page_starts_on,
        }

    if name == "add_section_boundary":
        after = op.get("after")
        if after is None:
            section = document.add_section()
        else:
            after_index = _section_index(after, section_count)
            section = document.add_section(after=after_index)
        if op.get("text") is not None:
            section.add_paragraph(str(op["text"]), inherit_style=False)
        configured = _configure_new_section(document, section, op)
        return {
            "op": name,
            "section_count_after": len(document.sections),
            "part_name": section.part_name,
            **configured,
        }

    if name == "remove_section_boundary":
        if section_count <= 1:
            raise ValueError("cannot remove the last document section")
        section_index = _section_index(op.get("section_index", section_count - 1), section_count)
        document.remove_section(section_index)
        return {
            "op": name,
            "removed_section_index": section_index,
            "section_count_after": len(document.sections),
        }

    raise ValueError(f"Unsupported story-layer operation: {name}")


def apply_story_layer_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if int(expected_revision) != int(current_revision):
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")
    if not operations or len(operations) > 64:
        raise ValueError("Story-layer transaction requires 1..64 operations")
    if not all(isinstance(op, dict) for op in operations):
        raise ValueError("Each story-layer operation must be an object")

    before = build_story_layer_map(path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p324-story-",
        suffix=".hwpx",
        dir=str(path.parent),
    )
    os.close(fd)
    candidate = Path(tmp_name)
    candidate.write_bytes(path.read_bytes())
    receipts: list[dict] = []
    validation = None

    try:
        document = HwpxDocument.open(str(candidate))
        try:
            for op in operations:
                receipts.append(_apply_one(document, op))
            for section in document.sections:
                section.remove_layout_caches()
            _save_document(document, candidate, candidate)
        finally:
            document.close()

        after = build_story_layer_map(candidate)
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "before": {
            "section_count": before["section_count"],
            "story_layer_sha256": before["story_layer_sha256"],
        },
        "after": {
            "section_count": after["section_count"],
            "story_layer_sha256": after["story_layer_sha256"],
        },
        "story_layer_changed": before["story_layer_sha256"] != after["story_layer_sha256"],
        "section_count_changed": before["section_count"] != after["section_count"],
        "operation_count": len(operations),
        "operations": operations,
        "receipts": receipts,
        "validation": validation,
        "authority": "STRUCTURAL_STORY_LAYER_AUTHORITY_ONLY",
        "native_render_batch_status": "DEFERRED_BY_DESIGN",
    }
