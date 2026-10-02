from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

from p411_visual_oracle import (
    build_golden_registry,
    evaluate_shadow_release_gate,
    evaluate_visual_slo,
    load_calibration,
)

def main(out: Path):
    calibration=load_calibration()
    registry=build_golden_registry(calibration)
    issues=[]
    for row in registry["archetypes"]:
        for code in row["observed_defects"]:
            issues.append({"code":code,"component_id":row["case_id"],"detail":"P4.10 calibration defect"})
    defects={"issues":issues}
    slo=evaluate_visual_slo(defects)
    gate=evaluate_shadow_release_gate(
        static_test_pass=True,
        structural_fidelity_pass=True,
        exact_head_docker_pass=True,
        native_capture_pass=True,
        visual_slo=slo,
        blocking=False,
    )
    result={"phase":"P4.11","registry":registry,"visual_slo":slo,"shadow_gate":gate}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"visual_slo":slo["status"],"promotion_eligible":gate["promotion_eligible"],"mode":gate["mode"]}))

if __name__=="__main__":
    main(Path("/tmp/p411-shadow-gate.json"))
