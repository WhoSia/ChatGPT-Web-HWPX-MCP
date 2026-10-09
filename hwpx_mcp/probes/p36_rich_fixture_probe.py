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
    "table": Path(os.environ.get("P36_TABLE_HWP", "/tmp/table-001.hwp")),
    "equation": Path(os.environ.get("P36_EQUATION_HWP", "/tmp/eq-01.hwp")),
    "picture": Path(os.environ.get("P36_PICTURE_HWP", "/tmp/test-image.hwp")),
}


async def main() -> None:
    approver = HeadlessApprover(PASSPHRASE)
    oauth = OAuthClientProvider(
        server_url=URL,
        client_metadata=OAuthClientMetadata(
            client_name="P3.7 Rich HWP Fixture Probe",
            redirect_uris=[AnyUrl("http://127.0.0.1:8765/callback")],
            scope="hwpx offline_access",
        ),
        storage=InMemoryTokenStorage(),
        redirect_handler=approver.redirect_handler,
        callback_handler=approver.callback_handler,
    )
    created: list[str] = []
    reports: dict[str, dict] = {}
    async with httpx2.AsyncClient(auth=oauth, timeout=60.0) as http_client:
        transport = streamable_http_client(URL, http_client=http_client)
        async with Client(transport, mode="2026-07-28") as client:
            for family, path in FIXTURES.items():
                raw = path.read_bytes()
                encoded = base64.b64encode(raw).decode("ascii")
                graph = _payload(await client.call_tool("get_hwp5_control_graph", {
                    "content_base64": encoded,
                    "filename": path.name,
                }))
                assessment = _payload(await client.call_tool("assess_hwp5_promotion", {
                    "content_base64": encoded,
                    "filename": path.name,
                }))
                if not graph or not graph.get("readable"):
                    raise RuntimeError(f"{family}: control graph unreadable: {graph}")
                closure = assessment.get("closure", {}) if assessment else {}
                if family == "picture":
                    print("P3.7 picture-link diagnostics:", json.dumps([
                        {
                            "record_index": item.get("record_index"),
                            "control_index": item.get("control_index"),
                            "anchor_paragraph_ordinal": item.get("anchor_paragraph_ordinal"),
                            "bin_item_id": item.get("bin_item_id"),
                            "binary_stream": (item.get("binary_link") or {}).get("stream"),
                            "binary_link_fidelity": item.get("binary_link_fidelity"),
                            "has_control_geometry": bool(item.get("control_geometry")),
                            "payload_bytes": item.get("payload_bytes"),
                        }
                        for item in graph.get("pictures", [])
                    ], ensure_ascii=False, sort_keys=True))

                if family == "table":
                    if not graph.get("tables"):
                        raise RuntimeError(f"table fixture yielded no table: {graph}")
                    if not closure.get("table_cell_paragraph_binding"):
                        raise RuntimeError(f"table binding did not close: {assessment}")
                elif family == "equation":
                    if not graph.get("equations"):
                        raise RuntimeError(f"equation fixture yielded no equation: {graph}")
                    if not closure.get("equation_anchor_position_binding"):
                        raise RuntimeError(f"equation binding did not close: {assessment}")
                elif family == "picture":
                    if not graph.get("pictures"):
                        raise RuntimeError(f"picture fixture yielded no picture: {graph}")
                    if not closure.get("picture_bindata_geometry_binding"):
                        raise RuntimeError(f"picture binding did not close: {assessment}")

                rich = _payload(await client.call_tool("materialize_hwp5_rich_derivative", {
                    "content_base64": encoded,
                    "filename": path.name,
                    "request_id": f"p37-real-{family}-fixture-v1",
                    "promote_tables": family == "table",
                    "promote_equations": family == "equation",
                    "promote_pictures": family == "picture",
                }))
                if not rich or not rich.get("ok"):
                    raise RuntimeError(f"{family}: rich derivative failed: {rich}")
                created.append(rich["document_id"])
                promotion = rich.get("promotion_report", {}).get(
                    {"table": "tables", "equation": "equations", "picture": "pictures"}[family],
                    {},
                )
                if int(promotion.get("promoted", 0)) < 1:
                    raise RuntimeError(f"{family}: no native rich object promoted: {rich}")

                inventory = rich.get("final_inventory", {})
                expected_key = {"table": "tables", "equation": "equations", "picture": "pictures"}[family]
                if int(inventory.get(expected_key, 0)) < 1:
                    raise RuntimeError(f"{family}: promoted object absent from final HWPX map: {rich}")

                oracle = _payload(await client.call_tool("compare_hwp5_roundtrip_fidelity", {
                    "content_base64": encoded,
                    "document_id": rich["document_id"],
                    "filename": path.name,
                }))
                if not oracle or not oracle.get("provenance_match"):
                    raise RuntimeError(f"{family}: round-trip provenance mismatch: {oracle}")
                families = oracle.get("families", {})
                if family == "table":
                    table_family = families.get("tables", {}) or {}
                    if not table_family.get("geometry_exact"):
                        raise RuntimeError(f"table geometry round-trip mismatch: {oracle}")
                    if not table_family.get("cell_geometry_exact"):
                        raise RuntimeError(f"table cell geometry round-trip mismatch: {oracle}")
                if family == "equation" and not (families.get("equations", {}) or {}).get("script_exact"):
                    raise RuntimeError(f"equation script round-trip mismatch: {oracle}")
                if family == "picture" and not (families.get("pictures", {}) or {}).get("count_exact"):
                    raise RuntimeError(f"picture count round-trip mismatch: {oracle}")

                reports[family] = {
                    "source_bytes": len(raw),
                    "closure": closure,
                    "promotion": promotion,
                    "final_inventory": inventory,
                    "control_count": len(graph.get("controls", [])),
                    "edge_count": len(graph.get("edges", [])),
                    "roundtrip": oracle.get("families", {}),
                }

            for doc_id in created:
                deleted = _payload(await client.call_tool("delete_document", {"document_id": doc_id}))
                if not deleted or not deleted.get("deleted"):
                    raise RuntimeError(f"cleanup failed: {doc_id}: {deleted}")

    print("P3.7 REAL_RICH_HWP_PROMOTION_PASS")
    print(json.dumps(reports, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
