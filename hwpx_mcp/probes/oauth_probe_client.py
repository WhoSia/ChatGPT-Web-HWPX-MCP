"""Shared, non-production OAuth client utilities for real-HWP world-contact probes.

The probe CLI must not depend on importing the monolithic lifecycle test
module by its old root location. Browser approval here uses the explicit
test passphrase supplied only by CI; it does not bypass production consent.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urljoin, urlparse

import httpx2
from mcp.client.auth import AuthorizationCodeResult
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


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
        value = getattr(block, "text", None)
        if not value:
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
