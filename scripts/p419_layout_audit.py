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

    public_sources = [ROOT / "server_p2.py", ROOT / "hwpx_mcp/interfaces/p418_mcp.py"]
    for path in public_sources:
        imports = [
            name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom) and node.module
            for name in [node.module]
        ]
        if "hwpx_mcp.orchestration.p419_product" not in imports:
            raise AssertionError(f"P4.19 public import still points outside its package: {path.name}")

    # Inspect implementation shape beyond the top-level file count.
    # This is diagnostic until an explicit, independently verified budget
    # has been set; moving files must not manufacture a green architecture gate.
    package_modules = sorted((ROOT / "hwpx_mcp").rglob("*.py"))
    package_modules = [p for p in package_modules if p.name != "__init__.py"]
    module_sizes = {
        str(p.relative_to(ROOT)): len(p.read_bytes())
        for p in package_modules
    }
    oversized_modules = sorted(
        ((name, size) for name, size in module_sizes.items() if size > 50_000),
        key=lambda item: (-item[1], item[0]),
    )
    launcher_sizes = {
        name: (ROOT / name).stat().st_size
        for name in ("server.py", "server_p2.py")
        if (ROOT / name).is_file()
    }

    # Prevent newly added phase files from undoing the root cleanup.
    root_python = sorted(ROOT.glob("*.py"))
    if len(root_python) > 34:
        raise AssertionError(f"Root Python module budget regressed: {len(root_python)} > 34")

    corpus = ROOT / "hwpx_mcp" / "corpus"
    expected_corpus = ["p317_regression_corpus","p318_regression_corpus","p319_regression_corpus","p320_regression_corpus","p321_regression_corpus","p322_regression_corpus","p323_regression_corpus","p324_regression_corpus","p325_regression_corpus","p326_regression_corpus","p327_regression_corpus","p328_regression_corpus","p329_regression_corpus","p330_regression_corpus","p331_regression_corpus","p332_regression_corpus", "p335_atlas", "p335_corpus", "p335_paragraph", "p335_registry", "p335_typography", "p335_visual"]
    for name in expected_corpus:
        if (ROOT / (name + ".py")).is_file() or not (corpus / (name + ".py")).is_file():
            raise AssertionError("Regression corpus package placement mismatch: " + name)

    expected_interfaces = ["p411_mcp","p412_mcp","p413_mcp","p414_mcp","p415_mcp","p416_mcp","p417_mcp","p343_mcp", "p346_mcp", "p347_mcp", "p348_mcp", "p349_mcp", "p335_mcp"]
    for module_name in expected_interfaces:
        if (ROOT / (module_name + ".py")).exists() or not (ROOT / "hwpx_mcp" / "interfaces" / (module_name + ".py")).is_file():
            raise AssertionError("MCP facade package placement mismatch: " + module_name)

    expected_probes = ["p36_real_hwp_probe", "p36_rich_fixture_probe", "p37_equivalence_probe", "p37_nested_flow_probe"]
    for probe in expected_probes:
        if (ROOT / (probe + ".py")).exists() or not (ROOT / "hwpx_mcp/probes" / (probe + ".py")).is_file():
            raise AssertionError("Native probe package placement mismatch: " + probe)
    if (ROOT / "p39_textbox.py").exists() or not (ROOT / "hwpx_mcp/document/p39_textbox.py").is_file():
        raise AssertionError("Native textbox parser package placement mismatch")

    # P3.34 native operations retain independent implementations in document/.
    p334_native = ("p334_rare_feature_registry", "p334r1_column_insertion",
                   "p334r2_tracked_resolution", "p334r3_existing_group")
    for name in p334_native:
        if (ROOT / (name + ".py")).is_file() or not (ROOT / "hwpx_mcp/document" / (name + ".py")).is_file():
            raise AssertionError("P3.34 native document module misplaced: " + name)

    # P3.13-P3.16 evidence custody and version-replay family.
    capture_custody = ("p313_capture_custody", "p314_capture_intake",
                       "p315_cross_version", "p315_replay_builder",
                       "p316_stability_builder", "p316_version_indexed")
    for name in capture_custody:
        if (ROOT / (name + ".py")).exists() or not (ROOT / "hwpx_mcp/custody" / (name + ".py")).is_file():
            raise AssertionError("Capture and version custody package mismatch: " + name)

    # Detect stale imports across every checked-in Python source before CI
    # reaches an unrelated production or Hancom workflow.
    # Derive the migration map from real package files, not a fixed phase list.
    packaged = {
        p.stem
        for family in ("interfaces", "corpus", "probes", "document", "custody", "orchestration", "evidence", "quality", "rendering", "operations", "delivery", "extensions")
        for p in (ROOT / "hwpx_mcp" / family).glob("*.py")
        if p.name != "__init__.py"
    }
    retired = {name for name in packaged if not (ROOT / (name + ".py")).is_file()}
    dynamic_loaders = {"__import__", "import_module", "run_module", "find_spec"}
    for source in ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "__pycache__", "artifacts"} for part in source.parts):
            continue
        syntax_tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(syntax_tree):
            if isinstance(node, ast.Import):
                references = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                references = [node.module.split(".")[0]]
            elif isinstance(node, ast.Call):
                # importlib.import_module("old_module"), __import__("old_module"),
                # runpy.run_module("old_module"), and find_spec("old_module").
                # Bare loader names are checked too; nonliteral arguments require
                # manual review by the dependency inventory.
                func = node.func
                loader = func.id if isinstance(func, ast.Name) else (
                    func.attr if isinstance(func, ast.Attribute) else None
                )
                if loader in dynamic_loaders and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    references = [node.args[0].value.split(".")[0]]
                else:
                    continue
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
        for match in re.finditer(r"(?<![A-Za-z0-9_/])tests/test_[A-Za-z0-9_./-]+\.py\b", text):
            candidate = match.group(0)
            if not (ROOT / candidate).is_file():
                missing_test_paths.append((workflow.name, candidate))
    if missing_test_paths:
        raise AssertionError(f"Workflow references missing test modules: {missing_test_paths[:12]}")

    return {"root_python": len(root_python), "root_test_python": 0,
            "tests_collected_files": len(tests),
            "p419_product_package": str(module.relative_to(ROOT)),
            "package_implementation_modules": len(package_modules),
            "oversized_packaged_modules_bytes_gt_50000": oversized_modules,
            "launcher_sizes_bytes": launcher_sizes,
            "result": "LAYOUT_CONTRACT_PASS"}


if __name__ == "__main__":
    import json
    print(json.dumps(audit(), ensure_ascii=False))
