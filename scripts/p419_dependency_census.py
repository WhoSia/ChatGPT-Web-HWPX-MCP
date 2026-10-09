"""P4.19 migration census: inventory root modules and their backlinks.

This is a non-destructive discovery aid; low reference counts do NOT prove a
module is unused, since plugins and entrypoints may be dynamically resolved.
Run from any directory: python scripts/p419_dependency_census.py
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_TEXT_CONFIG_SUFFIXES = {".yml", ".yaml", ".toml", ".sh", ".ps1", ".cmd", ".bat", ".json"}
_SCAN_SKIP = {".git", ".venv", "__pycache__", "artifacts", ".pytest_cache", ".mypy_cache"}


def _python_references(content: str, module_names: set[str]) -> set[str]:
    """Collect direct imports and literal dynamic imports; no code execution."""
    tree = ast.parse(content)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                first = alias.name.split(".", 1)[0]
                if first in module_names:
                    found.add(first)
        elif isinstance(node, ast.ImportFrom) and node.module:
            first = node.module.split(".", 1)[0]
            if first in module_names:
                found.add(first)
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            dynamic_import = (isinstance(func, ast.Name) and func.id == "__import__") or (
                isinstance(func, ast.Attribute) and func.attr == "import_module"
                and isinstance(func.value, ast.Name) and func.value.id == "importlib"
            )
            if dynamic_import and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                first = node.args[0].value.split(".", 1)[0]
                if first in module_names:
                    found.add(first)
    return found


def census(root: Path = ROOT) -> dict:
    files = sorted(root.glob("*.py"))
    module_names = {file.stem for file in files}
    backlinks: dict[str, set[str]] = defaultdict(set)
    dynamic_candidates: dict[str, set[str]] = defaultdict(set)
    for source in root.rglob("*"):
        if not source.is_file() or any(p in _SCAN_SKIP for p in source.relative_to(root).parts):
            continue
        relative = source.relative_to(root).as_posix()
        if source.suffix == ".py":
            # Syntax errors must fail the audit, never silently drop a backlink.
            text = source.read_text(encoding="utf-8")
            for name in _python_references(text, module_names):
                if relative != name + ".py":
                    backlinks[name].add(relative)
            # Literal string usage may be dynamic path resolution, CLI, or
            # documentation; flag separately and do not treat as zero-risk.
            for name in module_names:
                if name in text and name not in _python_references(text, module_names):
                    if relative != name + ".py":
                        dynamic_candidates[name].add(relative)
        elif source.suffix in _TEXT_CONFIG_SUFFIXES or source.name == "Dockerfile":
            try:
                text = source.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for name in module_names:
                if re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text):
                    backlinks[name].add(relative)
    modules = []
    for file in files:
        name = file.stem
        modules.append({
            "module": name,
            "root_path": file.name,
            "bytes": file.stat().st_size,
            "explicit_backlinks": sorted(backlinks[name]),
            "literal_string_candidates": sorted(dynamic_candidates[name] - backlinks[name]),
            "explicit_backlink_count": len(backlinks[name]),
            "review_status": "REQUIRES_MANUAL_REVIEW",
        })
    return {
        "schema": "chatgpt-web-hwpx-mcp/p4.19/root-dependency-census/v1",
        "root_module_count": len(modules),
        "modules": modules,
        "caution": "Zero backlinks is not proof of dead code; do not delete based on this inventory.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args()
    report = census()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    top = sorted(report["modules"], key=lambda row: (-row["explicit_backlink_count"], row["module"]))
    print(json.dumps({
        "schema": report["schema"],
        "root_module_count": report["root_module_count"],
        "most_connected": [{"module": row["module"], "backlinks": row["explicit_backlink_count"]}
                           for row in top[:max(0, args.top)]],
        "zero_explicit_backlink_count": sum(not row["explicit_backlinks"] for row in report["modules"]),
        "note": report["caution"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
