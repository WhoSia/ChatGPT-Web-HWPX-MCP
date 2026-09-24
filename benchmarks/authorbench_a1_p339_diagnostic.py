from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from p339_design_intelligence import (
    diagnose_document_design,
    plan_design_repairs,
    prepare_authoring_strategy,
)

SOURCE = Path("artifacts/authorbench-a1-generative-ai-science.hwpx")
REVIEW = Path("benchmarks/authorbench_a1_human_review.json")
OUT = Path("artifacts/authorbench-a1-p339-diagnostic.json")
REPAIR = Path("artifacts/authorbench-a1-p339-repair-plan.json")

automatic = diagnose_document_design(SOURCE)
auto_codes = {item["code"] for item in automatic["findings"]}
if "TABLE_CELL_PADDING_TIGHT" not in auto_codes:
    raise RuntimeError(f"P3.39 failed to detect A1 table padding weakness: {sorted(auto_codes)}")

review = json.loads(REVIEW.read_text(encoding="utf-8"))
human_feedback = [
    {
        "code": item["code"],
        "severity": item["severity"],
        "note": item["summary"],
    }
    for item in review["findings"]
]
combined = diagnose_document_design(SOURCE, human_feedback=human_feedback)
strategy = prepare_authoring_strategy({
    "archetype": "POLISHED_REPORT",
    "semantic_outline": [
        "TITLE", "EXECUTIVE_SUMMARY", "KEY_JUDGMENT",
        "SECTION", "ANALYTICAL_TABLE", "SECTION", "RISK_CALLOUT",
        "SECTION", "CONCLUSION", "REFERENCES",
    ],
})
repair = plan_design_repairs(combined, strategy=strategy)

payload = {
    "schema": "authorbench/a1/p3.39-diagnostic/v1",
    "automatic": automatic,
    "human_review_fixture": review,
    "combined": combined,
    "strategy": strategy,
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
REPAIR.write_text(json.dumps(repair, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "status": "PASS",
    "automatic_codes": sorted(auto_codes),
    "combined_findings": combined["finding_count"],
    "repair_actions": len(repair["actions"]),
}, ensure_ascii=False))
