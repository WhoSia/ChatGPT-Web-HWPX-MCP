from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from urllib.parse import parse_qs, urljoin, urlparse

import httpx2
from pydantic import AnyUrl

from mcp import Client
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")
RUN_WRITE_TEST = os.environ.get("RUN_P12_WRITE_TEST", os.environ.get("RUN_P11_WRITE_TEST", "")) == "1"
P11_OAUTH_PASSPHRASE = os.environ.get("P11_OAUTH_PASSPHRASE", "")


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
        async with httpx2.AsyncClient(follow_redirects=False) as browser:
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
            client_name="ChatGPT Web HWPX MCP P1.2 CI",
            redirect_uris=[AnyUrl("http://127.0.0.1:8765/callback")],
            scope="hwpx offline_access",
        ),
        storage=InMemoryTokenStorage(),
        redirect_handler=approver.redirect_handler,
        callback_handler=approver.callback_handler,
    )

    async with httpx2.AsyncClient(auth=oauth) as http_client:
        transport = streamable_http_client(URL, http_client=http_client)
        async with Client(transport) as client:
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
            }
            missing = expected - set(names)
            if missing:
                raise RuntimeError(f"missing tools: {sorted(missing)}")
            for tool in tools.tools:
                schema_text = json.dumps(tool.input_schema, ensure_ascii=False).lower()
                if "access_token" in schema_text or "passphrase" in schema_text:
                    raise RuntimeError(f"secret-bearing field leaked into tool schema: {tool.name}")

            read_payload = _payload(await client.call_tool("probe_read", {"message": "P1.2 OAuth smoke test"}))
            if not read_payload or not read_payload.get("ok"):
                raise RuntimeError("probe_read did not return ok=true")

            if not RUN_WRITE_TEST:
                return

            created = _payload(await client.call_tool("create_document", {
                "title": "P1.2 CI",
                "text": "ChatGPT Web HWPX MCP\nDurable OAuth and bounded ingress",
                "filename": "p1-2-ci.hwpx",
            }))
            if not created or not created.get("ok"):
                raise RuntimeError(f"create_document failed: {created}")
            document_id = created["document_id"]

            exported = _payload(await client.call_tool("export_document", {"document_id": document_id, "link_ttl_seconds": 120}))
            if not exported or not exported.get("download_url"):
                raise RuntimeError(f"export_document failed: {exported}")
            async with httpx2.AsyncClient() as downloader:
                download = await downloader.get(exported["download_url"])
            if download.status_code != 200:
                raise RuntimeError(f"download failed: {download.status_code} {download.text}")
            digest = hashlib.sha256(download.content).hexdigest()
            if digest != exported["sha256"] or download.content[:2] != b"PK":
                raise RuntimeError("generated artifact receipt mismatch")

            ingested = _payload(await client.call_tool("ingest_document", {
                "filename": "p1-2-existing.hwpx",
                "content_base64": base64.b64encode(download.content).decode("ascii"),
            }))
            if not ingested or ingested.get("admission") != "PASS":
                raise RuntimeError(f"ingest_document failed: {ingested}")
            if ingested.get("sha256") != digest:
                raise RuntimeError("ingested HWPX SHA-256 changed")
            inspected = _payload(await client.call_tool("inspect_document", {"document_id": ingested["document_id"]}))
            if not inspected or not inspected.get("validation", {}).get("valid"):
                raise RuntimeError(f"inspect ingested document failed: {inspected}")

            for doc_id in (document_id, ingested["document_id"]):
                deleted = _payload(await client.call_tool("delete_document", {"document_id": doc_id}))
                if not deleted or not deleted.get("deleted"):
                    raise RuntimeError(f"delete_document failed: {deleted}")
            print("P1.2 lifecycle PASS", digest)


if __name__ == "__main__":
    asyncio.run(main())
