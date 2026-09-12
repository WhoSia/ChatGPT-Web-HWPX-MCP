from __future__ import annotations

import asyncio
import json
import os
from mcp import Client

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
RUN_P1_WRITE_TEST = os.environ.get("RUN_P1_WRITE_TEST", "") == "1"
P1_ACCESS_TOKEN = os.environ.get("P1_ACCESS_TOKEN", "")


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
    async with Client(URL) as client:
        print("protocol:", client.protocol_version)
        print("server:", client.server_info)
        tools = await client.list_tools()
        names = [tool.name for tool in tools.tools]
        print("tools:")
        for name in names:
            print(" -", name)

        expected = {
            "probe_read",
            "probe_capabilities",
            "create_document",
            "inspect_document",
            "export_document",
            "delete_document",
        }
        missing = expected - set(names)
        if missing:
            raise RuntimeError(f"missing tools: {sorted(missing)}")

        result = await client.call_tool("probe_read", {"message": "P1 smoke test"})
        read_payload = _payload(result)
        print("probe_read:", read_payload)
        if not read_payload or not read_payload.get("ok"):
            raise RuntimeError("probe_read did not return ok=true")

        if RUN_P1_WRITE_TEST:
            if not P1_ACCESS_TOKEN:
                raise RuntimeError("P1_ACCESS_TOKEN is required for RUN_P1_WRITE_TEST=1")
            created = _payload(
                await client.call_tool(
                    "create_document",
                    {
                        "title": "P1 CI",
                        "text": "ChatGPT Web HWPX MCP\nminimal valid HWPX materialization",
                        "filename": "p1-ci.hwpx",
                        "access_token": P1_ACCESS_TOKEN,
                    },
                )
            )
            if not created or not created.get("ok"):
                raise RuntimeError(f"create_document failed: {created}")
            document_id = created["document_id"]
            print("created:", document_id, created.get("bytes"), created.get("sha256"))

            inspected = _payload(
                await client.call_tool(
                    "inspect_document",
                    {"document_id": document_id, "access_token": P1_ACCESS_TOKEN},
                )
            )
            if not inspected or not inspected.get("validation", {}).get("valid"):
                raise RuntimeError(f"inspect_document failed: {inspected}")

            exported = _payload(
                await client.call_tool(
                    "export_document",
                    {
                        "document_id": document_id,
                        "access_token": P1_ACCESS_TOKEN,
                        "link_ttl_seconds": 120,
                    },
                )
            )
            if not exported or not exported.get("download_url"):
                raise RuntimeError(f"export_document failed: {exported}")
            print("exported:", exported["download_url"])

            deleted = _payload(
                await client.call_tool(
                    "delete_document",
                    {"document_id": document_id, "access_token": P1_ACCESS_TOKEN},
                )
            )
            if not deleted or not deleted.get("deleted"):
                raise RuntimeError(f"delete_document failed: {deleted}")


if __name__ == "__main__":
    asyncio.run(main())
