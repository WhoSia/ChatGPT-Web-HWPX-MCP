from __future__ import annotations

from mcp.types import ToolAnnotations

from hwpx_mcp.operations.p42_migration import adjudicate_upgrade, current_runtime_state, migration_contract

def register_p42_tools(core):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_dependency_migration_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **migration_contract()}

    @core.mcp.tool(annotations=read)
    def get_dependency_runtime_state() -> dict:
        core._caller_subject()
        return {"ok": True, **current_runtime_state()}

    @core.mcp.tool(annotations=read)
    def adjudicate_dependency_upgrade(evidence: dict) -> dict:
        core._caller_subject()
        result = adjudicate_upgrade(evidence)
        return {"ok": result["verdict"] == "READY_FOR_PROMOTION_COMMIT", **result}

    return {"phase": "P4.2", "authority": "SEMANTIC_MIGRATION_AND_PROMOTION_ADJUDICATION"}
