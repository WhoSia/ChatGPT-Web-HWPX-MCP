from __future__ import annotations

import copy
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

from hwpx import HwpxDocument

from p2_document import _local, _paragraph_nodes, build_document_map
from p22_formatting import (
    PARAGRAPH_FORMAT_KEYS,
    RUN_FORMAT_KEYS,
    _ensure_run_style,
    _range_safe_run,
    _run_text,
    build_formatting_map,
)


def _mm_to_hwp_units(value: float) -> int:
    return int(round(float(value) * 7200.0 / 25.4))


def _pt_to_hwp_units(value: float) -> int:
    return int(round(float(value) * 100.0))


def _format_index(format_map: dict) -> dict[str, dict]:
    return {item["locator"]: item for item in format_map["paragraphs"]}


def _text_run_indexes(paragraph: dict) -> list[int]:
    return [int(run["run_index"]) for run in paragraph["runs"] if run["text"]]


def _source_run(paragraph: dict, requested: object) -> dict:
    if requested is None:
        candidates = [run for run in paragraph["runs"] if run["text"]]
        if not candidates:
            raise ValueError("Source paragraph has no text-bearing run")
        return candidates[0]
    if not isinstance(requested, int) or requested < 0:
        raise ValueError("source_run_index must be a non-negative integer")
    for run in paragraph["runs"]:
        if int(run["run_index"]) == requested:
            return run
    raise ValueError("source_run_index is outside the source paragraph")


def _validate_range(paragraph: dict, start: object, end: object) -> tuple[int, int]:
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("start and end must be integer character offsets")
    length = int(paragraph["direct_text_length"])
    if start < 0 or end <= start or end > length:
        raise ValueError(
            f"Invalid rich-text range [{start}, {end}) for direct text length {length}"
        )
    touched = [
        run for run in paragraph["runs"]
        if int(run["end"]) > start and int(run["start"]) < end
    ]
    if not touched:
        raise ValueError("Rich-text range does not intersect a text run")
    unsafe = [int(run["run_index"]) for run in touched if not run["range_safe"]]
    if unsafe:
        raise ValueError(
            "Range formatting would split or rewrite a rich/control-bearing run; "
            f"unsupported run indexes: {unsafe}"
        )
    return start, end


