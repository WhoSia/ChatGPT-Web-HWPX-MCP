from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
from hwpx_mcp.rendering.p411_visual_oracle import build_golden_registry, calibration_summary, load_calibration

out=Path("/tmp/p411-golden-registry.json")
cal=load_calibration()
result={
    "phase":"P4.11",
    "golden_registry":build_golden_registry(cal),
    "calibration_summary":calibration_summary(cal),
}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({
    "case_count":result["golden_registry"]["case_count"],
    "visual_regression_count":result["calibration_summary"]["visual_regression_count"],
    "alignment_promotion_eligible":result["calibration_summary"]["alignment_promotion_eligible"],
},ensure_ascii=False))
