from __future__ import annotations

import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from hwpx_mcp.operations.p42_migration import adjudicate_upgrade, migration_contract, normalize_list_number_format, semantic_page_geometry

contract=migration_contract()
assert contract["phase"]=="P4.2"
assert contract["product"]=="0.28.0-p4.2"
assert normalize_list_number_format("^1.",level=1)[0]=="DIGIT"
assert semantic_page_geometry(59528,84189,"NARROWLY")["width"]==84189
ready=adjudicate_upgrade({
    "candidate_targeted_regressions":True,
    "real_document_matrix":True,
    "performance_budget":True,
    "candidate_docker":True,
    "rollback_rehearsal":True,
})
assert ready["verdict"]=="READY_FOR_PROMOTION_COMMIT"
print("P4.2 release smoke PASS")
