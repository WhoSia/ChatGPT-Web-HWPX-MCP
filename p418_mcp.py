from __future__ import annotations

import os
from typing import Any, Callable

from mcp.types import CallToolResult, ToolAnnotations

from p418_product import PHASE, PRODUCT, document_agent_contract, prepare_document_task
from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
from hwpx_mcp.orchestration.p418_p2_preview import preview_workflow, correct_workflow
from hwpx_mcp.orchestration.p418_p2_admission import get_durable_approval_ledger, AdmissionError
from hwpx_mcp.orchestration.p418_p3_review_store import get_native_review_store


def _structured(result: Any) -> dict:
    if isinstance(result, dict):
        return dict(result)
    if isinstance(result, CallToolResult):
        value = getattr(result, "structured_content", None)
        if not isinstance(value, dict):
            value = getattr(result, "structuredContent", None)
        if not isinstance(value, dict):
            dumped = result.model_dump(by_alias=True)
            value = dumped.get("structuredContent") or dumped.get("structured_content")
        if isinstance(value, dict):
            return dict(value)
    return {}


def _augment(result: Any, extra: dict) -> Any:
    if isinstance(result, dict):
        return {**result, **extra}
    if isinstance(result, CallToolResult):
        payload = result.model_dump(by_alias=True)
        payload.pop("structured_content", None)
        payload["structuredContent"] = {**_structured(result), **extra}
        return CallToolResult.model_validate(payload)
    return result


