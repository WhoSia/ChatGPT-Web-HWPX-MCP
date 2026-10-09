"""P4.19 layout gate: preserve tests and module backlinks during cleanup.

Run at repository root: python scripts/p419_layout_audit.py
This guard checks location contracts, not native Hancom fidelity.
"""
from __future__ import annotations

import ast
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
    if len(root_python) > 150:
        raise AssertionError(f"Root Python module budget regressed: {len(root_python)} > 150")

    return {"root_python": len(root_python), "root_test_python": 0,
            "tests_collected_files": len(tests),
            "p419_product_package": str(module.relative_to(ROOT)),
            "result": "LAYOUT_CONTRACT_PASS"}


if __name__ == "__main__":
    import json
    print(json.dumps(audit(), ensure_ascii=False))