def _normalize_operations(operations: list[dict], before_format: dict) -> list[dict]:
    if not operations:
        raise ValueError("At least one formatting operation is required")
    if len(operations) > 100:
        raise ValueError("Too many formatting operations")

    index = _format_index(before_format)
    normalized: list[dict] = []
    run_targets: set[tuple[str, int]] = set()
    range_targets: set[str] = set()
    paragraph_targets: set[str] = set()

    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("Each formatting operation must be an object")
        op = raw.get("op")

        if op == "normalize_formatting":
            target = raw.get("target")
            if target is not None and (not isinstance(target, str) or target not in index):
                raise ValueError(f"Unknown paragraph locator: {target}")
            normalized.append({"op": op, "target": target})
            continue

        target = raw.get("target")
        if not isinstance(target, str) or target not in index:
            raise ValueError(f"Unknown paragraph locator: {target}")
        paragraph = index[target]

        if op == "set_run_format":
            fmt = raw.get("format")
            if not isinstance(fmt, dict) or not fmt:
                raise ValueError("set_run_format requires a non-empty format object")
            unknown = sorted(set(fmt) - RUN_FORMAT_KEYS)
            if unknown:
                raise ValueError(f"Unsupported run format keys: {', '.join(unknown)}")
            if target in range_targets:
                raise ValueError("Cannot mix run-index and range mutation on one paragraph transaction")
            run_index = raw.get("run_index")
            if run_index is None:
                run_indexes = _text_run_indexes(paragraph)
                if not run_indexes:
                    raise ValueError("Target paragraph has no text run to format")
            else:
                if not isinstance(run_index, int) or run_index < 0:
                    raise ValueError("run_index must be a non-negative integer")
                if run_index >= len(paragraph["runs"]):
                    raise ValueError("run_index is outside the target paragraph")
                run_indexes = [run_index]
            for idx in run_indexes:
                key = (target, idx)
                if key in run_targets:
                    raise ValueError("Duplicate run-format target in one transaction")
                run_targets.add(key)
            normalized.append({
                "op": op,
                "target": target,
                "run_indexes": run_indexes,
                "format": dict(fmt),
            })
            continue

        if op == "set_range_format":
            fmt = raw.get("format")
            if not isinstance(fmt, dict) or not fmt:
                raise ValueError("set_range_format requires a non-empty format object")
            unknown = sorted(set(fmt) - RUN_FORMAT_KEYS)
            if unknown:
                raise ValueError(f"Unsupported run format keys: {', '.join(unknown)}")
            if any(key[0] == target for key in run_targets):
                raise ValueError("Cannot mix run-index and range mutation on one paragraph transaction")
            start, end = _validate_range(paragraph, raw.get("start"), raw.get("end"))
            range_targets.add(target)
            normalized.append({
                "op": op,
                "target": target,
                "start": start,
                "end": end,
                "format": dict(fmt),
            })
            continue

        if op == "copy_run_format":
            source = raw.get("source")
            if not isinstance(source, str) or source not in index:
                raise ValueError(f"Unknown source paragraph locator: {source}")
            source_run = _source_run(index[source], raw.get("source_run_index"))
            source_ref = source_run.get("char_pr_id_ref")
            if source_ref is None:
                raise ValueError("Source run has no charPrIDRef to reuse")
            if any(key[0] == target for key in run_targets):
                raise ValueError("Cannot mix run-index and copy/range mutation on one paragraph transaction")

            has_range = raw.get("start") is not None or raw.get("end") is not None
            target_run_index = raw.get("run_index")
            if has_range and target_run_index is not None:
                raise ValueError("copy_run_format accepts either a target range or run_index, not both")
            if has_range:
                start, end = _validate_range(paragraph, raw.get("start"), raw.get("end"))
                range_targets.add(target)
                normalized.append({
                    "op": op,
                    "target": target,
                    "source": source,
                    "source_run_index": int(source_run["run_index"]),
                    "char_pr_id_ref": str(source_ref),
                    "start": start,
                    "end": end,
                })
            else:
                if target in range_targets:
                    raise ValueError("Cannot mix range and run-index mutation on one paragraph transaction")
                if target_run_index is None:
                    run_indexes = _text_run_indexes(paragraph)
                    if not run_indexes:
                        raise ValueError("Target paragraph has no text run to format")
                else:
                    if not isinstance(target_run_index, int) or target_run_index < 0:
                        raise ValueError("run_index must be a non-negative integer")
                    if target_run_index >= len(paragraph["runs"]):
                        raise ValueError("run_index is outside the target paragraph")
                    run_indexes = [target_run_index]
                for idx in run_indexes:
                    key = (target, idx)
                    if key in run_targets:
                        raise ValueError("Duplicate run-format target in one transaction")
                    run_targets.add(key)
                normalized.append({
                    "op": op,
                    "target": target,
                    "source": source,
                    "source_run_index": int(source_run["run_index"]),
                    "char_pr_id_ref": str(source_ref),
                    "run_indexes": run_indexes,
                })
            continue

        if op == "set_paragraph_format":
            fmt = raw.get("format")
            if not isinstance(fmt, dict) or not fmt:
                raise ValueError("set_paragraph_format requires a non-empty format object")
            unknown = sorted(set(fmt) - PARAGRAPH_FORMAT_KEYS)
            if unknown:
                raise ValueError(f"Unsupported paragraph format keys: {', '.join(unknown)}")
            if target in paragraph_targets:
                raise ValueError("Duplicate paragraph-format target in one transaction")
            paragraph_targets.add(target)
            normalized.append({
                "op": op,
                "target": target,
                "format": dict(fmt),
            })
            continue

        if op == "copy_paragraph_format":
            source = raw.get("source")
            if not isinstance(source, str) or source not in index:
                raise ValueError(f"Unknown source paragraph locator: {source}")
            if target in paragraph_targets:
                raise ValueError("Duplicate paragraph-format target in one transaction")
            paragraph_targets.add(target)
            normalized.append({
                "op": op,
                "target": target,
                "source": source,
                "para_pr_id_ref": index[source].get("para_pr_id_ref"),
                "style_id_ref": index[source].get("style_id_ref"),
                "copy_named_style": bool(raw.get("copy_named_style", False)),
                "page_break": index[source].get("page_break"),
                "column_break": index[source].get("column_break"),
            })
            continue

        raise ValueError(f"Unsupported formatting operation: {op}")

    return normalized


