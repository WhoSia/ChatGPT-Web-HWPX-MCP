from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from p412_native_repair import defect_eradication_contract,compile_repaired_visual_payload

c=defect_eradication_contract()
assert c["phase"]=="P4.12"
assert c["product"]=="0.37.0-p4.12"
sample={
    "component_id":"bar","type":"bar_chart",
    "rows":[{"label":"A","value":1},{"label":"B","value":2}]
}
p=compile_repaired_visual_payload(sample)
assert p["primitive_family"]=="PARAGRAPH_TEXT_VISUALIZATION"
assert "A" in p["paragraph_text"] and "B" in p["paragraph_text"]
print("P4.12 native visual repair smoke PASS")