def register_p418_tools(
    core,
    *,
    create_adapter: Callable[..., Any],
    edit_intent_adapter: Callable[..., dict],
    template_fill_adapter: Callable[..., Any],
    deliver_adapter: Callable[..., Any],
    inspect_adapter: Callable[[str], dict],
    semantic_graph_adapter: Callable[[str], dict],
    document_map_adapter: Callable[[str], dict],
):
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

    @core.mcp.tool(annotations=read)
    def get_p418_document_agent_contract() -> dict:
        core._caller_subject()
        return {"ok": True, **document_agent_contract()}

    @core.mcp.tool(annotations=read)
    def prepare_p418_document_task(task: dict) -> dict:
        core._caller_subject()
        return {"ok": True, **prepare_document_task(task)}

    @core.mcp.tool(annotations=read)
    def compile_p418_document_workflow(specification: dict, documents: list[dict]) -> dict:
        """Non-mutating workflow draft; caller catalog grants no ownership or approval."""
        core._caller_subject()
        return {"ok": True, **compile_workflow(specification, documents)}

    @core.mcp.tool(annotations=read)
    def preview_p418_document_workflow(draft: dict) -> dict:
        """Informational preview only; never produces approval or mutation authority."""
        core._caller_subject()
        return {"ok": True, **preview_workflow(draft)}

    @core.mcp.tool(annotations=read)
    def correct_p418_document_workflow(specification: dict, corrections: list[dict], documents: list[dict]) -> dict:
        """Correct draft input and invalidate any prior preview or approval."""
        core._caller_subject()
        return {"ok": True, **correct_workflow(specification, corrections, documents)}

    @core.mcp.tool(annotations=write)
    def stage_p418_document_workflow(draft: dict, preview: dict) -> dict:
        """Persist an unapproved workflow with server-verified document custody.

        This does not approve or execute a mutation. A future trusted host
        confirmation channel is required to turn STAGED into APPROVED.
        """
        owner = core._caller_subject()
        verified_preview = preview_workflow(draft)
        if not isinstance(preview, dict) or preview != verified_preview:
            raise AdmissionError("preview does not match canonical server preflight")
        # Recompile the submitted tasks against the supplied snapshot before
        # reading authoritative server custody. A caller-created SHA proves
        # neither authenticity nor that a normalized task is internally valid.
        from hwpx_mcp.orchestration.p418_p2_workflow import compile_workflow
        supplied_steps = draft["steps"]
        supplied_bindings = draft.get("resolved_inputs", {})
        document_ids = {
            row["document_id"] for row in supplied_bindings.values()
        }
        for step in supplied_steps:
            for field in ("document_id", "template_document_id", "reference_document_id"):
                doc_id = step["task"].get(field)
                if doc_id:
                    document_ids.add(doc_id)
        candidate_catalog = []
        for doc_id in sorted(document_ids):
            metadata = core._load_metadata(doc_id)
            core._require_owner(metadata)
            candidate_catalog.append({
                "document_id": doc_id, "revision": int(metadata["revision"])
            })
        try:
            reconstructed = compile_workflow(
                {"steps": [{"task": dict(step["task"])} for step in supplied_steps],
                 "input_bindings": {role: row["document_id"] for role, row in supplied_bindings.items()}},
                candidate_catalog)
        except ValueError as exc:
            raise AdmissionError("server-owned document revision changed or draft invalid") from exc
        if reconstructed != draft:
            raise AdmissionError("submitted draft was not canonically compiled")
        mutation_steps = [s for s in draft["steps"] if s["effect"] == "MUTATION"]
        if len(mutation_steps) != 1:
            raise AdmissionError("exactly one mutation required for admission")
        task = mutation_steps[0]["task"]
        identity_rows = []
        for field in ("document_id", "template_document_id", "reference_document_id"):
            document_id = task.get(field)
            if not document_id:
                continue
            metadata = core._load_metadata(document_id)
            core._require_owner(metadata)
            expected = task.get("expected_revision") if field == "document_id" else None
            if expected is not None and int(metadata["revision"]) != expected:
                raise AdmissionError("server-owned document revision changed")
            identity_rows.append({"role": field, "document_id": document_id,
                                  "revision": int(metadata["revision"]),
                                  "sha256": str(metadata.get("sha256", ""))})
        store = getattr(core, "DOCUMENT_STORE", None)
        url = getattr(store, "database_url", None)
        if not url:
            raise AdmissionError("PostgreSQL durable custody required for workflow admission")
        # P3 supports a trusted host review only when the exact normalized
        # effect can survive a server restart in encrypted durable custody.
        # Do not strand an executable approval without its reviewed payload.
        secret = getattr(core, "STATE_SECRET", "")
        if task["kind"] == "EDIT_INTENT" and (not isinstance(secret, str) or len(secret) < 32):
            raise AdmissionError("encrypted server-side review secret required")
        ledger = get_durable_approval_ledger(url)
        staged_bindings = {"documents": identity_rows}
        record = ledger.stage(
            owner=owner, draft_sha256=draft["draft_sha256"],
            preview_sha256=verified_preview["preview_sha256"],
            bound_inputs=staged_bindings,
            effect_scope=task["kind"])
        if task["kind"] == "EDIT_INTENT":
            try:
                get_native_review_store(url, secret).persist_staged(
                    owner=owner, workflow_id=record["workflow_id"],
                    draft=draft, preview=verified_preview,
                    bound_inputs=staged_bindings)
            except Exception:
                ledger.abort_unclaimed(owner=owner, workflow_id=record["workflow_id"])
                raise
        host_ready = (
            task["kind"] == "EDIT_INTENT"
            and len(os.environ.get("P418_HOST_REVIEW_PASSPHRASE", "")) >= 24
            and len(os.environ.get("P418_HOST_APPROVAL_SIGNING_SECRET", "")) >= 32
        )
        review_url = (
            str(getattr(core, "PUBLIC_BASE_URL", "")).rstrip("/")
            + "/p418/host/review?workflow_id=" + record["workflow_id"]
            if host_ready and str(getattr(core, "PUBLIC_BASE_URL", "")).startswith("https://")
            else None
        )
        return {"ok": True, **record,
                "human_review_url": review_url,
                "human_approval_enabled": review_url is not None,
                "authority": "SERVER_VERIFIED_STAGING_ONLY_NO_APPROVAL_OR_EXECUTION"}

    @core.mcp.tool(annotations=write)
    def recover_p418_document_workflow(workflow_id: str) -> dict:
        """Quarantine an unresolved claimed mutation and return recovery disposition."""
        owner = core._caller_subject()
        store = getattr(core, "DOCUMENT_STORE", None)
        url = getattr(store, "database_url", None)
        if not url:
            raise AdmissionError("PostgreSQL durable custody required for recovery")
        return {"ok": True, **get_durable_approval_ledger(url).recover(
            owner=owner, workflow_id=workflow_id)}

    @core.mcp.tool(annotations=write)
    def run_p418_document_task(task: dict):
        core._caller_subject()
        prepared = prepare_document_task(task)
        normalized = prepared["task"]
        kind = normalized["kind"]
        task_receipt = {
            "phase": PHASE,
            "product": PRODUCT,
            "p418_task_kind": kind,
            "p418_task_sha256": normalized["task_sha256"],
            "p418_route": prepared["route"],
        }

        if kind == "CREATE":
            result = create_adapter(
                normalized["plan"],
                normalized["filename"],
                normalized["request_id"],
                normalized["design_mode"],
                normalized["explicit_tokens"],
                normalized["link_ttl_seconds"],
            )
            return _augment(result, task_receipt)

        if kind == "TEMPLATE_FILL":
            result = template_fill_adapter(
                normalized["template_document_id"],
                normalized["values"],
                normalized["filename"],
                normalized["request_id"],
                normalized["require_each"],
                normalized["require_unique"],
                normalized["link_ttl_seconds"],
            )
            return _augment(result, task_receipt)

        if kind == "DELIVER":
            result = deliver_adapter(
                normalized["document_id"],
                normalized["revision"],
                normalized["link_ttl_seconds"],
            )
            return _augment(result, task_receipt)

        if kind == "EDIT_INTENT":
            execution = edit_intent_adapter(
                document_id=normalized["document_id"],
                expected_revision=normalized["expected_revision"],
                intent=normalized["intent"],
                reference_document_id=normalized["reference_document_id"],
                reference_transfer=normalized["reference_transfer"],
                repair_plan=normalized["repair_plan"],
                replan_intent=normalized["replan_intent"],
                lease_token=normalized["lease_token"],
            )
            if not execution.get("ok"):
                return {
                    **execution,
                    **task_receipt,
                    "delivery_status": "NOT_ATTEMPTED_AFTER_NON_EXECUTED_PLAN",
                }
            delivery = deliver_adapter(
                normalized["document_id"],
                int(execution["revision_after"]),
                normalized["link_ttl_seconds"],
            )
            return _augment(
                delivery,
                {
                    **task_receipt,
                    "p418_execution": execution,
                    "p418_outcome": "EDIT_EXECUTED_VERIFIED_AND_DELIVERED",
                },
            )

        if kind == "INSPECT":
            result: dict[str, Any] = {
                **task_receipt,
                "ok": True,
                "document_id": normalized["document_id"],
                "views": {},
                "authority": "COMPOSED_READ_ONLY_PRODUCT_INSPECTION",
            }
            for view in normalized["views"]:
                if view == "SUMMARY":
                    result["views"]["SUMMARY"] = inspect_adapter(normalized["document_id"])
                elif view == "SEMANTIC_GRAPH":
                    result["views"]["SEMANTIC_GRAPH"] = semantic_graph_adapter(normalized["document_id"])
                elif view == "DOCUMENT_MAP":
                    result["views"]["DOCUMENT_MAP"] = document_map_adapter(normalized["document_id"])
            return result

        raise RuntimeError("unreachable P4.18 task kind")

    return {
        "phase": PHASE,
        "product": PRODUCT,
        "authority": "P418_TASK_ORIENTED_PRODUCT_FACADE",
    }
