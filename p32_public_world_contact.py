from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx2

MCP_URL = os.environ.get("MCP_URL", "https://chatgpt-web-hwpx-mcp-p0.onrender.com/mcp")
BASE_URL = MCP_URL.rsplit("/mcp", 1)[0]
PASSPHRASE = os.environ.get("P11_OAUTH_PASSPHRASE", "")
REDIRECT_URI = "http://127.0.0.1:8765/callback"
PROTOCOL = "2026-07-28"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def parse_json_response(resp: httpx2.Response) -> dict:
    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        return resp.json()
    text = resp.text
    if "text/event-stream" in ctype:
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    return json.loads(payload)
    raise RuntimeError(f"unexpected response content-type={ctype!r} status={resp.status_code} body={text[:500]!r}")


def tool_payload(result: dict) -> dict | None:
    if result.get("isError"):
        return None
    structured = result.get("structuredContent") or result.get("structured_content")
    if isinstance(structured, dict):
        return structured
    for block in result.get("content") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            try:
                value = json.loads(block["text"])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    return None


async def main() -> None:
    if len(PASSPHRASE) < 12:
        raise RuntimeError("P11_OAUTH_PASSPHRASE is required")

    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode("ascii")).digest())

    async with httpx2.AsyncClient(follow_redirects=False, timeout=60.0, http2=False, headers={"Connection": "close"}) as client:
        registration = await client.post(
            f"{BASE_URL}/register",
            json={
                "client_name": "P3.2-R1 Raw MCP World Contact",
                "redirect_uris": [REDIRECT_URI],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": "hwpx offline_access",
            },
        )
        registration.raise_for_status()
        client_info = registration.json()
        client_id = client_info["client_id"]

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "state": secrets.token_urlsafe(24),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": MCP_URL,
            "scope": "hwpx offline_access",
            "prompt": "consent",
        }
        authorize = await client.get(f"{BASE_URL}/authorize?{urlencode(params)}")
        if authorize.status_code not in (302, 303, 307, 308):
            raise RuntimeError(f"authorize status={authorize.status_code}")
        approval_url = urljoin(BASE_URL, authorize.headers["location"])
        request_id = parse_qs(urlparse(approval_url).query).get("request", [""])[0]
        if not request_id:
            raise RuntimeError("approval request id missing")

        approved = await client.post(
            approval_url,
            data={"request": request_id, "passphrase": PASSPHRASE, "decision": "approve"},
        )
        if approved.status_code not in (302, 303, 307, 308):
            raise RuntimeError(f"approval status={approved.status_code}")
        callback = urljoin(approval_url, approved.headers["location"])
        code = parse_qs(urlparse(callback).query).get("code", [""])[0]
        if not code:
            raise RuntimeError("authorization code missing")

        token_response = await client.post(
            f"{BASE_URL}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": MCP_URL,
            },
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data["access_token"]
        print("oauth: DCR+PKCE+token PASS")

        transport_client = httpx2.AsyncClient(follow_redirects=False, timeout=60.0, http2=False, headers={"Connection": "close"})
        print("transport: forced HTTP/1.1 + connection-close")

        async def safe_probe(label: str, method: str, url: str, headers: dict | None = None) -> int:
            response = await transport_client.request(method, url, headers=headers or {})
            print(
                f"http-probe {label}:",
                response.status_code,
                response.headers.get("content-type", ""),
                response.text[:220].replace("\n", " "),
            )
            return response.status_code

        await safe_probe("health-no-auth", "GET", f"{BASE_URL}/health")
        await safe_probe(
            "health-valid-bearer",
            "GET",
            f"{BASE_URL}/health",
            {"Authorization": f"Bearer {access_token}"},
        )
        await safe_probe("auth-probe-no-auth", "POST", f"{BASE_URL}/p32-r2/auth-probe")
        await safe_probe(
            "auth-probe-bogus-bearer",
            "POST",
            f"{BASE_URL}/p32-r2/auth-probe",
            {"Authorization": "Bearer at_invalid"},
        )
        auth_probe = await transport_client.post(
            f"{BASE_URL}/p32-r2/auth-probe",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        print(
            "http-probe auth-probe-valid-bearer:",
            auth_probe.status_code,
            auth_probe.headers.get("content-type", ""),
            auth_probe.text[:300].replace("\n", " "),
        )
        if auth_probe.status_code != 200:
            raise RuntimeError(
                f"bearer lookup probe failed HTTP {auth_probe.status_code}: {auth_probe.text[:500]}"
            )

        async def wire_probe(label: str, headers: dict, payload: dict) -> int:
            response = await transport_client.post(MCP_URL, headers=headers, json=payload)
            print(
                f"wire-probe {label}:",
                response.status_code,
                response.headers.get("content-type", ""),
                response.text[:220].replace("\n", " "),
            )
            return response.status_code

        base_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        await wire_probe(
            "ping-auth-only",
            dict(base_headers),
            {"jsonrpc": "2.0", "id": 9001, "method": "ping", "params": {}},
        )
        await wire_probe(
            "ping-protocol",
            {**base_headers, "MCP-Protocol-Version": PROTOCOL},
            {"jsonrpc": "2.0", "id": 9002, "method": "ping", "params": {}},
        )

        rpc_id = 0
        async def rpc(method: str, params: dict | None = None, *, tool_name: str = "") -> dict:
            nonlocal rpc_id
            rpc_id += 1
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": PROTOCOL,
                "MCP-Method": method,
            }
            if tool_name:
                headers["MCP-Name"] = tool_name
            response = await transport_client.post(
                MCP_URL,
                headers=headers,
                json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params or {}},
            )
            safe_body = response.text[:700]
            if response.status_code >= 400:
                raise RuntimeError(f"RPC {method} HTTP {response.status_code}: {safe_body}")
            message = parse_json_response(response)
            if "error" in message:
                raise RuntimeError(f"RPC {method} error: {message['error']}")
            return message["result"]

        async def call_tool(name: str, arguments: dict, *, allow_error: bool = False) -> dict | None:
            result = await rpc("tools/call", {"name": name, "arguments": arguments}, tool_name=name)
            if result.get("isError"):
                if allow_error:
                    return None
                raise RuntimeError(f"tool {name} returned isError: {result}")
            payload = tool_payload(result)
            if payload is None and not allow_error:
                raise RuntimeError(f"tool {name} returned no structured payload: {result}")
            return payload

        listed = await rpc("tools/list")
        names = {item.get("name") for item in listed.get("tools", [])}
        required = {
            "create_document", "get_document_map", "apply_edits",
            "pin_document_revision", "acquire_document_lease", "release_document_lease",
            "compact_document_history", "verify_document_lineage", "delete_document",
        }
        missing = sorted(required - names)
        if missing:
            raise RuntimeError(f"missing public tools: {missing}")
        print("tools/list: P3.2 lineage surface PASS")

        document_id = None
        try:
            created = await call_tool("create_document", {
                "title": "P3.2-R1 Production World Contact",
                "text": "alpha\nbeta",
                "filename": "p32-r1-world-contact.hwpx",
            })
            document_id = created["document_id"]
            if created.get("revision") != 1:
                raise RuntimeError(f"unexpected initial revision: {created}")

            revision = 1
            for text_value in ("gamma", "delta", "epsilon"):
                mapped = await call_tool("get_document_map", {"document_id": document_id})
                locator = mapped["paragraphs"][-1]["locator"]
                edited = await call_tool("apply_edits", {
                    "document_id": document_id,
                    "expected_revision": revision,
                    "operations": [
                        {"op": "replace_paragraph_text", "target": locator, "text": text_value}
                    ],
                })
                revision += 1
                if edited.get("revision_after") != revision:
                    raise RuntimeError(f"revision advance failed: {edited}")

            pinned = await call_tool("pin_document_revision", {
                "document_id": document_id,
                "revision": 1,
                "reason": "p32-r1-production-anchor",
            })
            if pinned.get("revision") != 1 or not pinned.get("pinned"):
                raise RuntimeError(f"pin failed: {pinned}")

            lease = await call_tool("acquire_document_lease", {
                "document_id": document_id,
                "expected_revision": 4,
                "ttl_seconds": 30,
                "holder_id": "p32-r1-production",
            })
            lease_token = lease["lease_token"]

            blocked = await call_tool("compact_document_history", {
                "document_id": document_id,
                "expected_revision": 4,
                "keep_last": 2,
                "dry_run": False,
            }, allow_error=True)
            if blocked is not None:
                raise RuntimeError(f"active lease did not block compaction: {blocked}")

            released = await call_tool("release_document_lease", {
                "document_id": document_id,
                "lease_token": lease_token,
            })
            if not released.get("released"):
                raise RuntimeError(f"lease release failed: {released}")

            preview = await call_tool("compact_document_history", {
                "document_id": document_id,
                "expected_revision": 4,
                "keep_last": 2,
                "dry_run": True,
            })
            if preview.get("prunable_revisions") != [2]:
                raise RuntimeError(f"unexpected dry-run geometry: {preview}")

            compacted = await call_tool("compact_document_history", {
                "document_id": document_id,
                "expected_revision": 4,
                "keep_last": 2,
                "dry_run": False,
            })
            if compacted.get("deleted_revisions") != [2]:
                raise RuntimeError(f"unexpected compaction receipt: {compacted}")
            if not compacted.get("audit_chain_valid") or not compacted.get("restore_reachability_valid"):
                raise RuntimeError(f"post-compaction verification failed: {compacted}")

            lineage = await call_tool("verify_document_lineage", {"document_id": document_id})
            if not lineage.get("audit_chain_valid") or not lineage.get("restore_reachability_valid"):
                raise RuntimeError(f"lineage invalid: {lineage}")
            if lineage.get("commit_count") != 4:
                raise RuntimeError(f"unexpected commit count: {lineage}")
            if lineage.get("pinned_revisions") != [1]:
                raise RuntimeError(f"pin not preserved: {lineage}")
            if lineage.get("retained_revisions") != [1, 3, 4]:
                raise RuntimeError(f"unexpected retained revisions: {lineage}")

            print("world-contact: pin→lease-block→compact→verify PASS")
            print("receipt:", json.dumps({
                "revision": lineage["current_revision"],
                "commit_count": lineage["commit_count"],
                "retained_revisions": lineage["retained_revisions"],
                "compacted_revisions": lineage["compacted_revisions"],
                "pinned_revisions": lineage["pinned_revisions"],
                "audit_head": lineage["audit_head"],
            }, sort_keys=True))
        finally:
            if document_id:
                deleted = await call_tool("delete_document", {"document_id": document_id}, allow_error=True)
                print("cleanup:", bool(deleted and deleted.get("deleted")))
            await transport_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
