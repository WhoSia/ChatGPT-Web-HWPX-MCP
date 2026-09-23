from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx2
from pydantic import AnyUrl
from hwpx import HwpxDocument

from mcp import Client
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
RUN_WRITE_TEST = os.environ.get(
    "RUN_P2_WRITE_TEST",
    os.environ.get("RUN_P12_WRITE_TEST", os.environ.get("RUN_P11_WRITE_TEST", "")),
) == "1"
P11_OAUTH_PASSPHRASE = os.environ.get("P11_OAUTH_PASSPHRASE", "")
MCP_CLIENT_MODE = os.environ.get("MCP_CLIENT_MODE", "auto")


class InMemoryTokenStorage:
    def __init__(self) -> None:
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


class HeadlessApprover:
    def __init__(self, passphrase: str) -> None:
        self.passphrase = passphrase
        self.result: AuthorizationCodeResult | None = None

    async def redirect_handler(self, authorization_url: str) -> None:
        if not self.passphrase:
            raise RuntimeError("P11_OAUTH_PASSPHRASE is required for OAuth lifecycle CI")
        async with httpx2.AsyncClient(follow_redirects=False, timeout=60.0) as browser:
            authorize = await browser.get(authorization_url)
            if authorize.status_code not in (302, 303, 307, 308):
                raise RuntimeError(f"authorize returned {authorize.status_code}: {authorize.text}")
            approval_url = urljoin(authorization_url, authorize.headers["location"])
            request_id = parse_qs(urlparse(approval_url).query).get("request", [""])[0]
            if not request_id:
                raise RuntimeError(f"approval redirect missing request id: {approval_url}")
            approved = await browser.post(
                approval_url,
                data={"request": request_id, "passphrase": self.passphrase, "decision": "approve"},
            )
            if approved.status_code not in (302, 303, 307, 308):
                raise RuntimeError(f"approval returned {approved.status_code}: {approved.text}")
            callback_url = urljoin(approval_url, approved.headers["location"])
            params = parse_qs(urlparse(callback_url).query)
            code = params.get("code", [""])[0]
            if not code:
                raise RuntimeError(f"callback missing authorization code: {callback_url}")
            self.result = AuthorizationCodeResult(
                code=code,
                state=params.get("state", [None])[0],
                iss=params.get("iss", [None])[0],
            )

    async def callback_handler(self) -> AuthorizationCodeResult:
        if self.result is None:
            raise RuntimeError("OAuth callback requested before authorization completed")
        return self.result


def _payload(result):
    if result.structured_content:
        return result.structured_content
    for block in result.content or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


