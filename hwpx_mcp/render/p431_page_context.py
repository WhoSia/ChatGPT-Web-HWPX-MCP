"""Match rendered text to source paragraphs without claiming layout ownership."""
from collections import Counter
from xml.etree import ElementTree

from hwpx_mcp.document.p2_document import _local


def _compact(text: str) -> str:
    return "".join(text.split())


def page_paragraph_candidates(svg: bytes, paragraphs: list[dict], limit: int = 20) -> dict:
    root = ElementTree.fromstring(svg)
    if _local(root.tag) != "svg":
        raise ValueError("PAGE_CONTEXT_REQUIRES_SVG")
    # defs may contain reusable text that never appears on the page.
    def visible_text(node):
        if _local(node.tag) in {"defs", "metadata", "title", "desc"}:
            return
        if _local(node.tag) == "text":
            yield "".join(node.itertext())
            return
        for child in node:
            yield from visible_text(child)

    rendered = _compact("".join(visible_text(root)))
    counts = Counter(_compact(p["text"]) for p in paragraphs)
    matches = []
    total = 0
    for paragraph in paragraphs:
        text = _compact(paragraph["text"])
        if len(text) < 8 or text not in rendered:
            continue
        total += 1
        if len(matches) == limit:
            continue
        matches.append({
            "locator": paragraph["locator"],
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
        "truncated": total > len(matches),
        "complete_page_mapping": False,
        "limitations": [
            "Repeated text can match multiple paragraphs or pages.",
            "Paragraphs spanning pages and outlined glyphs may be absent.",
            "SVG text presence does not establish visibility or paragraph geometry.",
        ],
    }
