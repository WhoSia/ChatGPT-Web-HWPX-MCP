from __future__ import annotations

from typing import Any, Callable

from mcp.types import CallToolResult, ToolAnnotations

from p418_product import PHASE, PRODUCT, document_agent_contract, prepare_document_task


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
