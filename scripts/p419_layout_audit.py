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


def stale_root_imports(source: str, retired: set[str]) -> set[str]:
    """Find relocated-root imports, including literal dynamic loader calls.

    Only recognized stdlib loaders count; a random method named find_spec
    must not make the production layout fail. Computed strings are left for
    the separate dependency census and executable smoke tests.
    """
    tree = ast.parse(source)
    aliases: set[str] = set()
    dynamic_functions = {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"importlib", "importlib.util", "runpy"}:
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module in {"importlib", "importlib.util", "runpy"}:
                for alias in node.names:
                    if alias.name in {"import_module", "find_spec", "run_module"}:
                        dynamic_functions.add(alias.asname or alias.name)

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = (node.module,)
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            if isinstance(func, ast.Name):
                admitted = func.id in dynamic_functions
            elif isinstance(func, ast.Attribute):
                # Recognize module-qualified imports, never unrelated objects.
                admitted = (
                    isinstance(func.value, ast.Name)
                    and func.value.id in aliases
                    and func.attr in {"import_module", "run_module", "find_spec"}
                )
            else:
                admitted = False
            if not admitted or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                continue
            names = (node.args[0].value,)
        else:
            continue
        for name in names:
            top_level = name.split(".", 1)[0]
            if top_level in retired:
                found.add(top_level)
    return found


def workflow_backlink_errors(root: Path, retired: set[str]) -> list[tuple[str, int, str]]:
    """Catch workflow paths that survive a move and broken unittest patterns.

    A test file passed to unittest discover -p must be a basename glob, not
    tests/test_name.py: the latter silently discovers zero tests.
    """
    problems: list[tuple[str, int, str]] = []
    for workflow in sorted((root / ".github/workflows").glob("*.yml")):
        for number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if re.search(r"\bunittest\s+discover\b.*?\s-p\s+tests[/\\]test_[\w.-]+\.py", line):
                problems.append((workflow.name, number, "BROKEN_DISCOVER_PATTERN"))
            # Bare, retired filenames in a workflow do not resolve in a clean
            # checkout, whether used by compileall, a script or path filter.
            for match in re.finditer(r"(?<![A-Za-z0-9_/])([A-Za-z][A-Za-z0-9_]*\.py)\b", line):
                candidate = match.group(1)
                if candidate[:-3] in retired:
                    problems.append((workflow.name, number, candidate))
            if "python -m compileall" in line or "python -m py_compile" in line:
                for token in line.split():
                    candidate = token.strip().strip(",;").strip(chr(39) + chr(34) + chr(92))
                    if candidate.endswith(".py") and not (root / candidate).is_file():
                        problems.append((workflow.name, number, f"MISSING_COMPILE_TARGET:{candidate}"))
    return sorted(set(problems))


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
    if len(root_python) > 30:
        raise AssertionError(f"Root Python module budget regressed: {len(root_python)} > 30")

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
    for source in ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "__pycache__", "artifacts"} for part in source.parts):
            continue
        bad = stale_root_imports(source.read_text(encoding="utf-8"), retired)
        if bad:
            raise AssertionError(f"Stale root import {sorted(bad)} in {source.relative_to(ROOT)}")

    workflow_errors = workflow_backlink_errors(ROOT, retired)
    if workflow_errors:
        raise AssertionError(f"Broken workflow backlinks: {workflow_errors[:16]}")

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
            "workflow_backlink_errors": len(workflow_errors),
            "result": "LAYOUT_CONTRACT_PASS"}


if __name__ == "__main__":
    import json
    print(json.dumps(audit(), ensure_ascii=False))
