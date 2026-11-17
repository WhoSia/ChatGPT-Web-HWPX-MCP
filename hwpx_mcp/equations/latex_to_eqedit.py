"""Convert LaTeX with strict argument boundaries and the native EqEdit grammar."""
from __future__ import annotations

import re

from hwpx.equation.authoring import (
    MAX_GROUP_DEPTH,
    MAX_SOURCE_LENGTH,
    EquationConversionError,
    UnsupportedLatexError,
    _LatexLexer,
    _LatexParser,
    _strip_math_delimiters,
)


_ARGUMENT_BOUNDARIES = frozenset({"}", "^", "_", "&", r"\\", r"\right", r"\end"})
_EQEDIT_PART = re.compile(r'"[^"]*"|[_^]\{|[{}]|[^\s"{}^_]+|[_^]')


class _ArgumentBoundedParser(_LatexParser):
    """Use python-hwpx's EqEdit emission and intercept required math arguments."""

    def __init__(self, tokens: list[str]) -> None:
        super().__init__(tokens)
        self._sequence_stop: frozenset[str] = frozenset()

    def _sequence(self, *, depth: int, stop: frozenset[str]) -> list[str]:
        outer_stop = self._sequence_stop
        self._sequence_stop = stop
        try:
            return super()._sequence(depth=depth, stop=stop)
        finally:
            self._sequence_stop = outer_stop

    def _environment(self, depth: int) -> str:
        # A matrix cell has its own delimiters, even inside a root index.
        outer_stop = self._sequence_stop
        self._sequence_stop = frozenset()
        try:
            return super()._environment(depth)
        finally:
            self._sequence_stop = outer_stop

    def _group_or_atom(self, depth: int) -> str:
        token = self._peek()
        if token is None or token in _ARGUMENT_BOUNDARIES or token in self._sequence_stop:
            raise UnsupportedLatexError("missing LaTeX argument")
        if depth >= MAX_GROUP_DEPTH:
            raise EquationConversionError("equation nesting depth exceeded")
        if token == "{":
            return super()._group_or_atom(depth)

        # The lexer coalesces letter and number runs for EqEdit text. A bare
        # required argument consumes one source character of those runs.
        head = token[0]
        if len(token) > 1 and (head.isalpha() or head.isdigit() or head == "."):
            self._tokens[self._pos] = token[1:]
            return self._plain_token(head)

        # Consecutive unbraced commands may recurse without opening a brace.
        return super()._group_or_atom(depth + 1)


def _reject_duplicate_scripts(script: str) -> None:
    """Check consecutive postfix scripts in the native compiler's output."""
    scripts_by_group: list[set[str]] = [set()]
    for match in _EQEDIT_PART.finditer(script):
        part = match[0]
        if part in ("^{", "_{"):
            attached = scripts_by_group[-1]
            if part in attached:
                kind = "superscript" if part == "^{" else "subscript"
                raise UnsupportedLatexError(f"duplicate LaTeX {kind} on the same base")
            attached.add(part)
            scripts_by_group.append(set())
        elif part == "}":
            scripts_by_group.pop()
        else:
            # A normal atom, a grid separator or an explicit group ends the chain.
            scripts_by_group[-1].clear()
            if part == "{":
                scripts_by_group.append(set())


def latex_to_eqedit(latex: str) -> str:
    """Preserve required groups and consume one character from bare runs."""
    if len(latex) > MAX_SOURCE_LENGTH:
        raise EquationConversionError("LaTeX input exceeds size limit")
    source = _strip_math_delimiters(latex)
    if "$" in source:
        raise UnsupportedLatexError("interior $ math delimiters are not supported")
    if not source:
        raise UnsupportedLatexError("empty LaTeX input")
    script = _ArgumentBoundedParser(_LatexLexer(source).tokens).parse()
    _reject_duplicate_scripts(script)
    return script
