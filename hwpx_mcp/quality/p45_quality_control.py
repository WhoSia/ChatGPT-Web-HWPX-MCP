"""P4.5 quality-control policy; this module never acquires renderer authority."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from hwpx_mcp.quality.p44_health_intelligence import (
    canonical_corpus_provenance,
    canonical_release_observation,
    detect_longitudinal_drift,
    route_native_render_escalation,
)

PHASE = "P4.5"
PRODUCT = "0.31.0-p4.5"
MIN_RELEASES = 5


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def quality_control_contract() -> dict:
    body = {
        "schema": "chatgpt-web-hwpx-mcp/p4.5/quality-control/v1",
        "phase": PHASE,
        "product": PRODUCT,
        "authority_boundary": {
            "authoring": "python-hwpx==6.6.0",
            "quality_oracles": "observers only",
            "native_render": "explicit adjudication queue; no automatic world contact",
            "incident_store": "append-only events; lifecycle is derived",
        },
        "slo_governance": {"minimum_release_observations": MIN_RELEASES, "calibration": "median/MAD after a separate baseline is available"},
        "interop_authoring": {"equations": "LaTeX input converted to native EqEdit", "tables": "native HWPX table controls", "drawings": "native HWPX controls; render claims require native evidence"},
    }
    return {**body, "contract_sha256": _sha(body)}


def slo_readiness(observations: Sequence[Mapping[str, Any]], metric: str = "create_validate_p95_ms") -> dict:
    rows = [canonical_release_observation(x) for x in observations]
    count = len(rows)
    metric_count = sum(metric in row["metrics"] for row in rows)
    if metric_count < MIN_RELEASES:
        state = "PROVISIONAL_HARD_BUDGET"
    elif metric_count == MIN_RELEASES:
        state = "CALIBRATION_READY_PENDING_NEXT_OBSERVATION"
    else:
        state = "CALIBRATED_SLO_ACTIVE"
    return {
        "metric": metric,
        "release_observation_count": count,
        "metric_observation_count": metric_count,
        "state": state,
        "calibrated_slo": state == "CALIBRATED_SLO_ACTIVE",
        "reason": "five observations establish a frozen calibration cohort; the next observation is evaluated against it" if state != "CALIBRATED_SLO_ACTIVE" else "median/MAD budget is evaluated against a frozen prior cohort",
    }


def audit_feature_attribution(attribution: Mapping[str, Any], *, required_family: str = "") -> dict:
    candidates = list(attribution.get("candidates") or [])
    top = str(attribution.get("top_family") or "")
    abstain = bool(attribution.get("abstain"))
    required = required_family.strip().upper()
    verdict = "ABSTAIN" if abstain else ("MATCH" if not required or top == required else "MISMATCH")
    body = {"phase": PHASE, "required_family": required or None, "top_family": top or None, "top_confidence": float(attribution.get("top_confidence") or 0), "candidate_count": len(candidates), "verdict": verdict, "authority": "AUDIT_ONLY_NO_FORCED_RECLASSIFICATION"}
    return {**body, "audit_sha256": _sha(body)}


def create_incident_event(observation: Mapping[str, Any], *, incident_id: str = "", action: str = "OPEN", note: str = "") -> dict:
    action = action.upper()
    if action not in {"OPEN", "ACKNOWLEDGE", "RESOLVE", "REOPEN"}:
        raise ValueError("incident action must be OPEN, ACKNOWLEDGE, RESOLVE, or REOPEN")
    route = route_native_render_escalation(observation)
    incident = incident_id or "inc_" + _sha({"observation": dict(observation), "route": route})[:20]
    body = {"schema": "chatgpt-web-hwpx-mcp/p4.5/drift-incident-event/v1", "incident_id": incident, "action": action, "at": _now(), "note": str(note)[:1000], "observation": dict(observation), "routing": route}
    return {**body, "event_sha256": _sha(body)}


def derive_incident_lifecycle(events: Sequence[Mapping[str, Any]]) -> list[dict]:
    state: dict[str, dict] = {}
    for event in events:
        item = dict(event); iid = str(item.get("incident_id") or "")
        if not iid:
            continue
        action = str(item.get("action") or "").upper()
        previous = state.get(iid, {"incident_id": iid, "status": "UNKNOWN", "event_count": 0})
        transitions = {"OPEN": "OPEN", "ACKNOWLEDGE": "ACKNOWLEDGED", "RESOLVE": "RESOLVED", "REOPEN": "OPEN"}
        if action in transitions:
            state[iid] = {**previous, "status": transitions[action], "event_count": previous["event_count"] + 1, "last_event_sha256": item.get("event_sha256"), "native_render_route": (item.get("routing") or {}).get("route")}
    return [state[key] for key in sorted(state)]


def build_operator_alerts(observations: Sequence[Mapping[str, Any]], incidents: Sequence[Mapping[str, Any]]) -> dict:
    drift = detect_longitudinal_drift(observations) if observations else {"status": "INSUFFICIENT_HISTORY", "findings": []}
    lifecycle = derive_incident_lifecycle(incidents)
    alerts = []
    for finding in drift.get("findings", []):
        alerts.append({"kind": finding["kind"], "severity": finding["severity"], "delivery": "OPERATOR_PULL_ONLY"})
    for incident in lifecycle:
        if incident["status"] != "RESOLVED":
            alerts.append({"kind": "DRIFT_INCIDENT_" + incident["status"], "severity": "HIGH" if incident.get("native_render_route") == "NATIVE_RENDER_REQUIRED" else "MEDIUM", "incident_id": incident["incident_id"], "delivery": "OPERATOR_PULL_ONLY"})
    return {"phase": PHASE, "alerts": alerts, "alert_count": len(alerts), "notification_authority": "NO_EXTERNAL_NOTIFICATION_SIDE_EFFECT", "alerts_sha256": _sha(alerts)}


def active_corpus_governance(records: Sequence[Mapping[str, Any]]) -> dict:
    rows = [canonical_corpus_provenance(x) for x in records]
    blocking = [x for x in rows if x["blocking"]]
    fresh = [x for x in rows if x["source_kind"] == "LIVE_OFFICIAL_FRESHNESS"]
    return {"phase": PHASE, "record_count": len(rows), "blocking_record_count": len(blocking), "freshness_record_count": len(fresh), "freshness_is_release_blocking": False, "deduplicated_namespaces": sorted({x["federation_namespace"] for x in rows}), "authority": "PROVENANCE_FEDERATION_ONLY"}
