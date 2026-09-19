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
HWP = Path(os.environ.get("P37_PAIR_HWP", "/tmp/para-001.hwp"))
HWPX = Path(os.environ.get("P37_PAIR_HWPX", "/tmp/para-001.hwpx"))


async def main() -> None:
    hwp_raw = HWP.read_bytes()
    hwpx_raw = HWPX.read_bytes()
    hwp_b64 = base64.b64encode(hwp_raw).decode("ascii")
    hwpx_b64 = base64.b64encode(hwpx_raw).decode("ascii")

    approver = HeadlessApprover(PASSPHRASE)
    oauth = OAuthClientProvider(
        server_url=URL,
        client_metadata=OAuthClientMetadata(
            client_name="P3.7 HWP-HWPX Equivalence Probe",
            redirect_uris=[AnyUrl("http://127.0.0.1:8765/callback")],
            scope="hwpx offline_access",
        ),
        storage=InMemoryTokenStorage(),
        redirect_handler=approver.redirect_handler,
        callback_handler=approver.callback_handler,
    )
    document_id = None
    async with httpx2.AsyncClient(auth=oauth, timeout=60.0) as http_client:
        transport = streamable_http_client(URL, http_client=http_client)
        async with Client(transport, mode="2026-07-28") as client:
            source_ir = _payload(await client.call_tool("get_common_document_ir", {
                "content_base64": hwp_b64,
                "filename": HWP.name,
                "include_blocks": True,
                "max_blocks": 1000,
            }))
            if not source_ir or source_ir.get("source_format") != "hwp5":
                raise RuntimeError(f"HWP common IR failed: {source_ir}")
            source_paragraphs = [
                block for block in source_ir.get("blocks", [])
                if block.get("kind") == "paragraph"
            ]
            recovered_runs = sum(
                len((block.get("data") or {}).get("runs", []))
                for block in source_paragraphs
            )
            if recovered_runs < 1:
                raise RuntimeError(f"HWP equivalence fixture yielded no recovered runs: {source_ir}")

            ingested = _payload(await client.call_tool("ingest_document", {
                "content_base64": hwpx_b64,
                "filename": HWPX.name,
            }))
            if not ingested or not ingested.get("ok"):
                raise RuntimeError(f"HWPX pair ingestion failed: {ingested}")
            document_id = ingested["document_id"]

            target_ir = _payload(await client.call_tool("get_common_document_ir", {
                "document_id": document_id,
                "include_blocks": True,
                "max_blocks": 1000,
            }))
            if not target_ir or target_ir.get("source_format") != "hwpx":
                raise RuntimeError(f"HWPX common IR failed: {target_ir}")

            oracle = _payload(await client.call_tool("compare_hwp5_roundtrip_fidelity", {
                "content_base64": hwp_b64,
                "document_id": document_id,
                "filename": HWP.name,
                "require_provenance": False,
            }))
            if not oracle or oracle.get("authority") != "CROSS_FORMAT_EQUIVALENCE_RECEIPT":
                raise RuntimeError(f"equivalence authority failed: {oracle}")
            families = oracle.get("families", {})
            if not (families.get("body_text") or {}).get("exact"):
                raise RuntimeError(f"known-equivalent pair body text mismatch: {oracle}")

            report = {
                "hwp_bytes": len(hwp_raw),
                "hwpx_bytes": len(hwpx_raw),
                "source_ir_sha256": source_ir.get("ir_sha256"),
                "target_ir_sha256": target_ir.get("ir_sha256"),
                "source_paragraph_blocks": len(source_paragraphs),
                "source_recovered_runs": recovered_runs,
                "body_text": families.get("body_text"),
                "run_style": families.get("run_style"),
                "tables": families.get("tables"),
                "equations": families.get("equations"),
                "pictures": families.get("pictures"),
                "authority": oracle.get("authority"),
            }

            deleted = _payload(await client.call_tool(
                "delete_document", {"document_id": document_id}
            ))
            if not deleted or not deleted.get("deleted"):
                raise RuntimeError(f"pair cleanup failed: {deleted}")
            document_id = None

    print("P3.7 REAL_HWP_HWPX_EQUIVALENCE_PASS")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
