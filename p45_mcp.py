from __future__ import annotations

from mcp.types import ToolAnnotations
from p45_quality_control import active_corpus_governance, audit_feature_attribution, build_operator_alerts, create_incident_event, derive_incident_lifecycle, quality_control_contract, slo_readiness


def register_p45_tools(core, store=None):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    append = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    incidents: list[dict] = []

    @core.mcp.tool(annotations=read)
    def get_calibrated_quality_control_contract() -> dict:
        core._caller_subject(); return {"ok": True, **quality_control_contract()}

    @core.mcp.tool(annotations=read)
    def get_slo_readiness(metric: str = "create_validate_p95_ms") -> dict:
        core._caller_subject(); rows = store.query_release_observations(limit=500) if store else []; return {"ok": True, **slo_readiness(rows, metric)}

    @core.mcp.tool(annotations=read)
    def audit_document_feature_attribution(document_id: str, required_family: str = "") -> dict:
        core._caller_subject(); meta = core._load_metadata(document_id); core._require_owner(meta); path, _ = core._paths(document_id)
        from p44_health_intelligence import attribute_hwpx_feature_families
        return {"ok": True, **audit_feature_attribution(attribute_hwpx_feature_families(path), required_family=required_family)}

    @core.mcp.tool(annotations=append)
    def append_drift_incident(observation: dict, incident_id: str = "", action: str = "OPEN", note: str = "") -> dict:
        core._caller_subject(); event = create_incident_event(observation, incident_id=incident_id, action=action, note=note); incidents.append(event); return {"ok": True, **event}

    @core.mcp.tool(annotations=read)
    def get_native_render_adjudication_queue() -> dict:
        core._caller_subject(); active = [x for x in derive_incident_lifecycle(incidents) if x["status"] != "RESOLVED" and x.get("native_render_route") == "NATIVE_RENDER_REQUIRED"]; return {"ok": True, "queue": active, "queue_count": len(active), "authority": "QUEUE_ONLY_NO_RENDERER_INVOCATION"}

    @core.mcp.tool(annotations=read)
    def get_operator_quality_alerts() -> dict:
        core._caller_subject(); rows = store.query_release_observations(limit=500) if store else []; return {"ok": True, **build_operator_alerts(rows, incidents)}

    @core.mcp.tool(annotations=read)
    def get_active_corpus_governance() -> dict:
        core._caller_subject(); rows = store.query_corpus_provenance(limit=2000) if store else []; return {"ok": True, **active_corpus_governance(rows)}
    return {"phase": "P4.5", "authority": "CALIBRATED_QUALITY_CONTROL_PLANE"}
