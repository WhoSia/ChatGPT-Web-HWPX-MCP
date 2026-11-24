"""Match rendered text to source paragraphs without claiming layout ownership."""
from collections import Counter
from xml.etree import ElementTree

from hwpx_mcp.document.p2_document import _local


def _compact(text: str) -> str:
    return "".join(text.split())


def page_paragraph_candidates(svg: bytes, paragraphs: list[dict], limit: int = 20, offset: int = 0) -> dict:
    if type(offset) is not int or offset < 0:
        raise ValueError("CANDIDATE_OFFSET_INVALID")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("CANDIDATE_LIMIT_INVALID")
    root = ElementTree.fromstring(svg)
    if _local(root.tag) != "svg":
        raise ValueError("PAGE_CONTEXT_REQUIRES_SVG")
    def text_fragments(node, in_text=False):
        tag = _local(node.tag)
        if tag in {"defs", "metadata", "title", "desc", "symbol", "clipPath", "mask", "pattern"}:
            return
        if node.get("display", "").strip() == "none":
            return
        in_text = in_text or tag == "text"
        if in_text and node.text:
            yield node.text
        for child in node:
            yield from text_fragments(child, in_text)
            if in_text and child.tail:
                yield child.tail

    rendered = _compact("".join(text_fragments(root)))
    counts = Counter(_compact(p["text"]) for p in paragraphs)
    matches = []
    total = 0
    for paragraph_offset, paragraph in enumerate(paragraphs):
        text = _compact(paragraph["text"])
        if len(text) < 8 or text not in rendered:
            continue
        total += 1
        if total <= offset or len(matches) == limit:
            continue
        matches.append({
            "locator": paragraph["locator"],
            "paragraph_offset": paragraph_offset,
            "section_index": paragraph["section_index"],
            "paragraph_index": paragraph["paragraph_index"],
            "container": paragraph["container"],
            "text": paragraph["text"][:200],
            "text_chars": len(paragraph["text"]),
            "text_sha256": paragraph["text_sha256"],
            "source_text_unique": counts[text] == 1,
        })
    return {
        "method": "WHITESPACE_NORMALIZED_FULL_PARAGRAPH_SUBSTRING",
        "candidate_count": total,
        "candidates": matches,
        "truncated": total > offset + len(matches),
        "next_candidate_offset": offset + limit if total > offset + limit else None,
        "complete_page_mapping": False,
        "limitations": [
            "Repeated text can match multiple paragraphs or pages.",
            "Paragraphs spanning pages and outlined glyphs may be absent.",
            "SVG text presence does not establish visibility or paragraph geometry.",
        ],
    }
