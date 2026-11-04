"""Read-only document-shell fingerprints for equation-edit acceptance.

This is a *text preservation* signal, not proof of layout or semantic identity.
Never return source paragraphs or publish private report text.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from .p423_equation_corpus import extract_equations, MAX_SECTION_BYTES


@dataclass(frozen=True)
class DocumentShell:
    paragraph_count: int
    text_fragment_count: int
    plain_text_sha256: str
    equation_count: int


def inspect_document_shell(path: str | Path) -> DocumentShell:
    """Digest all non-equation hp:t fragments, retaining text boundaries."""
    equations = extract_equations(path)  # validates package section bounds first
    paragraphs = 0
    fragments: list[str] = []
    with zipfile.ZipFile(path) as archive:
        sections = sorted(
            (name for name in archive.namelist()
             if name.startswith("Contents/section") and name.endswith(".xml")),
            key=lambda value: (len(value), value),
        )
        for name in sections:
            if archive.getinfo(name).file_size > MAX_SECTION_BYTES:
                raise ValueError("section too large")
            root = ET.fromstring(archive.read(name))
            for node in root.iter():
                tag = node.tag.split("}")[-1]
                if tag == "p":
                    paragraphs += 1
                if tag == "t":
                    fragments.append(node.text or "")
    digest = sha256()
    for fragment in fragments:
        raw = fragment.encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return DocumentShell(paragraphs, len(fragments), digest.hexdigest(), len(equations))


def compare_document_shell(before: DocumentShell, after: DocumentShell) -> dict[str, bool]:
    """Expose differences, not an unsupported native-render quality verdict."""
    return {
        "paragraph_count_preserved": before.paragraph_count == after.paragraph_count,
        "text_fragment_count_preserved": before.text_fragment_count == after.text_fragment_count,
        "text_exact_fragment_digest_preserved": before.plain_text_sha256 == after.plain_text_sha256,
        "equation_count_preserved": before.equation_count == after.equation_count,
    }
