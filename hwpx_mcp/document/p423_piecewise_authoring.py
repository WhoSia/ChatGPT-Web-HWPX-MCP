"""Product-oriented native EqEdit cases/piecewise authoring.

Use structural '&' columns and '#' rows. Never simulate alignment with a
guessed number of '~' spaces. An explicit optional gap is a user override,
not a measured visual guarantee.
"""
from __future__ import annotations

from dataclasses import dataclass

from hwpx.equation import latex_to_eqedit

MAX_ROWS = 24
MAX_LATEX_CHARS = 4096


@dataclass(frozen=True)
class PiecewiseAuthoring:
    script: str
    row_count: int
    has_conditions: bool


def build_piecewise_script(rows: object, *, condition_gap: int = 0) -> PiecewiseAuthoring:
    """Compile declarative rows to the native EqEdit cases environment.

    Each row is {"expression": LaTeX, "condition": LaTeX}. No raw EqEdit
    input is admitted, and callers cannot inject '&' or '#' delimiters as
    arbitrary row content. The converter validates supported LaTeX.
    """
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("piecewise rows must contain 1..24 objects")
    if type(condition_gap) is not int or not 0 <= condition_gap <= 4:
        raise ValueError("condition_gap must be an integer from 0 to 4")
    native_rows: list[str] = []
    condition_flags: list[bool] = []
    for row in rows:
        if not isinstance(row, dict) or not set(row).issubset({"expression", "condition"}):
            raise ValueError("piecewise row accepts expression and optional condition only")
        expression = row.get("expression")
        if not isinstance(expression, str) or not expression.strip() or len(expression) > MAX_LATEX_CHARS:
            raise ValueError("piecewise expression must be non-empty bounded LaTeX")
        if any(ch in expression for ch in ("&", "#")):
            raise ValueError("piecewise expression may not contain native alignment separators")
        expr_script = latex_to_eqedit(expression)
        condition = row.get("condition")
        condition_flags.append(condition is not None)
        if condition is None:
            if condition_gap:
                raise ValueError("condition_gap requires a condition in each row")
            native_rows.append(expr_script)
            continue
        if not isinstance(condition, str) or not condition.strip() or len(condition) > MAX_LATEX_CHARS:
            raise ValueError("piecewise condition must be non-empty bounded LaTeX")
        if any(ch in condition for ch in ("&", "#")):
            raise ValueError("piecewise condition may not contain native alignment separators")
        cond_script = latex_to_eqedit(condition)
        # The ampersand separates real grid columns; gap is an explicit user
        # override inside the second cell, not a hard-coded heuristic.
        native_rows.append(expr_script + " & " + ("~" * condition_gap) + cond_script)
    if any(flag != condition_flags[0] for flag in condition_flags):
        raise ValueError("piecewise rows must consistently have conditions")
    return PiecewiseAuthoring(
        script="cases {" + " # ".join(native_rows) + "}",
        row_count=len(native_rows),
        has_conditions=condition_flags[0],
    )