def _paragraph_style_request(header, base_ref: str | None, fmt: dict) -> tuple[str | None, bool | None]:
    line_spacing = fmt.get("line_spacing_percent")
    if line_spacing is not None and float(line_spacing) <= 0:
        raise ValueError("line_spacing_percent must be positive")

    margins: dict[str, int] = {}
    if fmt.get("first_line_indent_mm") is not None:
        margins["intent"] = _mm_to_hwp_units(float(fmt["first_line_indent_mm"]))
    if fmt.get("indent_left_mm") is not None:
        margins["left"] = _mm_to_hwp_units(float(fmt["indent_left_mm"]))
    if fmt.get("indent_right_mm") is not None:
        margins["right"] = _mm_to_hwp_units(float(fmt["indent_right_mm"]))
    if fmt.get("spacing_before_pt") is not None:
        margins["prev"] = _pt_to_hwp_units(float(fmt["spacing_before_pt"]))
    if fmt.get("spacing_after_pt") is not None:
        margins["next"] = _pt_to_hwp_units(float(fmt["spacing_after_pt"]))

    heading = None
    if fmt.get("outline_level") is not None:
        level = int(fmt["outline_level"])
        if level < 0 or level > 10:
            raise ValueError("outline_level must be between 0 and 10")
        heading = (
            {"type": "NONE", "idRef": "0", "level": "0"}
            if level == 0
            else {"type": "OUTLINE", "idRef": "0", "level": str(level - 1)}
        )

    break_setting: dict[str, bool] = {}
    for key in ("keep_with_next", "keep_lines", "page_break_before"):
        if fmt.get(key) is not None:
            break_setting[key] = bool(fmt[key])

    wants_tabs = any(
        fmt.get(key) is not None
        for key in ("tab_stops", "auto_tab_left", "auto_tab_right")
    )
    tab_pr_id = None
    if wants_tabs:
        converted = []
        for idx, stop in enumerate(fmt.get("tab_stops") or []):
            if not isinstance(stop, dict) or stop.get("pos_mm") is None:
                raise ValueError(f"tab_stops[{idx}] requires pos_mm")
            converted.append({
                "pos": _mm_to_hwp_units(float(stop["pos_mm"])),
                "type": stop.get("type"),
                "leader": stop.get("leader"),
            })
        tab_pr_id = header.ensure_tab_definition(
            tab_stops=converted,
            auto_tab_left=bool(fmt.get("auto_tab_left")),
            auto_tab_right=bool(fmt.get("auto_tab_right")),
        )

    border = None
    if bool(fmt.get("bottom_border", False)):
        border_fill_id = header.ensure_border_fill(
            border_color=str(fmt.get("border_color", "#BFBFBF")),
            border_width=str(fmt.get("border_width", "0.12 mm")),
            active_borders=("bottom",),
        )
        border = {
            "borderFillIDRef": border_fill_id,
            "offsetLeft": "0",
            "offsetRight": "0",
            "offsetTop": "0",
            "offsetBottom": "0",
            "connect": "0",
            "ignoreMargin": "0",
        }

    wants_para = any([
        fmt.get("alignment") is not None,
        line_spacing is not None,
        bool(margins),
        heading is not None,
        bool(break_setting),
        wants_tabs,
        bool(fmt.get("bottom_border", False)),
    ])
    new_ref = base_ref
    if wants_para:
        new_ref = header.ensure_paragraph_format(
            base_para_pr_id=base_ref,
            alignment=fmt.get("alignment"),
            line_spacing_percent=line_spacing,
            margins=margins,
            heading=heading,
            border=border,
            break_setting=break_setting or None,
            tab_pr_id_ref=tab_pr_id,
        )
    column_break = (
        None if fmt.get("column_break") is None else bool(fmt.get("column_break"))
    )
    return (None if new_ref is None else str(new_ref), column_break)


