from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from mcp.server import MCPServer
from starlette.responses import JSONResponse

PROJECT = "ChatGPT Web HWPX MCP"
VERSION = "0.1.0-p0"

# P0 intentionally does NOT include the real HWPX engine.
# The objective is to test ChatGPT Web <-> remote MCP transport and
# the read/write capability boundary with the smallest possible server.

mcp = MCPServer(
    PROJECT,
    instructions=(
        "P0 transport/capability probe for ChatGPT Web. "
        "Use probe_read for a side-effect-free test. "
        "Use probe_write only when the user explicitly asks to test write actions."
    ),
)

ARTIFACT_DIR = Path(os.environ.get("P0_ARTIFACT_DIR", "/tmp/chatgpt-web-hwpx-mcp-p0"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# Optional shared secret for the write probe itself.
# This is not MCP transport authentication; it merely prevents casual invocation
# of the deliberately side-effecting P0 tool during an unauthenticated prototype.
WRITE_NONCE = os.environ.get("P0_WRITE_NONCE", "")


@mcp.tool()
def probe_read(message: str = "hello") -> dict:
    """Side-effect-free connectivity probe. Returns server identity and echoes a short message."""
    return {
        "ok": True,
        "project": PROJECT,
        "version": VERSION,
        "probe": "read",
        "message": message[:500],
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def probe_write(text: str, nonce: str = "") -> dict:
    """P0 write-action probe. Creates a tiny UTF-8 artifact on the remote server.

    This deliberately has a side effect so ChatGPT's write-action boundary can be tested.
    It does NOT create an HWPX file yet.
    """
    if WRITE_NONCE and not secrets.compare_digest(nonce, WRITE_NONCE):
        raise ValueError("Invalid P0 write nonce")

    payload = text[:10_000]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    token = secrets.token_hex(4)
    name = f"p0-write-{stamp}-{token}.txt"
    path = ARTIFACT_DIR / name
    path.write_text(payload, encoding="utf-8")

    return {
        "ok": True,
        "project": PROJECT,
        "version": VERSION,
        "probe": "write",
        "artifact_id": name,
        "bytes": path.stat().st_size,
        "note": (
            "The artifact exists on the remote MCP host only. "
            "P1 will replace this with a document-id/object-store handoff suitable for HWPX."
        ),
    }


@mcp.tool()
def probe_capabilities() -> dict:
    """Describe exactly what this P0 server is intended to test."""
    return {
        "project": PROJECT,
        "version": VERSION,
        "transport_target": "MCP Streamable HTTP",
        "endpoint": "/mcp",
        "tools": {
            "probe_read": "read-only / no side effect",
            "probe_write": "write / creates one temporary text artifact",
            "probe_capabilities": "read-only metadata",
        },
        "not_in_scope_yet": [
            "real HWPX parsing/editing",
            "file upload from ChatGPT to MCP",
            "downloadable artifact return",
            "OAuth",
            "Hancom rendering",
        ],
    }


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    """Unauthenticated liveness endpoint. Contains no private data."""
    return JSONResponse(
        {
            "status": "ok",
            "project": PROJECT,
            "version": VERSION,
        }
    )


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("MCP_PORT", "8000")))
    path = os.environ.get("MCP_PATH", "/mcp")

    # Official SDK v2 Streamable HTTP server.
    # For public deployment, put TLS at the hosting platform/reverse proxy layer.
    mcp.run(
        "streamable-http",
        host=host,
        port=port,
        streamable_http_path=path,
        stateless_http=True,
        json_response=True,
    )
