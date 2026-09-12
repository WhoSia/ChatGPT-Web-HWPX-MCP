from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from pydantic import AnyHttpUrl

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

HWPX_SCOPE = "hwpx"
OFFLINE_SCOPE = "offline_access"
SUBJECT = "hwpx-owner"
ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
PENDING_TTL_SECONDS = 5 * 60
MAX_APPROVAL_ATTEMPTS = 5


@dataclass
class PendingAuthorization:
    client_id: str
    params: AuthorizationParams
    expires_at: float
    attempts: int = 0


class SingleUserOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """Small single-user OAuth 2.1 provider for the P1.1 prototype.

    ChatGPT performs DCR + PKCE. The resource owner authorizes in a browser by
    entering a server-side passphrase. The passphrase is never part of an MCP
    tool schema or tool call.

    State is intentionally in-memory in P1.1. A service restart therefore
    invalidates registrations and tokens and requires re-authorization.
    """

    def __init__(self, *, base_url: str, resource_url: str, passphrase: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.resource_url = resource_url
        self.passphrase = passphrase
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.access_tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self.pending: dict[str, PendingAuthorization] = {}

    @property
    def configured(self) -> bool:
        return len(self.passphrase) >= 12

    def _cleanup(self) -> None:
        now = time.time()
        for request_id, pending in list(self.pending.items()):
            if pending.expires_at <= now:
                self.pending.pop(request_id, None)
        for code_value, code in list(self.codes.items()):
            if code.expires_at <= now:
                self.codes.pop(code_value, None)
        for token_value, token in list(self.access_tokens.items()):
            if token.expires_at is not None and token.expires_at <= int(now):
                self.access_tokens.pop(token_value, None)
        for token_value, token in list(self.refresh_tokens.items()):
            if token.expires_at is not None and token.expires_at <= int(now):
                self.refresh_tokens.pop(token_value, None)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        self._cleanup()
        request_id = secrets.token_urlsafe(32)
        self.pending[request_id] = PendingAuthorization(
            client_id=client.client_id,
            params=params,
            expires_at=time.time() + PENDING_TTL_SECONDS,
        )
        return f"{self.base_url}/oauth/approve?{urlencode({'request': request_id})}"

    def approval_status(self, request_id: str) -> str:
        self._cleanup()
        pending = self.pending.get(request_id)
        if pending is None:
            return "missing"
        if not self.configured:
            return "unconfigured"
        return "ready"

    def approve(self, request_id: str, supplied_passphrase: str) -> tuple[bool, str]:
        self._cleanup()
        pending = self.pending.get(request_id)
        if pending is None:
            return False, "Authorization request expired or is unknown."
        if not self.configured:
            return False, "P11_OAUTH_PASSPHRASE is not configured with at least 12 characters."

        if not secrets.compare_digest(supplied_passphrase, self.passphrase):
            pending.attempts += 1
            if pending.attempts >= MAX_APPROVAL_ATTEMPTS:
                self.pending.pop(request_id, None)
                return False, "Too many failed approval attempts; restart authorization."
            return False, "Invalid authorization passphrase."

        params = pending.params
        scopes = list(params.scopes or [HWPX_SCOPE, OFFLINE_SCOPE])
        if HWPX_SCOPE not in scopes:
            scopes.append(HWPX_SCOPE)
        resource = params.resource or self.resource_url
        code = AuthorizationCode(
            code="code_" + secrets.token_urlsafe(32),
            client_id=pending.client_id,
            scopes=scopes,
            expires_at=time.time() + 300,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=resource,
            subject=SUBJECT,
        )
        self.codes[code.code] = code
        self.pending.pop(request_id, None)
        return True, construct_redirect_uri(
            str(params.redirect_uri),
            code=code.code,
            state=params.state,
        )

    def deny(self, request_id: str) -> str | None:
        self._cleanup()
        pending = self.pending.pop(request_id, None)
        if pending is None:
            return None
        return construct_redirect_uri(
            str(pending.params.redirect_uri),
            error="access_denied",
            state=pending.params.state,
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        self._cleanup()
        code = self.codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        return code

    def _mint_access_token(self, *, client_id: str, scopes: list[str], resource: str, subject: str) -> AccessToken:
        value = "at_" + secrets.token_urlsafe(32)
        token = AccessToken(
            token=value,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + ACCESS_TOKEN_TTL_SECONDS,
            resource=resource,
            subject=subject,
            claims={"iss": self.base_url},
        )
        self.access_tokens[value] = token
        return token

    def _mint_refresh_token(self, *, client_id: str, scopes: list[str], resource: str, subject: str) -> RefreshToken:
        value = "rt_" + secrets.token_urlsafe(40)
        token = RefreshToken(
            token=value,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + REFRESH_TOKEN_TTL_SECONDS,
            resource=resource,
            subject=subject,
        )
        self.refresh_tokens[value] = token
        return token

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self._cleanup()
        self.codes.pop(authorization_code.code, None)
        resource = authorization_code.resource or self.resource_url
        subject = authorization_code.subject or SUBJECT
        access = self._mint_access_token(
            client_id=authorization_code.client_id,
            scopes=authorization_code.scopes,
            resource=resource,
            subject=subject,
        )
        refresh = self._mint_refresh_token(
            client_id=authorization_code.client_id,
            scopes=authorization_code.scopes,
            resource=resource,
            subject=subject,
        )
        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh.token,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        self._cleanup()
        return self.access_tokens.get(token)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        self._cleanup()
        token = self.refresh_tokens.get(refresh_token)
        if token is None or token.client_id != client.client_id:
            return None
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        self._cleanup()
        requested = list(scopes or refresh_token.scopes)
        if not set(requested).issubset(set(refresh_token.scopes)):
            requested = list(refresh_token.scopes)
        if HWPX_SCOPE not in requested:
            requested.append(HWPX_SCOPE)

        self.refresh_tokens.pop(refresh_token.token, None)
        resource = refresh_token.resource or self.resource_url
        subject = refresh_token.subject or SUBJECT
        access = self._mint_access_token(
            client_id=client.client_id,
            scopes=requested,
            resource=resource,
            subject=subject,
        )
        rotated = self._mint_refresh_token(
            client_id=client.client_id,
            scopes=requested,
            resource=resource,
            subject=subject,
        )
        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(requested),
            refresh_token=rotated.token,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # This is a single-user prototype: revocation invalidates the caller's
        # whole client/subject token family rather than only one token string.
        client_id = token.client_id
        subject = token.subject
        for value, candidate in list(self.access_tokens.items()):
            if candidate.client_id == client_id and candidate.subject == subject:
                self.access_tokens.pop(value, None)
        for value, candidate in list(self.refresh_tokens.items()):
            if candidate.client_id == client_id and candidate.subject == subject:
                self.refresh_tokens.pop(value, None)


def build_auth_settings(*, base_url: str, resource_url: str) -> AuthSettings:
    scopes = [HWPX_SCOPE, OFFLINE_SCOPE]
    return AuthSettings(
        issuer_url=AnyHttpUrl(base_url),
        resource_server_url=AnyHttpUrl(resource_url),
        required_scopes=[HWPX_SCOPE],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=scopes,
            default_scopes=scopes,
        ),
        validate_token_resource=True,
    )