def _save_document_to_candidate(document: HwpxDocument, candidate: Path, base: Path) -> None:
    fd, styled_name = tempfile.mkstemp(
        prefix=base.stem + ".p23-lib-", suffix=".hwpx", dir=str(base.parent)
    )
    os.close(fd)
    styled_path = Path(styled_name)
    try:
        document.save_to_path(str(styled_path))
        os.replace(styled_path, candidate)
    finally:
        try:
            styled_path.unlink()
        except FileNotFoundError:
            pass


def _set_run_text(run: ElementTree.Element, value: str) -> None:
    if not _range_safe_run(run):
        raise ValueError("Run is not safe for range splitting")
    text_node = list(run)[0]
    text_node.text = value


def _replace_run_with_pieces(
    paragraph: ElementTree.Element,
    run: ElementTree.Element,
    pieces: list[tuple[str, str | None]],
) -> None:
    children = list(paragraph)
    position = children.index(run)
    tail = run.tail
    paragraph.remove(run)
    built: list[ElementTree.Element] = []
    for text_value, char_ref in pieces:
        if not text_value:
            continue
        clone = copy.deepcopy(run)
        clone.tail = None
        _set_run_text(clone, text_value)
        if char_ref is None:
            clone.attrib.pop("charPrIDRef", None)
        else:
            clone.set("charPrIDRef", str(char_ref))
        built.append(clone)
    if not built:
        raise ValueError("Range split unexpectedly removed an entire run")
    built[-1].tail = tail
    for offset, clone in enumerate(built):
        paragraph.insert(position + offset, clone)


def _apply_range_ref(
    paragraph: ElementTree.Element,
    start: int,
    end: int,
    *,
    exact_ref: str | None = None,
    ref_by_base: dict[str | None, str] | None = None,
) -> None:
    runs = [child for child in list(paragraph) if _local(child.tag) == "run"]
    spans: list[tuple[ElementTree.Element, int, int, str]] = []
    offset = 0
    for run in runs:
        text = _run_text(run)
        spans.append((run, offset, offset + len(text), text))
        offset += len(text)
    if end > offset:
        raise ValueError("Target paragraph direct text changed during formatting transaction")

    touched = [entry for entry in spans if entry[2] > start and entry[1] < end]
    for run, run_start, run_end, text in reversed(touched):
        if not _range_safe_run(run):
            raise ValueError("Target range became unsafe during formatting transaction")
        base_ref = run.attrib.get("charPrIDRef")
        new_ref = exact_ref
        if new_ref is None:
            if ref_by_base is None or base_ref not in ref_by_base:
                raise ValueError("No prepared style for range base charPr")
            new_ref = ref_by_base[base_ref]
        local_start = max(0, start - run_start)
        local_end = min(len(text), end - run_start)
        if local_start == 0 and local_end == len(text):
            run.set("charPrIDRef", str(new_ref))
            continue
        pieces = [
            (text[:local_start], base_ref),
            (text[local_start:local_end], str(new_ref)),
            (text[local_end:], base_ref),
        ]
        _replace_run_with_pieces(paragraph, run, pieces)


def _normalize_paragraph_runs(paragraph: ElementTree.Element) -> int:
    merged = 0
    while True:
        runs = [child for child in list(paragraph) if _local(child.tag) == "run"]
        changed = False
        for left, right in zip(runs, runs[1:]):
            if not (_range_safe_run(left) and _range_safe_run(right)):
                continue
            if dict(left.attrib) != dict(right.attrib):
                continue
            left_text = _run_text(left)
            right_text = _run_text(right)
            if not left_text and not right_text:
                continue
            _set_run_text(left, left_text + right_text)
            left.tail = right.tail
            paragraph.remove(right)
            merged += 1
            changed = True
            break
        if not changed:
            return merged


def _clear_layout_cache(paragraph: ElementTree.Element) -> None:
    for child in list(paragraph):
        if _local(child.tag).lower() == "linesegarray":
            paragraph.remove(child)