async def main() -> None:
    approver = HeadlessApprover(P11_OAUTH_PASSPHRASE)
    oauth = OAuthClientProvider(
        server_url=URL,
        client_metadata=OAuthClientMetadata(
            client_name="ChatGPT Web HWPX MCP P3.2 CI",
            redirect_uris=[AnyUrl("http://127.0.0.1:8765/callback")],
            scope="hwpx offline_access",
        ),
        storage=InMemoryTokenStorage(),
        redirect_handler=approver.redirect_handler,
        callback_handler=approver.callback_handler,
    )

    async with httpx2.AsyncClient(auth=oauth, timeout=60.0) as http_client:
        transport = streamable_http_client(URL, http_client=http_client)
        async with Client(transport, mode=MCP_CLIENT_MODE) as client:
            print("protocol:", client.protocol_version)
            print("server:", client.server_info)
            tools = await client.list_tools()
            names = [tool.name for tool in tools.tools]
            print("tools:", names)
            expected = {
                "probe_read",
                "probe_capabilities",
                "create_document",
                "ingest_document",
                "inspect_document",
                "export_document",
                "delete_document",
                "acquire_document_lease",
                "release_document_lease",
                "get_document_commit_receipt",
                "get_document_versions",
                "restore_document_revision",
                "set_document_retention",
                "pin_document_revision",
                "unpin_document_revision",
                "compact_document_history",
                "verify_document_lineage",
                "get_document_map",
                "search_document_text",
                "get_document_slice",
                "plan_bulk_text_replace",
                "commit_bulk_text_replace",
                "inspect_hwp5_document",
                "materialize_hwp5_rich_derivative",
                "get_hwp5_control_graph",
                "compare_hwp5_roundtrip_fidelity",
                "get_hwp5_style_map",
                "get_paragraph_style_provenance",
                "get_textbox_map",
                "get_hwp5_text_flows",
                "materialize_hwp5_text_derivative",
                "get_common_document_ir",
                "extract_common_document",
                "search_common_document",
                "get_common_document_slice",
                "assess_hwp5_promotion",
                "get_text",
                "apply_edits",
                "compare_document",
                "p2_capabilities",
                "get_formatting",
                "apply_formatting",
                "get_inline_map",
                "apply_inline_edits",
                "apply_control_edits",
                "get_table_map",
                "apply_table_edits",
                "get_object_map",
                "apply_object_edits",
                "get_equation_map",
                "apply_equation_edits",
                "get_document_setup",
                "apply_document_setup",
                "get_structured_publishing",
                "apply_structured_publishing",
                "get_annotation_apparatus",
                "apply_annotation_apparatus",
                "get_document_plan_contract",
                "validate_document_plan",
                "create_document_from_plan",
                "get_review_workflow",
                "apply_review_workflow",
                "get_advanced_table_contract",
                "get_advanced_tables",
                "apply_advanced_table_edits",
                "get_story_layer_contract",
                "get_story_layer",
                "apply_story_layer",
                "get_drawing_layer_contract",
                "get_drawing_layer",
                "apply_drawing_layer",
                "get_drawing_style_contract",
                "get_drawing_styles",
                "apply_drawing_styles",
                "get_diagram_composition_contract",
                "get_diagram_composition",
                "apply_diagram_composition",
                "get_high_level_diagram_contract",
                "validate_high_level_diagram_plan",
                "get_high_level_diagrams",
                "apply_high_level_diagrams",
                "get_diagram_lifecycle_contract",
                "get_diagram_lifecycle",
                "apply_diagram_lifecycle",
                "get_diagram_design_system_contract",
                "get_diagram_design_system",
                "apply_diagram_design_system",
                "get_diagram_quality_assurance_contract",
                "get_diagram_quality",
                "validate_diagram_quality",
                "plan_diagram_repairs",
                "apply_diagram_repairs",
                "get_brownfield_diagram_contract",
                "recognize_existing_diagrams",
                "plan_diagram_adoption",
                "promote_diagram_candidate",
                "plan_legacy_diagram_refactor",
                "apply_legacy_diagram_refactor",
                "get_rare_feature_registry",
                "evaluate_rare_feature_lane",
                "plan_rare_feature_promotion",
                "get_product_ux_regression_contract",
            }
            missing = expected - set(names)
            if missing:
                raise RuntimeError(f"missing tools: {sorted(missing)}")
            for tool in tools.tools:
                schema_text = json.dumps(tool.input_schema, ensure_ascii=False).lower()
                if "access_token" in schema_text or "passphrase" in schema_text:
                    raise RuntimeError(f"secret-bearing field leaked into tool schema: {tool.name}")

            read_payload = _payload(await client.call_tool("probe_read", {"message": "P3.35 OAuth smoke test"}))
            if not read_payload or not read_payload.get("ok") or read_payload.get("version") != "0.13.0-p3.35":
                raise RuntimeError(f"probe_read did not expose current P3.35 product version: {read_payload}")

            p2_caps = _payload(await client.call_tool("p2_capabilities", {}))
            if not p2_caps or p2_caps.get("phase") != "P3.35":
                raise RuntimeError(f"p2_capabilities failed: {p2_caps}")

            rare_registry = _payload(await client.call_tool("get_rare_feature_registry", {}))
            assert rare_registry["authority"] == "EVIDENCE_GATED_REGISTRY_ONLY"
            assert rare_registry["features"]["smart_connectline"]["state"] == "BLOCKED_SEMANTIC_AMBIGUITY"
            assert rare_registry["features"]["tracked_change_resolution"]["state"] == "BOUNDED_PRODUCTION_AUTHORITY"
            assert rare_registry["features"]["tracked_change_resolution"]["authority"] == "UNPROTECTED_WHOLE_DOCUMENT_ACCEPT_REJECT_ALL"
            assert rare_registry["features"]["existing_group_ungroup"]["state"] == "BOUNDED_PRODUCTION_AUTHORITY"
            assert rare_registry["features"]["existing_group_ungroup"]["authority"] == "EXISTING_RECT_ELLIPSE_GROUP_UNGROUP_BOUNDED"
            ux_contract = _payload(await client.call_tool("get_product_ux_regression_contract", {}))
            assert ux_contract["policy"] == "PERIODIC_PRODUCT_UX_SMOKE"
            assert "every production phase before closure" in ux_contract["cadence"]

            if not RUN_WRITE_TEST:
                return

            delivery_contract = _payload(await client.call_tool("get_document_delivery_contract", {}))
            assert delivery_contract["evidence_gates"]["rare_features"]["status"] == "EVIDENCE_GATE_CLOSED"
            delivered = await client.call_tool("generate_document", {
                "plan": {"blocks": [{"type": "paragraph", "text": "P3.33 original"}]},
                "filename": "파일 전달 검증.hwpx", "request_id": "p333-oauth-delivery",
            })
            delivery = _payload(delivered)
            assert delivery["ok"] and delivery["revision"] == 1
            assert any(block.type == "resource_link" for block in delivered.content)
            delivery_id = delivery["document_id"]
            async with httpx2.AsyncClient(timeout=60) as download_client:
                original = await download_client.get(delivery["download_url"])
                original.raise_for_status()
                assert hashlib.sha256(original.content).hexdigest() == delivery["sha256"]
                assert "attachment" in original.headers["content-disposition"]
                mapped_delivery = _payload(await client.call_tool("get_document_map", {"document_id": delivery_id}))
                target = next(p["locator"] for p in mapped_delivery["paragraphs"] if p["text"] == "P3.33 original")
                edited_delivery = _payload(await client.call_tool("edit_document_and_deliver", {
                    "document_id": delivery_id, "expected_revision": 1,
                    "operations": [{"op": "replace_paragraph_text", "target": target, "text": "P3.33 edited"}],
                }))
                assert edited_delivery["ok"] and edited_delivery["revision"] == 2
                old_download = await download_client.get(delivery["download_url"])
                assert old_download.content == original.content
                edited_download = await download_client.get(edited_delivery["download_url"])
                edited_download.raise_for_status()
                assert hashlib.sha256(edited_download.content).hexdigest() == edited_delivery["sha256"]
                forged = await download_client.get(delivery["download_url"].replace("rev=1", "rev=2"))
                assert forged.status_code == 403
            delivered_ingest = _payload(await client.call_tool("ingest_document", {
                "filename": "delivery-reingest.hwpx", "content_base64": base64.b64encode(edited_download.content).decode(),
            }))
            assert delivered_ingest["admission"] == "PASS"
            renewed = _payload(await client.call_tool("deliver_document", {"document_id": delivery_id, "revision": 1}))
            assert renewed["sha256"] == delivery["sha256"]
            for delivered_id in (delivery_id, delivered_ingest["document_id"]):
                await client.call_tool("delete_document", {"document_id": delivered_id})
            print("P3.33 OAuth generate/edit/resource-link/download/exact-revision/re-ingest PASS")

            plan_checked = _payload(await client.call_tool("validate_document_plan", {
                "plan": {
                    "blocks": [
                        {"id": "h1", "type": "heading", "level": 1, "text": "P3.21 MCP transport"},
                        {"id": "p1", "type": "paragraph", "text": "one-shot authenticated creation"},
                        {"id": "t1", "type": "table", "rows": 2, "cols": 2, "cells": [["A", "B"], ["1", "2"]]},
                        {"id": "e1", "type": "equation", "latex": "x=1"},
                        {"id": "p2", "type": "paragraph", "text": "reference target verification"},
                    ],
                    "publishing": {"toc": True},
                    "post_operations": [{
                        "op": "add_page_crossref",
                        "paragraph": "$block:p2",
                        "target_paragraph": "$block:h1",
                        "cached_page": 1,
                    }],
                }
            }))
            if not plan_checked or not plan_checked.get("ok") or plan_checked.get("block_count") != 5:
                raise RuntimeError(f"P3.21 plan validation failed: {plan_checked}")

            planned = _payload(await client.call_tool("create_document_from_plan", {
                "plan": {
                    "document": {"title": "P3.21 Transport Smoke"},
                    "blocks": [
                        {"id": "h1", "type": "heading", "level": 1, "text": "P3.21 MCP transport"},
                        {"id": "p1", "type": "paragraph", "text": "one-shot authenticated creation"},
                        {"id": "t1", "type": "table", "rows": 2, "cols": 2, "cells": [["A", "B"], ["1", "2"]]},
                        {"id": "e1", "type": "equation", "latex": "x=1"},
                        {"id": "p2", "type": "paragraph", "text": "reference target verification"},
                    ],
                    "publishing": {"toc": True},
                    "post_operations": [{
                        "op": "add_page_crossref",
                        "paragraph": "$block:p2",
                        "target_paragraph": "$block:h1",
                        "cached_page": 1,
                    }],
                },
                "filename": "p321-one-shot.hwpx",
                "request_id": "p321-ci-one-shot-create",
            }))
            if (
                not planned
                or not planned.get("ok")
                or planned.get("revision") != 1
                or planned.get("composition", {}).get("block_count") != 5
                or not planned.get("composition", {}).get("atomic_commit")
            ):
                raise RuntimeError(f"P3.21 one-shot create failed: {planned}")
            planned_document_id = planned["document_id"]

            planned_map = _payload(await client.call_tool("get_document_map", {
                "document_id": planned_document_id,
            }))
            planned_body = next(
                (
                    p for p in planned_map.get("paragraphs", [])
                    if p.get("container") == "section-body"
                    and p.get("text") == "one-shot authenticated creation"
                ),
                None,
            )
            planned_ref = next(
                (
                    p for p in reversed(planned_map.get("paragraphs", []))
                    if p.get("container") == "section-body"
                    and str(p.get("text") or "").startswith("reference target verification")
                ),
                None,
            )
            if planned_body is None or planned_ref is None:
                raise RuntimeError(f"P3.22 review targets missing: {planned_map}")

            reviewed = _payload(await client.call_tool("apply_review_workflow", {
                "document_id": planned_document_id,
                "expected_revision": 1,
                "operations": [
                    {
                        "op": "tracked_replace",
                        "paragraph": planned_body["locator"],
                        "old": "authenticated",
                        "new": "reviewed",
                        "author": "CI Reviewer",
                    },
                    {
                        "op": "add_form_field",
                        "paragraph": planned_ref["locator"],
                        "name": "reviewer_name",
                        "prompt": "검토자",
                    },
                    {
                        "op": "add_check_box",
                        "paragraph": planned_ref["locator"],
                        "caption": "검토 완료",
                        "name": "review_done",
                        "checked": True,
                    },
                    {
                        "op": "add_highlight",
                        "paragraph": planned_body["locator"],
                        "match": "one-shot",
                        "color": "#FFFF00",
                    },
                    {
                        "op": "set_document_metadata",
                        "title": "P3.22 Transport Review Smoke",
                        "creator": "CI Reviewer",
                    },
                ],
            }))
            if (
                not reviewed
                or reviewed.get("revision_after") != 2
                or reviewed.get("transaction") != "COMMITTED"
            ):
                raise RuntimeError(f"P3.22 review workflow failed: {reviewed}")

            review_map = _payload(await client.call_tool("get_review_workflow", {
                "document_id": planned_document_id,
            }))
            review_counts = (review_map or {}).get("counts", {})
            if (
                not review_map
                or review_map.get("revision") != 2
                or review_counts.get("tracked_changes") != 2
                or review_counts.get("form_fields") != 1
                or review_counts.get("check_boxes") != 1
                or review_counts.get("highlights") != 1
                or not review_map.get("metadata")
                or review_map["metadata"].get("title") != "P3.22 Transport Review Smoke"
            ):
                raise RuntimeError(f"P3.22 review read-back failed: {review_map}")

            r2_created = _payload(await client.call_tool("create_document", {
                "title": "P3.34-R2 OAuth Resolution",
                "text": "r2 old value",
                "filename": "p334r2-resolution.hwpx",
                "request_id": "p334r2-oauth-resolution",
            }))
            if not r2_created or r2_created.get("revision") != 1:
                raise RuntimeError(f"P3.34-R2 fixture creation failed: {r2_created}")
            r2_document_id = r2_created["document_id"]
            r2_map = _payload(await client.call_tool("get_document_map", {
                "document_id": r2_document_id,
            }))
            r2_target = next(
                (p for p in r2_map.get("paragraphs", []) if p.get("text") == "r2 old value"),
                None,
            )
            if not r2_target:
                raise RuntimeError(f"P3.34-R2 paragraph target missing: {r2_map}")
            r2_tracked = _payload(await client.call_tool("apply_review_workflow", {
                "document_id": r2_document_id,
                "expected_revision": 1,
                "operations": [{
                    "op": "tracked_replace",
                    "paragraph": r2_target["locator"],
                    "old": "old",
                    "new": "new",
                    "author": "CI R2 Reviewer",
                }],
            }))
            if (
                not r2_tracked
                or r2_tracked.get("revision_after") != 2
                or r2_tracked.get("transaction") != "COMMITTED"
            ):
                raise RuntimeError(f"P3.34-R2 tracked fixture failed: {r2_tracked}")
            r2_resolved = _payload(await client.call_tool("apply_review_workflow", {
                "document_id": r2_document_id,
                "expected_revision": 2,
                "operations": [{"op": "accept_all_tracked_changes"}],
            }))
            r2_diff = (r2_resolved or {}).get("review_workflow_diff", {})
            if (
                not r2_resolved
                or r2_resolved.get("revision_after") != 3
                or r2_resolved.get("transaction") != "COMMITTED"
                or r2_diff.get("authority") != "UNPROTECTED_WHOLE_DOCUMENT_ACCEPT_REJECT_ALL"
                or r2_diff.get("after_counts", {}).get("tracked_changes") != 0
                or r2_diff.get("after_counts", {}).get("track_change_authors") != 0
            ):
                raise RuntimeError(f"P3.34-R2 bounded resolution failed: {r2_resolved}")
            r2_text = _payload(await client.call_tool("get_text", {
                "document_id": r2_document_id,
            }))
            if not r2_text or "r2 new value" not in r2_text.get("text", ""):
                raise RuntimeError(f"P3.34-R2 resolved text mismatch: {r2_text}")

            table_contract = _payload(await client.call_tool("get_advanced_table_contract", {}))
            if (
                not table_contract
                or table_contract.get("phase") != "P3.23"
                or table_contract.get("authority") != "STRUCTURAL_AUTHORITY_ONLY"
                or "insert_column_by_clone" not in table_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.23 table contract failed: {table_contract}")

            advanced_tables = _payload(await client.call_tool("get_advanced_tables", {
                "document_id": planned_document_id,
            }))
            if (
                not advanced_tables
                or advanced_tables.get("revision") != 2
                or advanced_tables.get("table_count") != 1
            ):
                raise RuntimeError(f"P3.23 advanced table map failed: {advanced_tables}")
            advanced_table = advanced_tables["tables"][0]
            target_cell = next(
                (
                    cell for cell in advanced_table.get("cells", [])
                    if cell.get("row") == 1 and cell.get("col") == 1
                ),
                None,
            )
            if target_cell is None:
                raise RuntimeError(f"P3.23 target cell missing: {advanced_table}")

            advanced_edited = _payload(await client.call_tool("apply_advanced_table_edits", {
                "document_id": planned_document_id,
                "expected_revision": 2,
                "operations": [
                    {
                        "op": "set_repeat_header",
                        "table": advanced_table["locator"],
                        "row": 0,
                        "enabled": True,
                    },
                    {
                        "op": "set_row_properties",
                        "table": advanced_table["locator"],
                        "row": 1,
                        "height": 2600,
                    },
                    {
                        "op": "set_cell_vertical_alignment",
                        "table": advanced_table["locator"],
                        "cell": target_cell["locator"],
                        "alignment": "BOTTOM",
                    },
                    {
                        "op": "set_table_page_break",
                        "table": advanced_table["locator"],
                        "mode": "TABLE",
                    },
                ],
            }))
            if (
                not advanced_edited
                or advanced_edited.get("revision_after") != 3
                or advanced_edited.get("transaction") != "COMMITTED"
                or advanced_edited.get("authority") != "STRUCTURAL_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.23 advanced table edit failed: {advanced_edited}")

            advanced_readback = _payload(await client.call_tool("get_advanced_tables", {
                "document_id": planned_document_id,
            }))
            if (
                not advanced_readback
                or advanced_readback.get("revision") != 3
                or advanced_readback.get("table_count") != 1
            ):
                raise RuntimeError(f"P3.23 advanced table read-back failed: {advanced_readback}")
            readback_table = advanced_readback["tables"][0]
            readback_cell = next(
                (
                    cell for cell in readback_table.get("cells", [])
                    if cell.get("row") == 1 and cell.get("col") == 1
                ),
                None,
            )
            if (
                not readback_table.get("repeat_header")
                or readback_table.get("page_break") != "TABLE"
                or not readback_table.get("row_geometry", [])[0].get("all_header")
                or readback_table.get("row_geometry", [])[1].get("heights") != [2600]
                or not readback_cell
                or readback_cell.get("vertical_alignment") != "BOTTOM"
            ):
                raise RuntimeError(f"P3.23 advanced table state mismatch: {advanced_readback}")

            story_contract = _payload(await client.call_tool("get_story_layer_contract", {}))
            if (
                not story_contract
                or story_contract.get("phase") != "P3.24"
                or story_contract.get("authority") != "STRUCTURAL_STORY_LAYER_AUTHORITY_ONLY"
                or story_contract.get("native_page_types") != ["BOTH", "EVEN", "ODD"]
                or "set_first_page_story" not in story_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.24 story-layer contract failed: {story_contract}")

            story_edited = _payload(await client.call_tool("apply_story_layer", {
                "document_id": planned_document_id,
                "expected_revision": 3,
                "operations": [
                    {
                        "op": "set_story_variant",
                        "section_index": 0,
                        "kind": "header",
                        "page_type": "ODD",
                        "text": "Odd CI Header",
                    },
                    {
                        "op": "set_story_variant",
                        "section_index": 0,
                        "kind": "header",
                        "page_type": "EVEN",
                        "text": "Even CI Header",
                    },
                    {
                        "op": "set_page_number_variant",
                        "section_index": 0,
                        "target": "footer",
                        "page_type": "ODD",
                        "prefix": "O-",
                    },
                    {
                        "op": "set_first_page_policy",
                        "section_index": 0,
                        "hide_header": True,
                        "hide_page_number": True,
                    },
                ],
            }))
            if (
                not story_edited
                or story_edited.get("revision_after") != 4
                or story_edited.get("transaction") != "COMMITTED"
                or story_edited.get("authority") != "STRUCTURAL_STORY_LAYER_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.24 story-layer edit failed: {story_edited}")

            story_readback = _payload(await client.call_tool("get_story_layer", {
                "document_id": planned_document_id,
            }))
            if (
                not story_readback
                or story_readback.get("revision") != 4
                or story_readback.get("section_count") != 1
            ):
                raise RuntimeError(f"P3.24 story-layer read-back failed: {story_readback}")
            first_story_section = story_readback["sections"][0]
            first_story_map = {
                (story.get("kind"), story.get("page_type")): story
                for story in first_story_section.get("stories", [])
            }
            if (
                first_story_section.get("first_page_policy") != {
                    "hide_header": True,
                    "hide_footer": False,
                    "hide_page_number": True,
                }
                or first_story_map.get(("header", "ODD"), {}).get("text") != "Odd CI Header"
                or first_story_map.get(("header", "EVEN"), {}).get("text") != "Even CI Header"
                or not all(
                    story.get("linkage_exact")
                    for story in first_story_section.get("stories", [])
                )
            ):
                raise RuntimeError(f"P3.24 story-layer state mismatch: {story_readback}")

            drawing_contract = _payload(await client.call_tool("get_drawing_layer_contract", {}))
            if (
                not drawing_contract
                or drawing_contract.get("phase") != "P3.25"
                or drawing_contract.get("authority") != "STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY"
                or "group_objects" not in drawing_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.25 drawing-layer contract failed: {drawing_contract}")

            drawing_edited = _payload(await client.call_tool("apply_drawing_layer", {
                "document_id": planned_document_id,
                "expected_revision": 4,
                "operations": [{
                    "op": "insert_textbox",
                    "anchor": planned_body["locator"],
                    "text": "P3.25 OAuth drawing",
                    "width": 9000,
                    "height": 4500,
                    "treat_as_char": False,
                    "horizontal_offset": 1200,
                    "vertical_offset": 900,
                    "z_order": 8,
                }],
            }))
            if (
                not drawing_edited
                or drawing_edited.get("revision_after") != 5
                or drawing_edited.get("transaction") != "COMMITTED"
                or drawing_edited.get("authority") != "STRUCTURAL_DRAWING_LAYER_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.25 drawing-layer edit failed: {drawing_edited}")

            drawing_readback = _payload(await client.call_tool("get_drawing_layer", {
                "document_id": planned_document_id,
            }))
            drawing_objects = (drawing_readback or {}).get("objects", [])
            drawing_box = next(
                (item for item in drawing_objects if item.get("text") == "P3.25 OAuth drawing"),
                None,
            )
            if (
                not drawing_readback
                or drawing_readback.get("revision") != 5
                or drawing_readback.get("drawing_count", 0) < 1
                or drawing_box is None
                or drawing_box.get("kind") != "rect"
                or drawing_box.get("z_order") != 8
                or drawing_box.get("position", {}).get("horzOffset") != "1200"
                or drawing_box.get("position", {}).get("vertOffset") != "900"
            ):
                raise RuntimeError(f"P3.25 drawing-layer read-back failed: {drawing_readback}")

            drawing_style_contract = _payload(await client.call_tool("get_drawing_style_contract", {}))
            if (
                not drawing_style_contract
                or drawing_style_contract.get("phase") != "P3.26"
                or drawing_style_contract.get("authority") != "STRUCTURAL_DRAWING_STYLE_AUTHORITY_ONLY"
                or "insert_curve" not in drawing_style_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.26 drawing-style contract failed: {drawing_style_contract}")

            drawing_styles_edited = _payload(await client.call_tool("apply_drawing_styles", {
                "document_id": planned_document_id,
                "expected_revision": 5,
                "operations": [
                    {
                        "op": "insert_line",
                        "anchor": planned_body["locator"],
                        "start_x": 0,
                        "start_y": 0,
                        "end_x": 9000,
                        "end_y": 3000,
                        "line_color": "#223344",
                        "line_width": 420,
                        "treat_as_char": False,
                    },
                    {
                        "op": "insert_ellipse",
                        "anchor": planned_body["locator"],
                        "width": 8000,
                        "height": 5000,
                        "line_color": "#335577",
                        "fill_color": "#DDEEFF",
                        "treat_as_char": False,
                    },
                ],
            }))
            if (
                not drawing_styles_edited
                or drawing_styles_edited.get("revision_after") != 6
                or drawing_styles_edited.get("transaction") != "COMMITTED"
                or drawing_styles_edited.get("authority") != "STRUCTURAL_DRAWING_STYLE_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.26 shape authoring failed: {drawing_styles_edited}")

            styles_readback = _payload(await client.call_tool("get_drawing_styles", {
                "document_id": planned_document_id,
            }))
            if (
                not styles_readback
                or styles_readback.get("revision") != 6
                or styles_readback.get("family_counts", {}).get("line", 0) < 1
                or styles_readback.get("family_counts", {}).get("ellipse", 0) < 1
            ):
                raise RuntimeError(f"P3.26 shape read-back failed: {styles_readback}")
            line_style = next(
                (item for item in styles_readback.get("styles", []) if item.get("kind") == "line"),
                None,
            )
            ellipse_style = next(
                (item for item in styles_readback.get("styles", []) if item.get("kind") == "ellipse"),
                None,
            )
            if (
                line_style is None
                or line_style.get("line_shape", {}).get("color") != "#223344"
                or ellipse_style is None
                or ellipse_style.get("fill", {}).get("faceColor") != "#DDEEFF"
            ):
                raise RuntimeError(f"P3.26 authored style mismatch: {styles_readback}")

            styled = _payload(await client.call_tool("apply_drawing_styles", {
                "document_id": planned_document_id,
                "expected_revision": 6,
                "operations": [
                    {
                        "op": "set_shape_stroke",
                        "drawing": line_style["locator"],
                        "color": "#446688",
                        "width": 480,
                        "style": "DASH",
                        "alpha": 30,
                    },
                    {
                        "op": "set_shape_arrowheads",
                        "drawing": line_style["locator"],
                        "head_style": "ARROW",
                        "tail_style": "FILLED_CIRCLE",
                    },
                    {
                        "op": "set_shape_shadow",
                        "drawing": ellipse_style["locator"],
                        "type": "DROP",
                        "color": "#777777",
                        "offset_x": 300,
                        "offset_y": 300,
                        "alpha": 70,
                    },
                ],
            }))
            if (
                not styled
                or styled.get("revision_after") != 7
                or styled.get("transaction") != "COMMITTED"
            ):
                raise RuntimeError(f"P3.26 style mutation failed: {styled}")

            styles_final = _payload(await client.call_tool("get_drawing_styles", {
                "document_id": planned_document_id,
            }))
            final_line = next(
                (item for item in styles_final.get("styles", []) if item.get("locator") == line_style["locator"]),
                None,
            )
            final_ellipse = next(
                (item for item in styles_final.get("styles", []) if item.get("locator") == ellipse_style["locator"]),
                None,
            )
            if (
                styles_final.get("revision") != 7
                or final_line is None
                or final_line.get("line_shape", {}).get("style") != "DASH"
                or final_line.get("line_shape", {}).get("headStyle") != "ARROW"
                or final_ellipse is None
                or final_ellipse.get("shadow", {}).get("type") != "DROP"
            ):
                raise RuntimeError(f"P3.26 final style read-back failed: {styles_final}")

            diagram_contract = _payload(await client.call_tool("get_diagram_composition_contract", {}))
            if (
                not diagram_contract
                or diagram_contract.get("phase") != "P3.27"
                or diagram_contract.get("authority") != "STRUCTURAL_DIAGRAM_COMPOSITION_AUTHORITY_ONLY"
                or "insert_smart_connector" not in diagram_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.27 diagram contract failed: {diagram_contract}")

            diagram_grouped = _payload(await client.call_tool("apply_diagram_composition", {
                "document_id": planned_document_id,
                "expected_revision": 7,
                "operations": [{
                    "op": "insert_diagram_block",
                    "preset": "three_stage",
                    "anchor": planned_body["locator"],
                    "horizontal_offset": 1800,
                    "vertical_offset": 1200,
                }],
            }))
            if (
                not diagram_grouped
                or diagram_grouped.get("revision_after") != 8
                or diagram_grouped.get("transaction") != "COMMITTED"
                or diagram_grouped.get("authority") != "STRUCTURAL_DIAGRAM_COMPOSITION_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.27 diagram block authoring failed: {diagram_grouped}")

            diagram_readback = _payload(await client.call_tool("get_diagram_composition", {
                "document_id": planned_document_id,
            }))
            if (
                not diagram_readback
                or diagram_readback.get("revision") != 8
                or diagram_readback.get("group_count", 0) < 1
            ):
                raise RuntimeError(f"P3.27 diagram read-back failed: {diagram_readback}")
            group = diagram_readback["groups"][-1]
            if (
                len(group.get("members", [])) != 3
                or group.get("position", {}).get("horzOffset") != "1800"
                or group.get("position", {}).get("vertOffset") != "1200"
            ):
                raise RuntimeError(f"P3.27 diagram group state mismatch: {group}")

            diagram_moved = _payload(await client.call_tool("apply_diagram_composition", {
                "document_id": planned_document_id,
                "expected_revision": 8,
                "operations": [{
                    "op": "translate_group",
                    "group": group["locator"],
                    "dx": 500,
                    "dy": 300,
                }],
            }))
            if (
                not diagram_moved
                or diagram_moved.get("revision_after") != 9
                or diagram_moved.get("transaction") != "COMMITTED"
            ):
                raise RuntimeError(f"P3.27 group translation failed: {diagram_moved}")

            diagram_final = _payload(await client.call_tool("get_diagram_composition", {
                "document_id": planned_document_id,
            }))
            moved_group = next(
                (item for item in diagram_final.get("groups", []) if item.get("locator") == group["locator"]),
                None,
            )
            if (
                diagram_final.get("revision") != 9
                or moved_group is None
                or moved_group.get("position", {}).get("horzOffset") != "2300"
                or moved_group.get("position", {}).get("vertOffset") != "1500"
            ):
                raise RuntimeError(f"P3.27 final group read-back failed: {diagram_final}")

            high_contract = _payload(await client.call_tool("get_high_level_diagram_contract", {}))
            if (
                not high_contract
                or high_contract.get("phase") != "P3.28"
                or high_contract.get("authority") != "STRUCTURAL_HIGH_LEVEL_DIAGRAM_AUTHORITY_ONLY"
                or "smart_connector_routing" not in high_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.28 high-level diagram contract failed: {high_contract}")

            plan_verdict = _payload(await client.call_tool("validate_high_level_diagram_plan", {
                "plan": {
                    "layout": "LEFT_TO_RIGHT",
                    "nodes": [
                        {"id": "start", "type": "terminator", "label": "Start"},
                        {"id": "work", "type": "process", "label": "Work"},
                        {"id": "end", "type": "terminator", "label": "End"},
                    ],
                    "edges": [
                        {"from": "start", "to": "work"},
                        {"from": "work", "to": "end"},
                    ],
                },
            }))
            if (
                not plan_verdict
                or plan_verdict.get("node_count") != 3
                or plan_verdict.get("edge_count") != 2
                or len(plan_verdict.get("plan_sha256", "")) != 64
            ):
                raise RuntimeError(f"P3.28 plan validation failed: {plan_verdict}")

            high_authored = _payload(await client.call_tool("apply_high_level_diagrams", {
                "document_id": planned_document_id,
                "expected_revision": 9,
                "operations": [{
                    "op": "insert_flowchart",
                    "anchor": planned_body["locator"],
                    "origin_x": 26000,
                    "origin_y": 1200,
                    "steps": [
                        {"id": "s", "label": "Start", "type": "terminator"},
                        {"id": "p", "label": "Process", "type": "process"},
                        {"id": "d", "label": "Check", "type": "decision"},
                        {"id": "e", "label": "End", "type": "terminator"},
                    ],
                }],
            }))
            if (
                not high_authored
                or high_authored.get("revision_after") != 10
                or high_authored.get("transaction") != "COMMITTED"
                or high_authored.get("authority") != "STRUCTURAL_HIGH_LEVEL_DIAGRAM_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.28 flowchart authoring failed: {high_authored}")

            high_readback = _payload(await client.call_tool("get_high_level_diagrams", {
                "document_id": planned_document_id,
            }))
            labels = {
                item.get("draw_text", {}).get("text")
                for item in high_readback.get("labeled_nodes", [])
            }
            if (
                not high_readback
                or high_readback.get("revision") != 10
                or high_readback.get("labeled_node_count", 0) < 4
                or not {"Start", "Process", "Check", "End"}.issubset(labels)
            ):
                raise RuntimeError(f"P3.28 flowchart read-back failed: {high_readback}")

            process_node = next(
                item for item in high_readback["labeled_nodes"]
                if item.get("draw_text", {}).get("text") == "Process"
            )
            high_relabeled = _payload(await client.call_tool("apply_high_level_diagrams", {
                "document_id": planned_document_id,
                "expected_revision": 10,
                "operations": [{
                    "op": "set_shape_text",
                    "drawing": process_node["locator"],
                    "text": "Execute",
                    "text_margin": 320,
                }],
            }))
            if (
                not high_relabeled
                or high_relabeled.get("revision_after") != 11
                or high_relabeled.get("transaction") != "COMMITTED"
            ):
                raise RuntimeError(f"P3.28 relabel failed: {high_relabeled}")

            high_final = _payload(await client.call_tool("get_high_level_diagrams", {
                "document_id": planned_document_id,
            }))
            final_labels = {
                item.get("draw_text", {}).get("text")
                for item in high_final.get("labeled_nodes", [])
            }
            if high_final.get("revision") != 11 or "Execute" not in final_labels:
                raise RuntimeError(f"P3.28 final label read-back failed: {high_final}")

            lifecycle_contract = _payload(await client.call_tool("get_diagram_lifecycle_contract", {}))
            if (
                not lifecycle_contract
                or lifecycle_contract.get("phase") != "P3.29"
                or lifecycle_contract.get("authority") != "STRUCTURAL_DIAGRAM_LIFECYCLE_AUTHORITY_ONLY"
                or "smart_connector_binding" not in lifecycle_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.29 lifecycle contract failed: {lifecycle_contract}")

            lifecycle_created = _payload(await client.call_tool("apply_diagram_lifecycle", {
                "document_id": planned_document_id,
                "expected_revision": 11,
                "operations": [{
                    "op": "instantiate_template",
                    "diagram_id": "oauth",
                    "template": "linear_process",
                    "anchor": planned_body["locator"],
                    "origin_y": 22000,
                }],
            }))
            if (
                not lifecycle_created
                or lifecycle_created.get("revision_after") != 12
                or lifecycle_created.get("transaction") != "COMMITTED"
                or lifecycle_created.get("authority") != "STRUCTURAL_DIAGRAM_LIFECYCLE_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.29 template creation failed: {lifecycle_created}")

            lifecycle_patched = _payload(await client.call_tool("apply_diagram_lifecycle", {
                "document_id": planned_document_id,
                "expected_revision": 12,
                "operations": [{
                    "op": "patch_node",
                    "diagram_id": "oauth",
                    "node_id": "work",
                    "label": "Review",
                    "x": 18000,
                    "width": 9000,
                }],
            }))
            if (
                not lifecycle_patched
                or lifecycle_patched.get("revision_after") != 13
                or lifecycle_patched.get("transaction") != "COMMITTED"
            ):
                raise RuntimeError(f"P3.29 node patch failed: {lifecycle_patched}")

            lifecycle_cloned = _payload(await client.call_tool("apply_diagram_lifecycle", {
                "document_id": planned_document_id,
                "expected_revision": 13,
                "operations": [{
                    "op": "clone_subgraph",
                    "diagram_id": "oauth",
                    "node_ids": ["start", "work"],
                    "new_prefix": "copy",
                    "dy": 9000,
                }],
            }))
            if (
                not lifecycle_cloned
                or lifecycle_cloned.get("revision_after") != 14
                or lifecycle_cloned.get("transaction") != "COMMITTED"
            ):
                raise RuntimeError(f"P3.29 subgraph clone failed: {lifecycle_cloned}")

            lifecycle_readback = _payload(await client.call_tool("get_diagram_lifecycle", {
                "document_id": planned_document_id,
            }))
            managed = next((d for d in lifecycle_readback.get("diagrams", []) if d.get("diagram_id") == "oauth"), None)
            if (
                not lifecycle_readback
                or lifecycle_readback.get("revision") != 14
                or managed is None
                or managed.get("node_count") != 5
                or managed.get("edge_count") != 3
                or next((n for n in managed.get("nodes", []) if n.get("node_id") == "work"), {}).get("label") != "Review"
                or "copy-start->copy-work" not in {e.get("edge_id") for e in managed.get("edges", [])}
            ):
                raise RuntimeError(f"P3.29 lifecycle read-back failed: {lifecycle_readback}")

            design_contract = _payload(await client.call_tool("get_diagram_design_system_contract", {}))
            if (
                not design_contract
                or design_contract.get("phase") != "P3.30"
                or design_contract.get("authority") != "STRUCTURAL_DIAGRAM_DESIGN_SYSTEM_AUTHORITY_ONLY"
                or "presentation" not in design_contract.get("themes", [])
                or "spacious" not in design_contract.get("layout_policies", [])
                or "rich_shape_text_typography" not in design_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.30 design-system contract failed: {design_contract}")

            design_applied = _payload(await client.call_tool("apply_diagram_design_system", {
                "document_id": planned_document_id,
                "expected_revision": 14,
                "operations": [{
                    "op": "apply_design_system",
                    "diagram_id": "oauth",
                    "theme": "presentation",
                    "layout_policy": "compact",
                    "layout": "LEFT_TO_RIGHT",
                }],
            }))
            if (
                not design_applied
                or design_applied.get("revision_after") != 15
                or design_applied.get("transaction") != "COMMITTED"
                or design_applied.get("authority") != "STRUCTURAL_DIAGRAM_DESIGN_SYSTEM_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.30 design-system apply failed: {design_applied}")

            design_readback = _payload(await client.call_tool("get_diagram_design_system", {
                "document_id": planned_document_id,
            }))
            designed = next(
                (d for d in design_readback.get("diagrams", []) if d.get("diagram_id") == "oauth"),
                None,
            )
            designed_work = None if designed is None else next(
                (n for n in designed.get("nodes", []) if n.get("node_id") == "work"),
                None,
            )
            designed_edge = None if designed is None else next(
                (e for e in designed.get("edges", []) if e.get("source") == "start" and e.get("target") == "work"),
                None,
            )
            if (
                not design_readback
                or design_readback.get("revision") != 15
                or designed is None
                or designed_work is None
                or designed_work.get("semantic_role") != "process"
                or designed_work.get("effective_style", {}).get("fill_color") != "#EAF2FF"
                or designed_edge is None
                or designed_edge.get("semantic_role") != "flow"
                or designed_edge.get("effective_style", {}).get("stroke_color") != "#425466"
                or not design_readback.get("semantic_style_sha256")
            ):
                raise RuntimeError(f"P3.30 design-system read-back failed: {design_readback}")

            qa_contract = _payload(await client.call_tool("get_diagram_quality_assurance_contract", {}))
            if (
                not qa_contract
                or qa_contract.get("phase") != "P3.31"
                or qa_contract.get("authority") != "STRUCTURAL_DIAGRAM_QUALITY_ASSURANCE_AUTHORITY_ONLY"
                or "flow" not in qa_contract.get("profiles", [])
                or "color_contrast_accessibility" not in qa_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.31 QA contract failed: {qa_contract}")

            qa_before = _payload(await client.call_tool("validate_diagram_quality", {
                "document_id": planned_document_id,
                "diagram_id": "oauth",
                "profile": "baseline",
                "constraints": {"require_weakly_connected": False},
                "expected_theme": "mono",
            }))
            qa_before_codes = {x.get("code") for x in qa_before.get("findings", [])}
            if (
                not qa_before
                or qa_before.get("revision") != 15
                or qa_before.get("passed")
                or "NATIVE_BBOX_OVERLAP" not in qa_before_codes
                or "NODE_THEME_MISMATCH" not in qa_before_codes
                or "EDGE_THEME_MISMATCH" not in qa_before_codes
            ):
                raise RuntimeError(f"P3.31 pre-repair validation failed: {qa_before}")

            qa_plan = _payload(await client.call_tool("plan_diagram_repairs", {
                "document_id": planned_document_id,
                "diagram_id": "oauth",
                "profile": "baseline",
                "constraints": {"require_weakly_connected": False},
                "expected_theme": "mono",
                "repair_theme": "mono",
                "repair_layout_policy": "standard",
                "layout": "LEFT_TO_RIGHT",
            }))
            if (
                not qa_plan
                or qa_plan.get("revision") != 15
                or qa_plan.get("operation_count") != 2
                or {op.get("op") for op in qa_plan.get("operations", [])} != {"apply_theme", "apply_layout_policy"}
                or not qa_plan.get("repair_plan_sha256")
            ):
                raise RuntimeError(f"P3.31 repair planning failed: {qa_plan}")

            qa_repaired = _payload(await client.call_tool("apply_diagram_repairs", {
                "document_id": planned_document_id,
                "expected_revision": 15,
                "repair_plan": {
                    "diagram_id": qa_plan["diagram_id"],
                    "source_qa_sha256": qa_plan["source_qa_sha256"],
                    "profile": qa_plan["profile"],
                    "constraints": qa_plan["constraints"],
                    "expected_theme": qa_plan["expected_theme"],
                    "operations": qa_plan["operations"],
                },
            }))
            if (
                not qa_repaired
                or qa_repaired.get("revision_after") != 16
                or qa_repaired.get("transaction") != "COMMITTED"
                or qa_repaired.get("authority") != "STRUCTURAL_DIAGRAM_QUALITY_ASSURANCE_AUTHORITY_ONLY"
                or qa_repaired.get("post_repair_report", {}).get("warning_count") != 0
                or not qa_repaired.get("post_repair_report", {}).get("passed")
            ):
                raise RuntimeError(f"P3.31 repair apply failed: {qa_repaired}")

            qa_after = _payload(await client.call_tool("validate_diagram_quality", {
                "document_id": planned_document_id,
                "diagram_id": "oauth",
                "profile": "baseline",
                "constraints": {"require_weakly_connected": False},
                "expected_theme": "mono",
            }))
            if (
                not qa_after
                or qa_after.get("revision") != 16
                or not qa_after.get("passed")
                or qa_after.get("warning_count") != 0
                or qa_after.get("error_count") != 0
                or not qa_after.get("qa_sha256")
            ):
                raise RuntimeError(f"P3.31 post-repair validation failed: {qa_after}")

            brownfield_contract = _payload(await client.call_tool("get_brownfield_diagram_contract", {}))
            if (
                not brownfield_contract
                or brownfield_contract.get("phase") != "P3.32"
                or brownfield_contract.get("authority") != "STRUCTURAL_BROWNFIELD_DIAGRAM_ADOPTION_AUTHORITY_ONLY"
                or "pixel_visual_recognition" not in brownfield_contract.get("deferred_operations", {})
                or "semantic_auto_repair" not in brownfield_contract.get("deferred_operations", {})
            ):
                raise RuntimeError(f"P3.32 brownfield contract failed: {brownfield_contract}")

            brownfield_scan = _payload(await client.call_tool("recognize_existing_diagrams", {
                "document_id": planned_document_id,
            }))
            legacy_candidate = next(
                (
                    item for item in brownfield_scan.get("candidates", [])
                    if {"Start", "Execute", "Check", "End"}.issubset(
                        {node.get("label") for node in item.get("nodes", [])}
                    )
                ),
                None,
            )
            if (
                not brownfield_scan
                or brownfield_scan.get("revision") != 16
                or legacy_candidate is None
                or not legacy_candidate.get("promotable")
                or legacy_candidate.get("node_count") != 4
                or legacy_candidate.get("edge_count") != 3
            ):
                raise RuntimeError(f"P3.32 brownfield recognition failed: {brownfield_scan}")

            binding_by_label = {
                "Start": {"node_id": "legacy-start", "node_type": "terminator"},
                "Execute": {"node_id": "legacy-work", "node_type": "process"},
                "Check": {"node_id": "legacy-check", "node_type": "decision"},
                "End": {"node_id": "legacy-end", "node_type": "terminator"},
            }
            adoption_bindings = {
                node["locator"]: binding_by_label[node["label"]]
                for node in legacy_candidate["nodes"]
            }
            adoption_plan = _payload(await client.call_tool("plan_diagram_adoption", {
                "document_id": planned_document_id,
                "candidate_id": legacy_candidate["candidate_id"],
                "diagram_id": "legacy-oauth",
                "node_bindings": adoption_bindings,
            }))
            if (
                not adoption_plan
                or adoption_plan.get("revision") != 16
                or not adoption_plan.get("adoption_plan_sha256")
                or adoption_plan.get("mutation_scope") != "HP_DRAWTEXT_NAME_ONLY"
            ):
                raise RuntimeError(f"P3.32 adoption planning failed: {adoption_plan}")

            promoted = _payload(await client.call_tool("promote_diagram_candidate", {
                "document_id": planned_document_id,
                "expected_revision": 16,
                "adoption_plan": {
                    "candidate_id": adoption_plan["candidate_id"],
                    "diagram_id": adoption_plan["diagram_id"],
                    "source_document_sha256": adoption_plan["source_document_sha256"],
                    "source_recognition_sha256": adoption_plan["source_recognition_sha256"],
                    "source_candidate_sha256": adoption_plan["source_candidate_sha256"],
                    "bindings": adoption_plan["bindings"],
                    "observed_relations": adoption_plan["observed_relations"],
                    "adoption_plan_sha256": adoption_plan["adoption_plan_sha256"],
                },
            }))
            promoted_diagram = next(
                (
                    item for item in promoted.get("diagram_lifecycle", {}).get("diagrams", [])
                    if item.get("diagram_id") == "legacy-oauth"
                ),
                None,
            )
            if (
                not promoted
                or promoted.get("revision_after") != 17
                or promoted.get("transaction") != "COMMITTED"
                or promoted.get("authority") != "STRUCTURAL_BROWNFIELD_DIAGRAM_ADOPTION_AUTHORITY_ONLY"
                or promoted_diagram is None
                or promoted_diagram.get("node_count") != 4
                or promoted_diagram.get("edge_count") != 3
                or not promoted.get("promotion", {}).get("source_object_identity_preserved")
            ):
                raise RuntimeError(f"P3.32 managed-graph promotion failed: {promoted}")

            legacy_refactor_plan = _payload(await client.call_tool("plan_legacy_diagram_refactor", {
                "document_id": planned_document_id,
                "diagram_id": "legacy-oauth",
                "layout_policy": "standard",
                "layout": "LEFT_TO_RIGHT",
                "theme": "classic",
            }))
            if (
                not legacy_refactor_plan
                or legacy_refactor_plan.get("revision") != 17
                or [op.get("op") for op in legacy_refactor_plan.get("operations", [])]
                    != ["apply_layout_policy", "apply_theme"]
                or not legacy_refactor_plan.get("refactor_plan_sha256")
            ):
                raise RuntimeError(f"P3.32 legacy refactor planning failed: {legacy_refactor_plan}")

            legacy_refactored = _payload(await client.call_tool("apply_legacy_diagram_refactor", {
                "document_id": planned_document_id,
                "expected_revision": 17,
                "refactor_plan": {
                    "diagram_id": legacy_refactor_plan["diagram_id"],
                    "source_identity_sha256": legacy_refactor_plan["source_identity_sha256"],
                    "source_relation_sha256": legacy_refactor_plan["source_relation_sha256"],
                    "operations": legacy_refactor_plan["operations"],
                    "refactor_plan_sha256": legacy_refactor_plan["refactor_plan_sha256"],
                },
            }))
            if (
                not legacy_refactored
                or legacy_refactored.get("revision_after") != 18
                or legacy_refactored.get("transaction") != "COMMITTED"
                or not legacy_refactored.get("legacy_refactor", {}).get("relation_preserved")
                or legacy_refactored.get("authority") != "STRUCTURAL_BROWNFIELD_DIAGRAM_ADOPTION_AUTHORITY_ONLY"
            ):
                raise RuntimeError(f"P3.32 legacy refactor apply failed: {legacy_refactored}")

            planned_export = _payload(await client.call_tool("export_document", {
                "document_id": planned_document_id,
                "link_ttl_seconds": 120,
            }))
            if not planned_export or not planned_export.get("download_url"):
                raise RuntimeError(f"P3.21 one-shot export failed: {planned_export}")
            async with httpx2.AsyncClient() as downloader:
                planned_download = await downloader.get(planned_export["download_url"])
            if planned_download.status_code != 200:
                raise RuntimeError(
                    f"P3.21 one-shot download failed: {planned_download.status_code} {planned_download.text}"
                )
            if (
                hashlib.sha256(planned_download.content).hexdigest() != planned_export["sha256"]
                or planned_download.content[:2] != b"PK"
            ):
                raise RuntimeError("P3.21 one-shot export receipt mismatch")

            planned_ingested = _payload(await client.call_tool("ingest_document", {
                "filename": "p321-reingested.hwpx",
                "content_base64": base64.b64encode(planned_download.content).decode("ascii"),
            }))
            if (
                not planned_ingested
                or planned_ingested.get("admission") != "PASS"
                or planned_ingested.get("revision") != 1
            ):
                raise RuntimeError(f"P3.21 one-shot re-ingest failed: {planned_ingested}")
            planned_inspected = _payload(await client.call_tool("inspect_document", {
                "document_id": planned_ingested["document_id"],
            }))
            if not planned_inspected or not planned_inspected.get("validation", {}).get("valid"):
                raise RuntimeError(f"P3.21 one-shot reopen verification failed: {planned_inspected}")

            reingested_lifecycle = _payload(await client.call_tool("get_diagram_lifecycle", {
                "document_id": planned_ingested["document_id"],
            }))
            reingested_managed = next(
                (d for d in reingested_lifecycle.get("diagrams", []) if d.get("diagram_id") == "oauth"),
                None,
            )
            if (
                not reingested_lifecycle
                or reingested_managed is None
                or reingested_managed.get("node_count") != 5
                or reingested_managed.get("edge_count") != 3
                or {n.get("node_id") for n in reingested_managed.get("nodes", [])}
                    != {"start", "work", "end", "copy-start", "copy-work"}
                or "copy-start->copy-work"
                    not in {e.get("edge_id") for e in reingested_managed.get("edges", [])}
            ):
                raise RuntimeError(f"P3.29 export/re-ingest identity persistence failed: {reingested_lifecycle}")

            reingested_design = _payload(await client.call_tool("get_diagram_design_system", {
                "document_id": planned_ingested["document_id"],
            }))
            reingested_designed = next(
                (d for d in reingested_design.get("diagrams", []) if d.get("diagram_id") == "oauth"),
                None,
            )
            reingested_work_style = None if reingested_designed is None else next(
                (n for n in reingested_designed.get("nodes", []) if n.get("node_id") == "work"),
                None,
            )
            if (
                not reingested_design
                or reingested_designed is None
                or reingested_work_style is None
                or reingested_work_style.get("effective_style", {}).get("fill_color") != "#FFFFFF"
                or not reingested_design.get("semantic_style_sha256")
            ):
                raise RuntimeError(f"P3.30 export/re-ingest style persistence failed: {reingested_design}")

            reingested_qa = _payload(await client.call_tool("validate_diagram_quality", {
                "document_id": planned_ingested["document_id"],
                "diagram_id": "oauth",
                "profile": "baseline",
                "constraints": {"require_weakly_connected": False},
                "expected_theme": "mono",
            }))
            if (
                not reingested_qa
                or not reingested_qa.get("passed")
                or reingested_qa.get("error_count") != 0
                or reingested_qa.get("warning_count") != 0
                or not reingested_qa.get("qa_sha256")
            ):
                raise RuntimeError(f"P3.31 export/re-ingest QA persistence failed: {reingested_qa}")

            reingested_brownfield = _payload(await client.call_tool("recognize_existing_diagrams", {
                "document_id": planned_ingested["document_id"],
            }))
            reingested_legacy = next(
                (
                    d for d in reingested_brownfield.get("managed_diagrams", [])
                    if d.get("diagram_id") == "legacy-oauth"
                ),
                None,
            )
            if (
                not reingested_brownfield
                or reingested_brownfield.get("revision") != 1
                or reingested_legacy is None
                or reingested_legacy.get("node_count") != 4
                or reingested_legacy.get("edge_count") != 3
                or not reingested_brownfield.get("recognition_sha256")
            ):
                raise RuntimeError(
                    f"P3.32 export/re-ingest managed promotion persistence failed: {reingested_brownfield}"
                )

            create_request_id = "p33-ci-idempotent-create"
            created = _payload(await client.call_tool("create_document", {
                "title": "P2 CI",
                "text": "alpha\nbeta",
                "filename": "p2-ci.hwpx",
                "request_id": create_request_id,
            }))
            if not created or not created.get("ok"):
                raise RuntimeError(f"create_document failed: {created}")
            document_id = created["document_id"]
            if created.get("revision") != 1:
                raise RuntimeError(f"new P2 document did not start at revision 1: {created}")

            replayed_create = _payload(await client.call_tool("create_document", {
                "title": "P2 CI",
                "text": "alpha\nbeta",
                "filename": "p2-ci.hwpx",
                "request_id": create_request_id,
            }))
            if (
                not replayed_create
                or replayed_create.get("document_id") != document_id
                or not replayed_create.get("idempotent_replay")
                or replayed_create.get("revision") != 1
            ):
                raise RuntimeError(f"idempotent create replay failed: {replayed_create}")

            mapped = _payload(await client.call_tool("get_document_map", {"document_id": document_id}))
            if not mapped or mapped.get("revision") != 1 or len(mapped.get("paragraphs", [])) < 3:
                raise RuntimeError(f"get_document_map failed: {mapped}")
            textbox_map = _payload(await client.call_tool(
                "get_textbox_map", {"document_id": document_id}
            ))
            if (
                not textbox_map
                or textbox_map.get("revision") != 1
                or textbox_map.get("textbox_count") != 0
                or not textbox_map.get("textbox_geometry_sha256")
            ):
                raise RuntimeError(f"P3.9 textbox map baseline failed: {textbox_map}")

            style_provenance = _payload(await client.call_tool(
                "get_paragraph_style_provenance",
                {"document_id": document_id, "max_paragraphs": 10},
            ))
            if (
                not style_provenance
                or style_provenance.get("source_format") != "hwpx"
                or style_provenance.get("returned_paragraphs", 0) < 1
                or style_provenance.get("authority") != "STYLE_REFERENCE_PROVENANCE_GRAPH"
            ):
                raise RuntimeError(f"P3.9 style provenance failed: {style_provenance}")

            common_ir = _payload(await client.call_tool("get_common_document_ir", {
                "document_id": document_id,
                "include_blocks": True,
                "max_blocks": 20,
            }))
            if (
                not common_ir
                or common_ir.get("source_format") != "hwpx"
                or common_ir.get("revision") != 1
                or common_ir.get("inventory", {}).get("paragraph", 0) < 1
                or not common_ir.get("ir_sha256")
            ):
                raise RuntimeError(f"P3.5 common IR failed: {common_ir}")

            common_search = _payload(await client.call_tool("search_common_document", {
                "document_id": document_id,
                "query": "beta",
                "kinds": ["paragraph"],
                "max_results": 10,
            }))
            if (
                not common_search
                or common_search.get("source_format") != "hwpx"
                or common_search.get("match_count", 0) < 1
                or not common_search.get("hits")
            ):
                raise RuntimeError(f"P3.5 cross-format search failed: {common_search}")

            common_slice = _payload(await client.call_tool("get_common_document_slice", {
                "document_id": document_id,
                "start_block": 0,
                "block_count": 2,
                "kinds": ["paragraph"],
            }))
            if (
                not common_slice
                or common_slice.get("source_format") != "hwpx"
                or common_slice.get("returned_blocks") != 2
            ):
                raise RuntimeError(f"P3.5 common IR slice failed: {common_slice}")

            searched = _payload(await client.call_tool("search_document_text", {
                "document_id": document_id,
                "query": "beta",
                "max_results": 10,
                "context_chars": 20,
            }))
            if (
                not searched
                or searched.get("revision") != 1
                or searched.get("match_count", 0) < 1
                or not searched.get("hits")
            ):
                raise RuntimeError(f"search_document_text failed: {searched}")

            sliced = _payload(await client.call_tool("get_document_slice", {
                "document_id": document_id,
                "start_paragraph": 0,
                "paragraph_count": 2,
                "include_locators": True,
            }))
            if (
                not sliced
                or sliced.get("revision") != 1
                or sliced.get("returned_paragraphs") != 2
                or len(sliced.get("paragraphs", [])) != 2
            ):
                raise RuntimeError(f"get_document_slice failed: {sliced}")

            target = mapped["paragraphs"][-1]
            locator = target["locator"]
            structure_before = mapped["structure_sha256"]
            semantic_before = mapped["semantic_sha256"]

            edited = _payload(await client.call_tool("apply_edits", {
                "document_id": document_id,
                "expected_revision": 1,
                "operations": [
                    {"op": "replace_paragraph_text", "target": locator, "text": "gamma"}
                ],
            }))
            if not edited or edited.get("transaction") != "COMMITTED" or edited.get("revision_after") != 2:
                raise RuntimeError(f"apply_edits failed: {edited}")
            diff = edited.get("semantic_diff", {})
            if diff.get("before", {}).get("semantic_sha256") != semantic_before:
                raise RuntimeError("semantic diff before-receipt mismatch")
            if diff.get("after", {}).get("structure_sha256") != structure_before:
                raise RuntimeError("text-only edit changed structural digest")

            formatting_before = _payload(await client.call_tool("get_formatting", {
                "document_id": document_id,
                "locator": locator,
            }))
            if not formatting_before or formatting_before.get("revision") != 2:
                raise RuntimeError(f"get_formatting before range edit failed: {formatting_before}")
            formatting_sha_before = formatting_before["formatting_sha256"]

            formatted = _payload(await client.call_tool("apply_formatting", {
                "document_id": document_id,
                "expected_revision": 2,
                "operations": [{
                    "op": "set_range_format",
                    "target": locator,
                    "start": 1,
                    "end": 3,
                    "format": {"bold": True},
                }],
            }))
            if (
                not formatted
                or formatted.get("transaction") != "COMMITTED"
                or formatted.get("revision_after") != 3
                or formatted.get("semantic_changed") is not False
                or formatted.get("structure_changed") is not False
                or formatted.get("formatting_changed") is not True
            ):
                raise RuntimeError(f"apply_formatting range edit failed: {formatted}")

            formatting_after = _payload(await client.call_tool("get_formatting", {
                "document_id": document_id,
                "locator": locator,
            }))
            if not formatting_after or formatting_after.get("revision") != 3:
                raise RuntimeError(f"get_formatting after range edit failed: {formatting_after}")
            if formatting_after.get("formatting_sha256") == formatting_sha_before:
                raise RuntimeError("range formatting did not change formatting digest")
            runs_after = [
                run for run in formatting_after.get("paragraph", {}).get("runs", [])
                if run.get("text")
            ]
            if [run.get("text") for run in runs_after] != ["g", "am", "ma"]:
                raise RuntimeError(f"range formatting did not split runs as expected: {runs_after}")
            if not runs_after[1].get("style", {}).get("bold"):
                raise RuntimeError(f"range formatting did not resolve bold middle run: {runs_after}")

            inline_before = _payload(await client.call_tool("get_inline_map", {
                "document_id": document_id,
                "locator": locator,
            }))
            if not inline_before or inline_before.get("revision") != 3:
                raise RuntimeError(f"get_inline_map before cross-run edit failed: {inline_before}")
            if inline_before.get("paragraph", {}).get("inline_text") != "gamma":
                raise RuntimeError(f"unexpected inline text before cross-run edit: {inline_before}")
            inline_structure_before = inline_before["inline_structure_sha256"]

            inline_edited = _payload(await client.call_tool("apply_inline_edits", {
                "document_id": document_id,
                "expected_revision": 3,
                "operations": [{
                    "op": "replace_inline_text",
                    "target": locator,
                    "start": 1,
                    "end": 4,
                    "text": "XYZ",
                    "expected_text": "amm",
                }],
            }))
            if (
                not inline_edited
                or inline_edited.get("transaction") != "COMMITTED"
                or inline_edited.get("revision_after") != 4
                or inline_edited.get("inline_text_changed") is not True
                or inline_edited.get("inline_structure_changed") is not False
                or inline_edited.get("structure_changed") is not False
            ):
                raise RuntimeError(f"apply_inline_edits cross-run edit failed: {inline_edited}")

            inline_after = _payload(await client.call_tool("get_inline_map", {
                "document_id": document_id,
                "locator": locator,
            }))
            if not inline_after or inline_after.get("revision") != 4:
                raise RuntimeError(f"get_inline_map after cross-run edit failed: {inline_after}")
            if inline_after.get("paragraph", {}).get("inline_text") != "gXYZa":
                raise RuntimeError(f"cross-run inline edit text mismatch: {inline_after}")
            if inline_after.get("inline_structure_sha256") != inline_structure_before:
                raise RuntimeError("cross-run inline edit changed inline structure receipt")

            special_inserted = _payload(await client.call_tool("apply_control_edits", {
                "document_id": document_id,
                "expected_revision": 4,
                "operations": [{
                    "op": "insert_special_atom",
                    "target": locator,
                    "offset": 2,
                    "kind": "lineBreak",
                }],
            }))
            if (
                not special_inserted
                or special_inserted.get("transaction") != "COMMITTED"
                or special_inserted.get("revision_after") != 5
                or special_inserted.get("inline_structure_changed") is not True
            ):
                raise RuntimeError(f"apply_control_edits insert special failed: {special_inserted}")

            inline_special = _payload(await client.call_tool("get_inline_map", {
                "document_id": document_id,
                "locator": locator,
            }))
            if inline_special.get("paragraph", {}).get("inline_text") != "gX\nYZa":
                raise RuntimeError(f"special atom insertion mismatch: {inline_special}")

            special_deleted = _payload(await client.call_tool("apply_control_edits", {
                "document_id": document_id,
                "expected_revision": 5,
                "operations": [{
                    "op": "delete_special_atom",
                    "target": locator,
                    "offset": 2,
                }],
            }))
            if (
                not special_deleted
                or special_deleted.get("transaction") != "COMMITTED"
                or special_deleted.get("revision_after") != 6
            ):
                raise RuntimeError(f"apply_control_edits delete special failed: {special_deleted}")

            partial_link = _payload(await client.call_tool("apply_control_edits", {
                "document_id": document_id,
                "expected_revision": 6,
                "operations": [{
                    "op": "create_hyperlink",
                    "target": locator,
                    "start": 1,
                    "end": 4,
                    "url": "https://example.com/p26",
                }],
            }))
            if (
                not partial_link
                or partial_link.get("transaction") != "COMMITTED"
                or partial_link.get("revision_after") != 7
                or partial_link.get("inline_structure_changed") is not True
            ):
                raise RuntimeError(f"P2.6 partial hyperlink create failed: {partial_link}")

            linked_map = _payload(await client.call_tool("get_inline_map", {
                "document_id": document_id,
                "locator": locator,
            }))
            fields = linked_map.get("paragraph", {}).get("fields", [])
            if len(fields) != 1 or fields[0].get("type") != "HYPERLINK":
                raise RuntimeError(f"P2.6 partial hyperlink field missing: {linked_map}")
            p = linked_map["paragraph"]
            if p["inline_text"][fields[0]["start"]:fields[0]["end"]] != "XYZ":
                raise RuntimeError(f"P2.6 partial hyperlink span mismatch: {linked_map}")

            unlinked = _payload(await client.call_tool("apply_control_edits", {
                "document_id": document_id,
                "expected_revision": 7,
                "operations": [{
                    "op": "remove_hyperlink",
                    "target": locator,
                    "field_index": 0,
                }],
            }))
            if not unlinked or unlinked.get("revision_after") != 8:
                raise RuntimeError(f"P2.6 hyperlink remove failed: {unlinked}")

            targeted = _payload(await client.call_tool("get_text", {"document_id": document_id, "locator": locator}))
            if not targeted or targeted.get("revision") != 8 or targeted.get("text") != "gXYZa":
                raise RuntimeError(f"targeted get_text failed: {targeted}")

            compared = _payload(await client.call_tool("compare_document", {
                "document_id": document_id,
                "semantic_sha256": semantic_before,
                "structure_sha256": structure_before,
                "inline_structure_sha256": inline_structure_before,
            }))
            if not compared or compared.get("matches", {}).get("semantic") is not False:
                raise RuntimeError(f"compare_document semantic verdict failed: {compared}")
            if compared.get("matches", {}).get("structure") is not True:
                raise RuntimeError(f"compare_document structure verdict failed: {compared}")
            if compared.get("matches", {}).get("inline_structure") is not True:
                raise RuntimeError(f"compare_document inline-structure verdict failed: {compared}")

            table_doc = HwpxDocument.new()
            table = table_doc.add_table(rows=2, cols=2)
            table.set_cell_text(0, 0, "A")
            table.set_cell_text(0, 1, "B")
            table.set_cell_text(1, 0, "C")
            table.set_cell_text(1, 1, "D")
            table_bytes = table_doc.to_bytes()
            table_doc.close()

            ingested_table = _payload(await client.call_tool("ingest_document", {
                "filename": "p27-table.hwpx",
                "content_base64": base64.b64encode(table_bytes).decode("ascii"),
            }))
            if not ingested_table or ingested_table.get("admission") != "PASS":
                raise RuntimeError(f"P2.7 table ingest failed: {ingested_table}")
            table_document_id = ingested_table["document_id"]

            table_map = _payload(await client.call_tool("get_table_map", {
                "document_id": table_document_id,
            }))
            if not table_map or table_map.get("table_count") != 1:
                raise RuntimeError(f"P2.7 get_table_map failed: {table_map}")
            table_info = table_map["tables"][0]
            first_cell = next(
                cell for cell in table_info["cells"]
                if cell["row"] == 0 and cell["col"] == 0
            )

            table_edit = _payload(await client.call_tool("apply_table_edits", {
                "document_id": table_document_id,
                "expected_revision": 1,
                "operations": [{
                    "op": "set_cell_text",
                    "table": table_info["locator"],
                    "cell": first_cell["locator"],
                    "text": "AA",
                }],
            }))
            if (
                not table_edit
                or table_edit.get("transaction") != "COMMITTED"
                or table_edit.get("revision_after") != 2
            ):
                raise RuntimeError(f"P2.7 apply_table_edits failed: {table_edit}")

            table_map_after = _payload(await client.call_tool("get_table_map", {
                "document_id": table_document_id,
            }))
            first_after = next(
                cell for cell in table_map_after["tables"][0]["cells"]
                if cell["row"] == 0 and cell["col"] == 0
            )
            if first_after.get("text") != "AA":
                raise RuntimeError(f"P2.7 table cell text mismatch: {table_map_after}")

            created_table = _payload(await client.call_tool("apply_table_edits", {
                "document_id": document_id,
                "expected_revision": 8,
                "operations": [{
                    "op": "create_table",
                    "rows": 2,
                    "cols": 2,
                    "cells": [["H1", "H2"], ["V1", "V2"]],
                }],
            }))
            if (
                not created_table
                or created_table.get("transaction") != "COMMITTED"
                or created_table.get("revision_after") != 9
                or created_table.get("table_structure_changed") is not True
            ):
                raise RuntimeError(f"P2.8 create_table failed: {created_table}")

            created_map = _payload(await client.call_tool("get_table_map", {
                "document_id": document_id,
            }))
            if not created_map or created_map.get("table_count") != 1:
                raise RuntimeError(f"P2.8 get_table_map after create failed: {created_map}")
            created_locator = created_map["tables"][0]["locator"]

            deleted_table = _payload(await client.call_tool("apply_table_edits", {
                "document_id": document_id,
                "expected_revision": 9,
                "operations": [{
                    "op": "delete_table",
                    "table": created_locator,
                }],
            }))
            if (
                not deleted_table
                or deleted_table.get("transaction") != "COMMITTED"
                or deleted_table.get("revision_after") != 10
            ):
                raise RuntimeError(f"P2.8 delete_table failed: {deleted_table}")

            final_table_map = _payload(await client.call_tool("get_table_map", {
                "document_id": document_id,
            }))
            if final_table_map.get("table_count") != 0:
                raise RuntimeError(f"P2.8 table lifecycle did not close: {final_table_map}")

            png_bytes = (
                b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
                + (1).to_bytes(4, "big") + (1).to_bytes(4, "big")
                + b"\x00" * 32
            )
            inserted_picture = _payload(await client.call_tool("apply_object_edits", {
                "document_id": document_id,
                "expected_revision": 10,
                "operations": [{
                    "op": "insert_picture",
                    "paragraph": locator,
                    "content_base64": base64.b64encode(png_bytes).decode("ascii"),
                    "image_format": "png",
                    "width": 7200,
                    "height": 3600,
                    "placement": "inline",
                }],
            }))
            if (
                not inserted_picture
                or inserted_picture.get("transaction") != "COMMITTED"
                or inserted_picture.get("revision_after") != 11
                or inserted_picture.get("media_custody_changed") is not True
            ):
                raise RuntimeError(f"P2.9 insert_picture failed: {inserted_picture}")

            object_map = _payload(await client.call_tool("get_object_map", {
                "document_id": document_id,
            }))
            if (
                not object_map
                or object_map.get("picture_count") != 1
                or object_map.get("media_item_count") != 1
            ):
                raise RuntimeError(f"P2.9 get_object_map failed: {object_map}")
            picture_locator = object_map["pictures"][0]["locator"]

            removed_picture = _payload(await client.call_tool("apply_object_edits", {
                "document_id": document_id,
                "expected_revision": 11,
                "operations": [{
                    "op": "remove_picture",
                    "picture": picture_locator,
                    "remove_orphaned": True,
                }],
            }))
            if (
                not removed_picture
                or removed_picture.get("transaction") != "COMMITTED"
                or removed_picture.get("revision_after") != 12
            ):
                raise RuntimeError(f"P2.9 remove_picture failed: {removed_picture}")
            object_map_after = _payload(await client.call_tool("get_object_map", {
                "document_id": document_id,
            }))
            if object_map_after.get("picture_count") != 0 or object_map_after.get("media_item_count") != 0:
                raise RuntimeError(f"P2.9 picture/media lifecycle did not close: {object_map_after}")

            inserted_equation = _payload(await client.call_tool("apply_equation_edits", {
                "document_id": document_id,
                "expected_revision": 12,
                "operations": [{
                    "op": "insert_equation",
                    "paragraph": locator,
                    "latex": "\\frac{a}{b}",
                }],
            }))
            if (
                not inserted_equation
                or inserted_equation.get("transaction") != "COMMITTED"
                or inserted_equation.get("revision_after") != 13
                or inserted_equation.get("equation_script_custody_changed") is not True
            ):
                raise RuntimeError(f"P2.10 insert_equation failed: {inserted_equation}")

            equation_map = _payload(await client.call_tool("get_equation_map", {
                "document_id": document_id,
            }))
            if not equation_map or equation_map.get("equation_count") != 1:
                raise RuntimeError(f"P2.10 get_equation_map failed: {equation_map}")
            equation_locator = equation_map["equations"][0]["locator"]

            removed_equation = _payload(await client.call_tool("apply_equation_edits", {
                "document_id": document_id,
                "expected_revision": 13,
                "operations": [{
                    "op": "remove_equation",
                    "equation": equation_locator,
                }],
            }))
            if (
                not removed_equation
                or removed_equation.get("transaction") != "COMMITTED"
                or removed_equation.get("revision_after") != 14
            ):
                raise RuntimeError(f"P2.10 remove_equation failed: {removed_equation}")

            equation_map_after = _payload(await client.call_tool("get_equation_map", {
                "document_id": document_id,
            }))
            if equation_map_after.get("equation_count") != 0:
                raise RuntimeError(f"P2.10 equation lifecycle did not close: {equation_map_after}")

            # Simulate a Render restart/local-cache loss without deleting durable custody.
            object_dir = Path(os.environ.get("P1_OBJECT_DIR", "/tmp/chatgpt-web-hwpx-mcp-p1"))
            for suffix in (".hwpx", ".json"):
                try:
                    (object_dir / f"{document_id}{suffix}").unlink()
                except FileNotFoundError:
                    pass

            recovered_inspect = _payload(await client.call_tool("inspect_document", {
                "document_id": document_id,
            }))
            if (
                not recovered_inspect
                or recovered_inspect.get("revision") != 14
                or recovered_inspect.get("storage") != "postgres-encrypted-versioned"
            ):
                raise RuntimeError(f"P3.0 restart rehydration failed: {recovered_inspect}")

            versions = _payload(await client.call_tool("get_document_versions", {
                "document_id": document_id,
            }))
            if (
                not versions
                or versions.get("version_count", 0) < 14
                or versions.get("versions", [])[-1].get("revision") != 14
            ):
                raise RuntimeError(f"P3.0 durable version history failed: {versions}")

            lease = _payload(await client.call_tool("acquire_document_lease", {
                "document_id": document_id,
                "expected_revision": 14,
                "ttl_seconds": 30,
                "holder_id": "ci-worker-a",
            }))
            if not lease or not lease.get("lease_token"):
                raise RuntimeError(f"P3.2 lease acquisition failed: {lease}")

            restored = _payload(await client.call_tool("restore_document_revision", {
                "document_id": document_id,
                "revision": 1,
                "expected_revision": 14,
                "lease_token": lease["lease_token"],
            }))
            if (
                not restored
                or restored.get("transaction") != "RECOVERED_AS_NEW_REVISION"
                or restored.get("revision_after") != 15
                or restored.get("recovered_from_revision") != 1
            ):
                raise RuntimeError(f"P3.2 historical recovery under lease failed: {restored}")

            commit_receipt = _payload(await client.call_tool("get_document_commit_receipt", {
                "document_id": document_id,
                "revision": 15,
            }))
            if (
                not commit_receipt
                or commit_receipt.get("expected_revision") != 14
                or len(commit_receipt.get("receipt_id", "")) != 64
                or commit_receipt.get("sha256") != restored.get("sha256")
            ):
                raise RuntimeError(f"P3.2 commit receipt failed: {commit_receipt}")

            release_after_commit = _payload(await client.call_tool("release_document_lease", {
                "document_id": document_id,
                "lease_token": lease["lease_token"],
            }))
            if not release_after_commit or release_after_commit.get("released") is not False:
                raise RuntimeError(f"P3.2 commit should auto-release lease: {release_after_commit}")

            release_lease = _payload(await client.call_tool("acquire_document_lease", {
                "document_id": document_id,
                "expected_revision": 15,
                "ttl_seconds": 30,
                "holder_id": "ci-worker-release",
            }))
            released = _payload(await client.call_tool("release_document_lease", {
                "document_id": document_id,
                "lease_token": release_lease["lease_token"],
            }))
            if not released or released.get("released") is not True:
                raise RuntimeError(f"P3.2 explicit lease release failed: {released}")

            pinned_revision = _payload(await client.call_tool("pin_document_revision", {
                "document_id": document_id,
                "revision": 1,
                "reason": "ci-restore-anchor",
            }))
            if not pinned_revision or pinned_revision.get("revision") != 1:
                raise RuntimeError(f"P3.2 revision pin failed: {pinned_revision}")

            maintenance_lease = _payload(await client.call_tool("acquire_document_lease", {
                "document_id": document_id,
                "expected_revision": 15,
                "ttl_seconds": 30,
                "holder_id": "ci-p32-maintenance-race",
            }))
            blocked_compaction = None
            try:
                blocked_compaction = await client.call_tool("compact_document_history", {
                    "document_id": document_id,
                    "expected_revision": 15,
                    "keep_last": 2,
                    "dry_run": False,
                })
            except Exception:
                blocked_compaction = "blocked"
            if blocked_compaction != "blocked":
                payload = _payload(blocked_compaction)
                if payload and payload.get("ok"):
                    raise RuntimeError(f"P3.2 active lease failed to block compaction: {payload}")
            await client.call_tool("release_document_lease", {
                "document_id": document_id,
                "lease_token": maintenance_lease["lease_token"],
            })

            preview_compaction = _payload(await client.call_tool("compact_document_history", {
                "document_id": document_id,
                "expected_revision": 15,
                "keep_last": 2,
                "dry_run": True,
            }))
            if not preview_compaction or 1 in preview_compaction.get("prunable_revisions", []):
                raise RuntimeError(f"P3.2 dry-run endangered pinned revision: {preview_compaction}")

            compacted = _payload(await client.call_tool("compact_document_history", {
                "document_id": document_id,
                "expected_revision": 15,
                "keep_last": 2,
                "dry_run": False,
            }))
            if (
                not compacted
                or not compacted.get("audit_chain_valid")
                or not compacted.get("restore_reachability_valid")
                or 1 in compacted.get("deleted_revisions", [])
            ):
                raise RuntimeError(f"P3.2 compaction failed: {compacted}")

            lineage = _payload(await client.call_tool("verify_document_lineage", {
                "document_id": document_id,
            }))
            if (
                not lineage
                or not lineage.get("audit_chain_valid")
                or not lineage.get("restore_reachability_valid")
                or lineage.get("commit_count") != 15
                or 1 not in lineage.get("pinned_revisions", [])
            ):
                raise RuntimeError(f"P3.2 lineage verification failed: {lineage}")

            restored_text = _payload(await client.call_tool("get_text", {
                "document_id": document_id,
            }))
            if not restored_text or restored_text.get("revision") != 15:
                raise RuntimeError(f"P3.0 recovered document read failed: {restored_text}")

            retention = _payload(await client.call_tool("set_document_retention", {
                "document_id": document_id,
                "retention_seconds": 604800,
            }))
            if (
                not retention
                or retention.get("revision") != 15
                or retention.get("retention_seconds") != 604800
            ):
                raise RuntimeError(f"P3.0 retention update failed: {retention}")

            exported = _payload(await client.call_tool("export_document", {"document_id": document_id, "link_ttl_seconds": 120}))
            if not exported or not exported.get("download_url"):
                raise RuntimeError(f"export_document failed: {exported}")
            async with httpx2.AsyncClient() as downloader:
                download = await downloader.get(exported["download_url"])
            if download.status_code != 200:
                raise RuntimeError(f"download failed: {download.status_code} {download.text}")
            digest = hashlib.sha256(download.content).hexdigest()
            if digest != exported["sha256"] or download.content[:2] != b"PK":
                raise RuntimeError("edited artifact receipt mismatch")

            ingested = _payload(await client.call_tool("ingest_document", {
                "filename": "p2-existing.hwpx",
                "content_base64": base64.b64encode(download.content).decode("ascii"),
            }))
            if not ingested or ingested.get("admission") != "PASS" or ingested.get("revision") != 1:
                raise RuntimeError(f"ingest_document failed: {ingested}")
            inspected = _payload(await client.call_tool("inspect_document", {"document_id": ingested["document_id"]}))
            if not inspected or not inspected.get("validation", {}).get("valid"):
                raise RuntimeError(f"inspect ingested document failed: {inspected}")

            bulk_created = _payload(await client.call_tool("create_document", {
                "title": "P3.4 Bulk Text",
                "text": "red one\nblue red two\nred red three",
                "filename": "p34-bulk.hwpx",
                "request_id": "p34-ci-bulk-document",
            }))
            if not bulk_created or bulk_created.get("revision") != 1:
                raise RuntimeError(f"P3.4 bulk fixture create failed: {bulk_created}")
            bulk_document_id = bulk_created["document_id"]

            bulk_plan = _payload(await client.call_tool("plan_bulk_text_replace", {
                "document_id": bulk_document_id,
                "query": "red",
                "replacement": "GREEN",
                "case_sensitive": False,
                "max_operations": 10,
                "selected_hit_indexes": [0, 2],
            }))
            if (
                not bulk_plan
                or bulk_plan.get("revision") != 1
                or bulk_plan.get("selected_hit_count") != 2
                or not bulk_plan.get("plan_id")
                or bulk_plan.get("preview", {}).get("structure_changed")
                or bulk_plan.get("preview", {}).get("inline_structure_changed")
            ):
                raise RuntimeError(f"P3.4 bulk preview failed: {bulk_plan}")

            bulk_commit = _payload(await client.call_tool("commit_bulk_text_replace", {
                "document_id": bulk_document_id,
                "expected_revision": 1,
                "plan_id": bulk_plan["plan_id"],
                "query": "red",
                "replacement": "GREEN",
                "case_sensitive": False,
                "max_operations": 10,
                "selected_hit_indexes": [0, 2],
            }))
            if (
                not bulk_commit
                or bulk_commit.get("transaction") != "COMMITTED"
                or bulk_commit.get("revision_after") != 2
                or bulk_commit.get("operation_count") != 2
                or bulk_commit.get("changed_paragraph_count") < 1
            ):
                raise RuntimeError(f"P3.4 bulk commit failed: {bulk_commit}")

            bulk_text = _payload(await client.call_tool("get_text", {
                "document_id": bulk_document_id,
            }))
            if (
                not bulk_text
                or bulk_text.get("revision") != 2
                or bulk_text.get("text", "").count("GREEN") != 2
                or bulk_text.get("text", "").count("red") != 2
            ):
                raise RuntimeError(f"P3.4 bounded post-edit verification failed: {bulk_text}")

            for doc_id in (
                document_id,
                ingested["document_id"],
                table_document_id,
                bulk_document_id,
                planned_document_id,
                planned_ingested["document_id"],
                r2_document_id,
            ):
                deleted = _payload(await client.call_tool("delete_document", {"document_id": doc_id}))
                if not deleted or not deleted.get("deleted"):
                    raise RuntimeError(f"delete_document failed: {deleted}")
            print("P3.21 lifecycle and one-shot generation PASS", digest)


if __name__ == "__main__":
    asyncio.run(main())
