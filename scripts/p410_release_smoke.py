from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hwpx_mcp.quality.p410_closure import PRODUCT, adjudicate_closure, closure_contract

contract = closure_contract()
assert contract["phase"] == "P4.10"
assert contract["product"] == PRODUCT == "0.35.0-p4.10"
assert contract["inherits"]["p49_geometry_safe_lowering"] == "IMPLEMENTED"
pending = adjudicate_closure(None)
assert pending["status"] == "HUMAN_RENDER_EVIDENCE_PENDING"
assert pending["geometry_authority_promoted"] is False
print("P4.10 closure contract smoke PASS")
