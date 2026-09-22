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
            }
            missing = expected - set(names)
            if missing:
                raise RuntimeError(f"missing tools: {sorted(missing)}")
            for tool in tools.tools:
                schema_text = json.dumps(tool.input_schema, ensure_ascii=False).lower()
                if "access_token" in schema_text or "passphrase" in schema_text:
                    raise RuntimeError(f"secret-bearing field leaked into tool schema: {tool.name}")

            read_payload = _payload(await client.call_tool("probe_read", {"message": "P2 OAuth smoke test"}))
            if not read_payload or not read_payload.get("ok") or read_payload.get("version") != "0.9.0-p3.26":
                raise RuntimeError(f"probe_read did not expose P2: {read_payload}")

            p2_caps = _payload(await client.call_tool("p2_capabilities", {}))
            if not p2_caps or p2_caps.get("phase") != "P3.26":
                raise RuntimeError(f"p2_capabilities failed: {p2_caps}")

            if not RUN_WRITE_TEST:
                return

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
            ):
                deleted = _payload(await client.call_tool("delete_document", {"document_id": doc_id}))
                if not deleted or not deleted.get("deleted"):
                    raise RuntimeError(f"delete_document failed: {deleted}")
            print("P3.21 lifecycle and one-shot generation PASS", digest)


if __name__ == "__main__":
    asyncio.run(main())
