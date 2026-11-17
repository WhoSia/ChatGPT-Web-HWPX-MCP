"""Single-node phrase corrections in a native HWPX table cell."""
from __future__ import annotations

from hwpx.oxml._document_primitives import _clear_paragraph_layout_cache, _sanitize_text

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def validate_phrase_operation(operation: dict) -> None:
    index = operation.get("paragraph_index")
    if type(index) is not int or index < 0:
        raise ValueError("P427_CELL_PARAGRAPH_INDEX_INVALID")
    old = operation.get("old_text")
    new = operation.get("new_text")
    if (not isinstance(old, str) or not old or not isinstance(new, str)
            or old == new or any(_sanitize_text(value) != value or any(c in value for c in "\t\r\n")
                                 for value in (old, new))):
        raise ValueError("P427_CELL_PHRASE_INVALID")


def replace_phrase_in_plain_node(paragraph, old: str, new: str) -> None:
    """Modify one plain text node while retaining its native run and siblings."""
    nodes = paragraph.findall(f"{HP}run/{HP}t")
    if any(len(node) for node in nodes) or paragraph.find(f"{HP}run/{HP}tab") is not None:
        raise ValueError("P427_CELL_MIXED_TEXT_UNSUPPORTED")
    text = "".join(node.text or "" for node in nodes)
    start = text.find(old)
    if start < 0 or text.find(old, start + 1) >= 0:
        raise ValueError("P427_CELL_PHRASE_NOT_UNIQUE")
    stop = start + len(old)
    offset = 0
    for node in nodes:
        current = node.text or ""
        end = offset + len(current)
        if offset <= start and stop <= end:
            node.text = current[:start - offset] + new + current[stop - offset:]
            _clear_paragraph_layout_cache(paragraph)
            return
        offset = end
    raise ValueError("P427_CELL_PHRASE_CROSSES_RUNS")
