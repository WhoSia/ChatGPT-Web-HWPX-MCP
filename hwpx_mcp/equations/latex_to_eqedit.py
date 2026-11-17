"""Preserve single-token LaTeX scripts before native EqEdit conversion."""
from __future__ import annotations

import re

from hwpx.equation import latex_to_eqedit as _native_latex_to_eqedit
from hwpx.equation.authoring import UnsupportedLatexError


_CONTROL_OR_SCRIPT = re.compile(r"\\([^\W\d_]+|.)|[_^]", re.DOTALL)
_LITERAL_COMMANDS = frozenset({"text", "mathrm", "textrm", "mbox"})
_LITERAL_ARGUMENT = re.compile(r"\s*\{(?:\\.|[^{}\\])*\}", re.DOTALL)
_NEXT_ATOM = re.compile(r"\s*(\S)")
_EQEDIT_PART = re.compile(r'"[^"]*"|[_^]\{|[{}]|[^\s"{}^_]+|[_^]')


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
    """Use the native converter with TeX's unbraced script boundaries.

    The native lexer reads adjacent letters or digits as one token. After
    an unbraced script marker TeX consumes one token, so ``p_iS_i`` needs
    a boundary after ``i`` before the native lexer reads it.
    """
    pieces = []
    emitted_until = 0
    literal_end = 0
    for match in _CONTROL_OR_SCRIPT.finditer(latex):
        if match.start() < literal_end:
            continue
        command = match[1]
        if command is not None:
            if command in _LITERAL_COMMANDS:
                literal = _LITERAL_ARGUMENT.match(latex, match.end())
                if literal:
                    literal_end = literal.end()
            continue
        argument = _NEXT_ATOM.match(latex, match.end())
        if argument is None or argument[1] in "_^}&$":
            raise UnsupportedLatexError(f"missing LaTeX argument after {match[0]}")
        if argument.end() == len(latex):
            continue
        atom = argument[1]
        following = latex[argument.end()]
        joins_word = atom.isalpha() and following.isalpha()
        joins_number = (atom.isdigit() or atom == ".") and (following.isdigit() or following == ".")
        if joins_word or joins_number:
            pieces.extend((latex[emitted_until:argument.start(1)], "{", atom, "}"))
            emitted_until = argument.end()
    pieces.append(latex[emitted_until:])
    script = _native_latex_to_eqedit("".join(pieces))
    _reject_duplicate_scripts(script)
    return script
