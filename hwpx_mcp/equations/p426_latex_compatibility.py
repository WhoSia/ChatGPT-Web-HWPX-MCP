"""P4.26 small, explicit LaTeX spacing dialect adapter.

Only spacing control sequences are normalized, never math structural macros.
The "portable" policy is opt-in; upstream latex_to_eqedit remains the
single authoritative native script compiler. No claim of pixel fidelity.
"""
from __future__ import annotations

import hashlib
import re

SPACING_MACROS = frozenset({",", ";", ":", "!", "quad", "qquad"})
CONTROL_RE = re.compile(r"\\([A-Za-z]+|.)")


def normalize_equation_latex(latex: str, policy: str = "strict") -> dict:
    if policy not in ("strict", "portable"):
        raise ValueError("EQUATION_POLICY_INVALID")
    if not isinstance(latex, str) or not latex.strip() or len(latex) > 8192:
        raise ValueError("LATEX_EQUATION_INVALID")
    original = latex.strip()
    removed = []
    def replace(match: re.Match[str]) -> str:
        command = match.group(1)
        if command in SPACING_MACROS and policy == "portable":
            removed.append("\\" + command)
            return " "
        return match.group(0)
    adapted = CONTROL_RE.sub(replace, original)
    if not adapted.strip():
        raise ValueError("EQUATION_ONLY_SPACING_INVALID")
    return {
        "policy": policy,
        "original_latex": original,
        "normalized_latex": adapted,
        "removed_spacing_commands": removed,
        "spacing_adjusted": bool(removed),
        "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "normalized_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
        "visual_spacing_preserved": not bool(removed),
        "semantic_equivalence_claim": "STRUCTURAL_COMMANDS_UNCHANGED_SPACING_ONLY",
    }
