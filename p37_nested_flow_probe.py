from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path

import httpx2
from pydantic import AnyUrl
from mcp import Client
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata

from test_client import HeadlessApprover, InMemoryTokenStorage, _payload

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
PASSPHRASE = os.environ.get("P11_OAUTH_PASSPHRASE", "")
FIXTURES = {
    "header": Path(os.environ.get("P37_HEADER_HWP", "/tmp/pic-in-head-01.hwp")),
    "footnote": Path(os.environ.get("P37_FOOTNOTE_HWP", "/tmp/footnote-01.hwp")),
    "endnote": Path(os.environ.get("P37_ENDNOTE_HWP", "/tmp/endnote-01.hwp")),
    "footer": Path(os.environ.get("P37_FOOTER_HWP", "/tmp/sub-superscript.hwp")),
    "object-text": Path(os.environ.get("P37_TEXTBOX_HWP", "/tmp/footnote-tbox-01.hwp")),
}


async def main() -> None:
    approver = HeadlessApprover(PASSPHRASE)
    oauth = OAuthClientProvider(
        server_url=URL,
        client_metadata=OAuthClientMetadata(
            client_name="P3.9 Nested HWP Flow Probe",
            redirect_uris=[AnyUrl("http://127.0.0.1:8765/callback")],
            scope="hwpx offline_access",
        ),
        storage=InMemoryTokenStorage(),
        redirect_handler=approver.redirect_handler,
        callback_handler=approver.callback_handler,
    )
    created: list[str] = []
    report: dict[str, dict] = {}
    async with httpx2.AsyncClient(auth=oauth, timeout=60.0) as http_client:
        transport = streamable_http_client(URL, http_client=http_client)
        async with Client(transport, mode="2026-07-28") as client:
            for expected_flow, path in FIXTURES.items():
                raw = path.read_bytes()
                encoded = base64.b64encode(raw).decode("ascii")
                flows = _payload(await client.call_tool("get_hwp5_text_flows", {
                    "content_base64": encoded,
                    "filename": path.name,
                }))
                if not flows or not flows.get("readable"):
                    raise RuntimeError(f"{expected_flow}: unreadable nested-flow fixture: {flows}")
                count = int((flows.get("flow_counts") or {}).get(expected_flow, 0))
                if count < 1:
                    raise RuntimeError(
                        f"{expected_flow}: expected nested flow was not recovered: {flows}"
                    )

                common = _payload(await client.call_tool("get_common_document_ir", {
                    "content_base64": encoded,
                    "filename": path.name,
                    "include_blocks": True,
                    "max_blocks": 1000,
                }))
                kinds = [item.get("kind") for item in (common or {}).get("blocks", [])]
                if expected_flow not in kinds:
                    raise RuntimeError(
                        f"{expected_flow}: Common IR omitted nested flow kind: {common}"
                    )

                rich = _payload(await client.call_tool("materialize_hwp5_rich_derivative", {
                    "content_base64": encoded,
                    "filename": path.name,
                    "request_id": f"p39-nested-{expected_flow}-v2",
                    "promote_tables": False,
                    "promote_equations": False,
                    "promote_pictures": False,
                }))
                if not rich or not rich.get("ok"):
                    raise RuntimeError(f"{expected_flow}: derivative failed: {rich}")
                created.append(rich["document_id"])
                nested_receipt = (rich.get("promotion_report") or {}).get(
                    "nested_text_flows", {}
                )
                if int(nested_receipt.get("recovered", 0)) < 1:
                    raise RuntimeError(
                        f"{expected_flow}: promotion receipt lost nested flow: {rich}"
                    )
                family_receipt = (nested_receipt.get("families") or {}).get(
                    expected_flow, {}
                )
                if expected_flow in {"header", "footer", "footnote", "endnote"}:
                    if family_receipt.get("status") != "PROMOTED_NATIVE":
                        raise RuntimeError(
                            f"{expected_flow}: native promotion did not close: {rich}"
                        )
                elif expected_flow == "object-text":
                    control_graph = _payload(await client.call_tool(
                        "get_hwp5_control_graph",
                        {
                            "content_base64": encoded,
                            "filename": path.name,
                        },
                    ))
                    object_control_indexes = {
                        int(item.get("control_index"))
                        for item in (flows.get("flows") or {}).get("object-text", [])
                        if item.get("control_index") is not None
                    }
                    rectangle_controls = [
                        item for item in (control_graph or {}).get("controls", [])
                        if item.get("control_index") is not None
                        and int(item.get("control_index")) in object_control_indexes
                        and item.get("shape_family") == "rectangle"
                    ]
                    if rectangle_controls:
                        if family_receipt.get("status") not in {"PROMOTED_NATIVE", "PARTIAL"}:
                            raise RuntimeError(
                                f"{expected_flow}: rectangle-certified textbox was not promoted: {rich}"
                            )
                        if int(family_receipt.get("promoted_controls", 0)) < 1:
                            raise RuntimeError(
                                f"{expected_flow}: no rectangle textbox promotion receipt: {rich}"
                            )
                    elif family_receipt.get("status") != "DEFERRED":
                        raise RuntimeError(
                            f"{expected_flow}: non-rectangle textbox promotion overstated: {rich}"
                        )

                oracle = _payload(await client.call_tool(
                    "compare_hwp5_roundtrip_fidelity",
                    {
                        "content_base64": encoded,
                        "document_id": rich["document_id"],
                        "filename": path.name,
                    },
                ))
                if not oracle or not oracle.get("provenance_match"):
                    raise RuntimeError(
                        f"{expected_flow}: source provenance mismatch: {oracle}"
                    )
                nested_oracle = (oracle.get("families") or {}).get(
                    "nested_text_flows", {}
                )
                if int(nested_oracle.get("source_count", 0)) < 1:
                    raise RuntimeError(
                        f"{expected_flow}: oracle omitted nested source flow: {oracle}"
                    )
                if nested_oracle.get("native_promotion") != "FAMILY_GRADED":
                    raise RuntimeError(
                        f"{expected_flow}: oracle lost family-graded promotion: {oracle}"
                    )
                oracle_family = (
                    (nested_oracle.get("promotion_receipt") or {}).get("families") or {}
                ).get(expected_flow, {})
                if expected_flow in {"header", "footer", "footnote", "endnote"}:
                    if oracle_family.get("status") != "PROMOTED_NATIVE":
                        raise RuntimeError(
                            f"{expected_flow}: oracle promotion receipt did not close: {oracle}"
                        )
                elif expected_flow == "object-text":
                    textbox_oracle = (oracle.get("families") or {}).get("textboxes", {})
                    if rectangle_controls:
                        if oracle_family.get("status") not in {"PROMOTED_NATIVE", "PARTIAL"}:
                            raise RuntimeError(
                                f"{expected_flow}: oracle lost native textbox promotion: {oracle}"
                            )
                        if not textbox_oracle.get("structural_geometry_exact"):
                            raise RuntimeError(
                                f"{expected_flow}: structural textbox geometry did not round-trip: {oracle}"
                            )
                    elif oracle_family.get("status") != "DEFERRED":
                        raise RuntimeError(
                            f"{expected_flow}: oracle overstated non-rectangle text-box promotion: {oracle}"
                        )

                report[expected_flow] = {
                    "source_bytes": len(raw),
                    "flow_counts": flows.get("flow_counts", {}),
                    "ir_kind_count": kinds.count(expected_flow),
                    "nested_promotion_receipt": nested_receipt,
                    "oracle": nested_oracle,
                }

            for document_id in created:
                deleted = _payload(await client.call_tool(
                    "delete_document", {"document_id": document_id}
                ))
                if not deleted or not deleted.get("deleted"):
                    raise RuntimeError(f"cleanup failed: {document_id}: {deleted}")

    print("P3.9 REAL_NESTED_HWP_FLOW_PASS")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
