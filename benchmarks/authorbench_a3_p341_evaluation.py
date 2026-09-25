from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "artifacts" / "authorbench-a3-receipt.json"
OUT = ROOT / "artifacts" / "authorbench-a3-p341-evaluation.json"

A1_FAILURE_FAMILY = {
    "SECTION_HIERARCHY_CONTRAST_WEAK",
    "SECTION_SEPARATION_WEAK",
    "TABLE_CELL_PADDING_TIGHT",
    "TABLE_DENSITY_HIGH",
    "TABLE_HEADER_CONTRAST_WEAK",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    cases = list(payload.get("cases") or [])
    if len(cases) != 3:
        raise RuntimeError("AuthorBench A3 requires exactly three fresh archetype cases")

    checks = []
    all_ok = True
    for case in cases:
        path = ROOT / case["generated_file"]
        if not path.is_file():
            raise RuntimeError(f"missing A3 artifact: {path}")
        hash_ok = sha256_file(path) == case["sha256"]
        preview_ok = case["preview_verdict"] == "PASS"
        high_ok = int(case["static_high_count"]) == 0
        survivors = sorted(A1_FAILURE_FAMILY.intersection(case.get("static_finding_codes") or []))
        family_ok = not survivors
        semantic_ok = not case["semantic_finish_changed_text"] and not case["semantic_finish_changed_structure"]
        ok = hash_ok and preview_ok and high_ok and family_ok and semantic_ok
        all_ok = all_ok and ok
        checks.append({
            "id": case["id"],
            "archetype": case["archetype"],
            "hash_ok": hash_ok,
            "preview_ok": preview_ok,
            "high_severity_ok": high_ok,
            "a1_failure_family_survivors": survivors,
            "semantic_structure_preserved": semantic_ok,
            "verdict": "PASS" if ok else "FAIL",
        })

    result = {
        "schema": "authorbench/a3/p341-evaluation/v1",
        "phase": "P3.41",
        "fresh_cross_archetype_generalization": {
            "verdict": "PASS" if all_ok else "FAIL",
            "case_count": len(cases),
            "archetypes": [x["archetype"] for x in cases],
            "checks": checks,
            "authority": "FRESH_FIRST_PASS_STATIC_AND_NATIVE_STRUCTURE_BEFORE_A3_RENDER_CONTACT",
        },
        "polyglot_kernel": {
            "python_reference": "CI_REQUIRED",
            "rust_exact_kernel": "CI_REQUIRED",
            "typescript_contract": "CI_REQUIRED",
            "shared_fixture": "benchmarks/p341_page_geometry_golden.tsv",
        },
        "render_world_contact": "PENDING_EXTERNAL_HANCOM_WORLD_CONTACT",
        "human_review": "PENDING_AFTER_NATIVE_RENDER",
        "non_claim": "A3 static/structural pass is not yet page-composition native-render authority.",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