def _patch_package(path: Path, prepared: list[dict]) -> dict:
    current_map = build_document_map(path)
    locator_index = {item["locator"]: item for item in current_map["paragraphs"]}
    by_section: dict[str, list[dict]] = {}
    normalize_all = any(op["op"] == "normalize_formatting" and op["target"] is None for op in prepared)

    for op in prepared:
        target = op.get("target")
        if target is None:
            continue
        mapped = locator_index.get(target)
        if mapped is None:
            raise ValueError("Formatting target locator did not survive header update")
        by_section.setdefault(mapped["section"], []).append({
            **op,
            "paragraph_index": int(mapped["paragraph_index"]),
        })

    normalized_merges = 0
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p23-patch-", suffix=".hwpx", dir=str(path.parent)
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(tmp_path, "w") as target_zip:
            for info in source.infolist():
                payload = source.read(info.filename)
                section_ops = by_section.get(info.filename, [])
                if section_ops or (normalize_all and info.filename.startswith("Contents/section")):
                    root = ElementTree.fromstring(payload)
                    paragraphs = _paragraph_nodes(root)
                    for op in section_ops:
                        paragraph = paragraphs[op["paragraph_index"]]
                        kind = op["op"]
                        if kind == "set_run_format":
                            runs = [child for child in list(paragraph) if _local(child.tag) == "run"]
                            for assignment in op["assignments"]:
                                idx = int(assignment["run_index"])
                                if idx >= len(runs):
                                    raise ValueError("Target run disappeared during formatting transaction")
                                runs[idx].set("charPrIDRef", str(assignment["char_pr_id_ref"]))
                            _clear_layout_cache(paragraph)
                        elif kind == "set_range_format":
                            _apply_range_ref(
                                paragraph, int(op["start"]), int(op["end"]),
                                ref_by_base=op["ref_by_base"],
                            )
                            _clear_layout_cache(paragraph)
                        elif kind == "copy_run_format":
                            if "start" in op:
                                _apply_range_ref(
                                    paragraph, int(op["start"]), int(op["end"]),
                                    exact_ref=str(op["char_pr_id_ref"]),
                                )
                            else:
                                runs = [child for child in list(paragraph) if _local(child.tag) == "run"]
                                for idx in op["run_indexes"]:
                                    if int(idx) >= len(runs):
                                        raise ValueError("Target run disappeared during formatting transaction")
                                    runs[int(idx)].set("charPrIDRef", str(op["char_pr_id_ref"]))
                            _clear_layout_cache(paragraph)
                        elif kind == "set_paragraph_format":
                            if op.get("para_pr_id_ref") is not None:
                                paragraph.set("paraPrIDRef", str(op["para_pr_id_ref"]))
                            if op.get("column_break") is not None:
                                paragraph.set("columnBreak", "1" if op["column_break"] else "0")
                            _clear_layout_cache(paragraph)
                        elif kind == "copy_paragraph_format":
                            ref = op.get("para_pr_id_ref")
                            if ref is None:
                                paragraph.attrib.pop("paraPrIDRef", None)
                            else:
                                paragraph.set("paraPrIDRef", str(ref))
                            if op.get("copy_named_style"):
                                style_ref = op.get("style_id_ref")
                                if style_ref is None:
                                    paragraph.attrib.pop("styleIDRef", None)
                                else:
                                    paragraph.set("styleIDRef", str(style_ref))
                            for attr, value in (("pageBreak", op.get("page_break")), ("columnBreak", op.get("column_break"))):
                                if value is None:
                                    paragraph.attrib.pop(attr, None)
                                else:
                                    paragraph.set(attr, str(value))
                            _clear_layout_cache(paragraph)
                        elif kind == "normalize_formatting":
                            normalized_merges += _normalize_paragraph_runs(paragraph)
                            _clear_layout_cache(paragraph)

                    if normalize_all:
                        for paragraph in paragraphs:
                            normalized_merges += _normalize_paragraph_runs(paragraph)
                            _clear_layout_cache(paragraph)
                    payload = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
                target_zip.writestr(info, payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return {"merged_adjacent_runs": normalized_merges}


def apply_rich_formatting_atomic(
    path: Path,
    operations: list[dict],
    *,
    expected_revision: int,
    current_revision: int,
    validator: Callable[[Path], dict] | None = None,
) -> dict:
    if expected_revision != current_revision:
        raise ValueError(f"Stale revision: expected {expected_revision}, current {current_revision}")

    before_document = build_document_map(path)
    before_format = build_formatting_map(path)
    before_index = _format_index(before_format)
    normalized = _normalize_operations(operations, before_format)

    fd, tmp_name = tempfile.mkstemp(
        prefix=path.stem + ".p23-", suffix=".hwpx", dir=str(path.parent)
    )
    os.close(fd)
    candidate = Path(tmp_name)
    shutil.copy2(path, candidate)
    validation = None
    prepared: list[dict] = []

    try:
        document = HwpxDocument.open(str(candidate))
        try:
            if not document.oxml.headers:
                raise ValueError("HWPX document has no header for style mutation")
            header = document.oxml.headers[0]

            for op in normalized:
                kind = op["op"]
                if kind == "set_run_format":
                    paragraph = before_index[op["target"]]
                    runs = {int(run["run_index"]): run for run in paragraph["runs"]}
                    assignments = []
                    for idx in op["run_indexes"]:
                        base_ref = runs[int(idx)].get("char_pr_id_ref")
                        new_ref = _ensure_run_style(document, base_ref, op["format"])
                        assignments.append({"run_index": int(idx), "char_pr_id_ref": str(new_ref)})
                    prepared.append({**op, "assignments": assignments})
                elif kind == "set_range_format":
                    paragraph = before_index[op["target"]]
                    touched = [
                        run for run in paragraph["runs"]
                        if int(run["end"]) > int(op["start"]) and int(run["start"]) < int(op["end"])
                    ]
                    refs: dict[str | None, str] = {}
                    for run in touched:
                        base_ref = run.get("char_pr_id_ref")
                        if base_ref not in refs:
                            refs[base_ref] = str(_ensure_run_style(document, base_ref, op["format"]))
                    prepared.append({**op, "ref_by_base": refs})
                elif kind == "set_paragraph_format":
                    paragraph = before_index[op["target"]]
                    new_ref, column_break = _paragraph_style_request(
                        header,
                        paragraph.get("para_pr_id_ref"),
                        op["format"],
                    )
                    prepared.append({
                        **op,
                        "para_pr_id_ref": new_ref,
                        "column_break": column_break,
                    })
                else:
                    prepared.append(dict(op))

            _save_document_to_candidate(document, candidate, path)
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()

        normalization = _patch_package(candidate, prepared)
        after_document = build_document_map(candidate)
        after_format = build_formatting_map(candidate)

        if before_document["semantic_sha256"] != after_document["semantic_sha256"]:
            raise ValueError("Formatting transaction changed document text; refusing commit")
        if before_document["structure_sha256"] != after_document["structure_sha256"]:
            raise ValueError("Formatting transaction changed paragraph structure; refusing commit")
        if validator is not None:
            validation = validator(candidate)
        os.replace(candidate, path)
    except Exception:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
        raise

    after_index = _format_index(after_format)
    changes = []
    for op in normalized:
        target = op.get("target")
        changes.append({
            "op": op["op"],
            "target": target,
            "source": op.get("source"),
            "before": before_index.get(target) if target else None,
            "after": after_index.get(target) if target else None,
            **({"start": op["start"], "end": op["end"]} if "start" in op else {}),
        })

    result = {
        "before": {
            "semantic_sha256": before_document["semantic_sha256"],
            "structure_sha256": before_document["structure_sha256"],
            "formatting_sha256": before_format["formatting_sha256"],
        },
        "after": {
            "semantic_sha256": after_document["semantic_sha256"],
            "structure_sha256": after_document["structure_sha256"],
            "formatting_sha256": after_format["formatting_sha256"],
        },
        "semantic_changed": False,
        "structure_changed": False,
        "formatting_changed": (
            before_format["formatting_sha256"] != after_format["formatting_sha256"]
        ),
        "operation_count": len(normalized),
        "changes": changes,
        "normalization": normalization,
    }
    if validation is not None:
        result["validation"] = validation
    return result
