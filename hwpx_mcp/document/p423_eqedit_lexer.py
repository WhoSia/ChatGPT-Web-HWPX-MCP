"""Conservative lexer for Hancom EqEdit font state and structure.

The lexer never rewrites a script. Braces group syntax but do not restore font
state: Hancom requires an explicit 'it' after an upright segment. This is a
diagnostic, NOT a renderer or a complete grammar.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_FONT = ("rmbold", "boldrm", "rm", "it")
_STRUCTURE = ("left", "right", "box")
_MAX_LENGTH = 65536


@dataclass(frozen=True)
class EqEditToken:
    kind: str
    value: str
    offset: int
    depth: int


@dataclass(frozen=True)
class EqEditScan:
    tokens: tuple[EqEditToken, ...]
    issues: tuple[str, ...]
    final_font: str
    maximum_depth: int


def scan_eqedit(script: str) -> EqEditScan:
    """Scan explicit control tokens and brace nesting without interpretation.

    Identifiers enclosed in double quotes are literal. Font commands can be
    attached to capitalized words (e.g. 'rmA', 'itM'); lowercase word tails do
    not count. Offsets are exact indices into the original Python string.
    """
    if not isinstance(script, str):
        raise TypeError("EqEdit script must be str")
    if len(script) > _MAX_LENGTH:
        raise ValueError("EqEdit script exceeds diagnostic size limit")
    tokens: list[EqEditToken] = []
    issues: list[str] = []
    depth = highest = 0
    font = "italic"
    i = 0
    while i < len(script):
        char = script[i]
        if char == '"':
            end = script.find('"', i + 1)
            if end < 0:
                issues.append("unclosed_quote")
                break
            tokens.append(EqEditToken("literal", script[i:end + 1], i, depth))
            i = end + 1
            continue
        if char == "{":
            tokens.append(EqEditToken("open_group", "{", i, depth))
            depth += 1
            highest = max(highest, depth)
            i += 1
            continue
        if char == "}":
            if depth == 0:
                issues.append("extra_closing_brace")
            else:
                depth -= 1
            tokens.append(EqEditToken("close_group", "}", i, depth))
            i += 1
            continue
        if (i == 0 or not script[i - 1].isalpha()):
            found = False
            for command in _FONT + _STRUCTURE:
                if not script.startswith(command, i):
                    continue
                end = i + len(command)
                if end < len(script) and script[end].islower():
                    continue
                kind = "font" if command in _FONT else "structure"
                tokens.append(EqEditToken(kind, command, i, depth))
                if kind == "font":
                    font = "italic" if command == "it" else "upright"
                i = end
                found = True
                break
            if found:
                continue
        i += 1
    if depth:
        issues.append("unclosed_group")
    return EqEditScan(tuple(tokens), tuple(issues), font, highest)


def font_transitions(script: str) -> tuple[EqEditToken, ...]:
    """Return ordered font commands with source offsets and nesting depths."""
    return tuple(token for token in scan_eqedit(script).tokens if token.kind == "font")
