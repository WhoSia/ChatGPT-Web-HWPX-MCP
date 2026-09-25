from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "hwpx-authoring"
SKILL = SKILL_ROOT / "SKILL.md"
SERVER = ROOT / "server_p2.py"

REQUIRED_REFERENCES = (
    "references/evidence-authority.md",
    "references/page-composition.md",
)
REQUIRED_TOOL_NAMES = (
    "get_document_design_intelligence_contract",
    "prepare_authoring_strategy",
    "create_rich_document_and_deliver",
    "diagnose_document_design",
    "diagnose_rendered_document_design",
    "plan_executable_document_design_repairs",
    "apply_document_design_repairs",
    "compare_document_design_diagnostics",
    "get_page_composition_contract",
    "diagnose_page_composition",
    "plan_render_guided_page_layout",
    "compare_page_composition_diagnostics",
)
MAX_SKILL_LINES = 220


def _local_markdown_links(text: str) -> list[str]:
    return [
        target.split("#", 1)[0]
        for target in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", text)
        if target
        and not target.startswith(("http://", "https://", "mailto:", "#"))
    ]


def _balanced_fences(text: str) -> bool:
    backtick_fence = chr(96) * 3
    return sum(
        1
        for line in text.splitlines()
        if line.lstrip().startswith((backtick_fence, "~~~"))
    ) % 2 == 0


def validate() -> list[str]:
    failures: list[str] = []
    if not SKILL.is_file():
        return [f"missing skill: {SKILL.relative_to(ROOT)}"]

    text = SKILL.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not text.startswith("---\n"):
        failures.append("SKILL.md must start with YAML front matter")
    if not re.search(r"(?m)^name:\s*hwpx-authoring\s*$", text):
        failures.append("SKILL.md front matter must declare name: hwpx-authoring")
    if not re.search(r'(?m)^description:\s*".+"\s*$', text):
        failures.append("SKILL.md front matter must declare a quoted description")
    if len(lines) > MAX_SKILL_LINES:
        failures.append(
            f"SKILL.md is too long for a routing layer: {len(lines)} > {MAX_SKILL_LINES}"
        )
    if "\ufffd" in text:
        failures.append("SKILL.md contains replacement-character encoding damage")
    if not _balanced_fences(text):
        failures.append("SKILL.md has unbalanced fenced code blocks")

    for relative in REQUIRED_REFERENCES:
        path = SKILL_ROOT / relative
        if not path.is_file():
            failures.append(f"missing required skill reference: {relative}")
        if f"]({relative})" not in text:
            failures.append(f"SKILL.md does not route to required reference: {relative}")

    for target in _local_markdown_links(text):
        if not (SKILL_ROOT / target).resolve().is_file():
            failures.append(f"broken local skill link: {target}")

    reference_dir = SKILL_ROOT / "references"
    for path in reference_dir.glob("*.md"):
        reference = path.read_text(encoding="utf-8")
        if "\ufffd" in reference:
            failures.append(
                f"encoding damage in {path.relative_to(SKILL_ROOT).as_posix()}"
            )
        if not _balanced_fences(reference):
            failures.append(
                f"unbalanced fence in {path.relative_to(SKILL_ROOT).as_posix()}"
            )
        for target in _local_markdown_links(reference):
            resolved = (path.parent / target).resolve()
            if not resolved.is_file():
                failures.append(
                    f"broken local reference link in {path.name}: {target}"
                )

    server = SERVER.read_text(encoding="utf-8")
    for tool in REQUIRED_TOOL_NAMES:
        if tool not in text:
            failures.append(f"skill routing omits required tool: {tool}")
        if not re.search(rf"(?m)^def\s+{re.escape(tool)}\s*\(", server):
            failures.append(f"server surface omits skill-required tool: {tool}")

    evidence_reference = SKILL_ROOT / "references" / "evidence-authority.md"
    if evidence_reference.is_file():
        evidence_text = evidence_reference.read_text(encoding="utf-8")
        for phrase in (
            "No silent promotion",
            "USER_VISUAL_OBSERVATION",
            "Machine evidence can support the question but cannot satisfy",
        ):
            if phrase not in evidence_text:
                failures.append(
                    f"evidence reference lost required authority rule: {phrase}"
                )

    return failures


def main() -> int:
    failures = validate()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "PASS: hwpx-authoring skill routing, local references, evidence rules, "
        "and required MCP tool surface are structurally aligned. "
        "Structural validation only; native render and human review remain separate evidence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
