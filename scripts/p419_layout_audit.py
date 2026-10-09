"""P4.19 layout gate: preserve tests and module backlinks during cleanup.

Run at repository root: python scripts/p419_layout_audit.py
This guard checks location contracts, not native Hancom fidelity.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "tests"


def audit() -> dict:
    root_tests = sorted(p.name for p in ROOT.glob("test_*.py"))
    if root_tests:
        raise AssertionError(f"Top-level test modules must live in tests/: {root_tests[:10]}")

    tests = list(TEST_DIR.glob("test_*.py"))
    if len(tests) < 111:
        raise AssertionError(f"Test collection unexpectedly shrank: {len(tests)} < 111")

    module = ROOT / "hwpx_mcp/orchestration/p419_product.py"
    if not module.is_file():
        raise AssertionError("Consolidated P4.19 module is missing")
    for retired_root in ("p419_workspace.py", "p419_change_flow.py"):
        if (ROOT / retired_root).exists():
            raise AssertionError(f"Duplicated P4.19 root module remains: {retired_root}")

    public_sources = [ROOT / "server_p2.py", ROOT / "p418_mcp.py"]
    for path in public_sources:
        imports = [
            name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom) and node.module
            for name in [node.module]
        ]
        if "hwpx_mcp.orchestration.p419_product" not in imports:
            raise AssertionError(f"P4.19 public import still points outside its package: {path.name}")

    # Prevent newly added phase files from undoing the root cleanup.
    root_python = sorted(ROOT.glob("*.py"))
    if len(root_python) > 122:
        raise AssertionError(f"Root Python module budget regressed: {len(root_python)} > 122")

    corpus = ROOT / "hwpx_mcp" / "corpus"
    expected_corpus = ["p317_regression_corpus","p318_regression_corpus","p319_regression_corpus","p320_regression_corpus","p321_regression_corpus","p322_regression_corpus","p323_regression_corpus","p324_regression_corpus","p325_regression_corpus","p326_regression_corpus","p327_regression_corpus","p328_regression_corpus","p329_regression_corpus","p330_regression_corpus","p331_regression_corpus","p332_regression_corpus"]
    for name in expected_corpus:
        if (ROOT / (name + ".py")).is_file() or not (corpus / (name + ".py")).is_file():
            raise AssertionError("Regression corpus package placement mismatch: " + name)

    expected_interfaces = ["p411_mcp","p412_mcp","p413_mcp","p414_mcp","p415_mcp","p416_mcp","p417_mcp","p343_mcp", "p346_mcp", "p347_mcp", "p348_mcp", "p349_mcp"]
    for module_name in expected_interfaces:
        if (ROOT / (module_name + ".py")).exists() or not (ROOT / "hwpx_mcp" / "interfaces" / (module_name + ".py")).is_file():
            raise AssertionError("MCP facade package placement mismatch: " + module_name)

    # Detect stale imports across every checked-in Python source before CI
    # reaches an unrelated production or Hancom workflow.
    retired = set(expected_corpus) | set(expected_interfaces)
    for source in ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "__pycache__", "artifacts"} for part in source.parts):
            continue
        syntax_tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(syntax_tree):
            if isinstance(node, ast.Import):
                references = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                references = [node.module.split(".")[0]]
            else:
                continue
            bad = retired.intersection(references)
            if bad:
                raise AssertionError(f"Stale root import {sorted(bad)} in {source.relative_to(ROOT)}")

    # Moved test files must be referenced by their real paths in ALL workflow
    # invocations, not a mechanical replacement of implementation paths.
    # This catches the P3.46–P3.49 failure where
    # tests/test_hwpx_mcp/interfaces/p347_mcp.py was invented.
    missing_test_paths = []
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for match in re.finditer(r"(?<![A-Za-z0-9_/])tests/test_[A-Za-z0-9_./-]+\\.py\\b", text):
            candidate = match.group(0)
            if not (ROOT / candidate).is_file():
                missing_test_paths.append((workflow.name, candidate))
    if missing_test_paths:
        raise AssertionError(f"Workflow references missing test modules: {missing_test_paths[:12]}")

    return {"root_python": len(root_python), "root_test_python": 0,
            "tests_collected_files": len(tests),
            "p419_product_package": str(module.relative_to(ROOT)),
            "result": "LAYOUT_CONTRACT_PASS"}


if __name__ == "__main__":
    import json
    print(json.dumps(audit(), ensure_ascii=False))
