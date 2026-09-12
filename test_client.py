from __future__ import annotations

import asyncio
import os
from mcp import Client

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")


async def main() -> None:
    async with Client(URL) as client:
        print("protocol:", client.protocol_version)
        print("server:", client.server_info)
        tools = await client.list_tools()
        print("tools:")
        for tool in tools.tools:
            print(" -", tool.name)

        result = await client.call_tool("probe_read", {"message": "P0 local smoke test"})
        print("probe_read:", result.structured_content)


if __name__ == "__main__":
    asyncio.run(main())
