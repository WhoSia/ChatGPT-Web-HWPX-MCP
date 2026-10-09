from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.rendering.p46_native_authoring import (
    audit_equation_latex,
    compile_native_authoring_bundle,
    native_authoring_contract,
    real_document_benchmark_contract,
)

contract = native_authoring_contract()
assert contract["phase"] == "P4.6"
assert contract["product"] == "0.32.0-p4.6"
assert audit_equation_latex(r"\frac{a}{b}")["supported"] is True
assert audit_equation_latex(r"\mathbb{R}")["status"] == "UNSUPPORTED_MATH_STYLE"
assert audit_equation_latex(r"\mathcal{F}")["status"] == "UNSUPPORTED_MATH_STYLE"
compiled = compile_native_authoring_bundle(
    {"equations": [{"op": "insert_equation", "paragraph": "first_body", "latex": r"\frac{1}{2}"}]},
    document_map={"paragraphs": [{"locator": "p_anchor", "text": "Anchor"}]},
)
assert compiled["ready"] is True
assert real_document_benchmark_contract()["scenario_count"] >= 4
print("P4.6 native authoring fidelity smoke PASS")
