from __future__ import annotations
import json
from p341_page_composition import compare_page_composition_diagnostics, diagnose_page_composition, page_composition_contract, plan_render_guided_layout_policy

def line(y: int, index: int, *, width: int = 430) -> dict:
    return {"x":100,"y":y,"width":width,"height":18,"baseline":y+18,"text_sha256":f"{index+1:064x}","paragraph_locator":f"p_{index//3}"}

def capture(lines: list[dict], raster: str) -> dict:
    return {"pages":[{"page_index":0,"width_px":1000,"height_px":1400,"raster_sha256":raster*64,"line_boxes":list(reversed(lines))}]}

contract=page_composition_contract()
assert contract["phase"]=="P3.41"
assert contract["polyglot"]["rule"]=="POLYGLOT_BY_COMPARATIVE_ADVANTAGE_NOT_LANGUAGE_COUNT"
balanced=diagnose_page_composition(capture([line(170+i*32,i) for i in range(24)],"a"),archetype="POLISHED_REPORT")
assert balanced["verdict"]!="REVIEW_REQUIRED"
crowded=diagnose_page_composition(capture([line(55+i*20,i,width=820) for i in range(62)],"b"),archetype="POLISHED_REPORT")
assert "PAGE_COMPOSITION_OVERFULL" in [x["code"] for x in crowded["findings"]]
policy=plan_render_guided_layout_policy(crowded)
assert policy["executable_count"]==0 and policy["agent_plan_count"]>=1
comparison=compare_page_composition_diagnostics({**crowded,"authority":"HANCOM_NATIVE_RENDER_EVIDENCE"},{**balanced,"authority":"HANCOM_NATIVE_RENDER_EVIDENCE"})
assert comparison["native_before_after_available"] is True
assert any(x["code"]=="PAGE_COMPOSITION_OVERFULL" for x in comparison["resolved"])
print(json.dumps({"status":"PASS","phase":"P3.41","balanced_verdict":balanced["verdict"],"crowded_findings":crowded["finding_count"],"policy_actions":policy["action_count"],"native_compare":comparison["authority"],"polyglot_rule":contract["polyglot"]["rule"]}))
