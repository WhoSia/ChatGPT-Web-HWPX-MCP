from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from pydantic import AnyHttpUrl

from auth_store import DurableOAuthStore
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
    """Single-user OAuth 2.1 provider with durable encrypted server-side state."""

    def __init__(
        self,
        *,
        base_url: str,
        resource_url: str,
        passphrase: str,
        store: DurableOAuthStore,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.resource_url = resource_url
        self.passphrase = passphrase
        self.store = store

    @property
    def configured(self) -> bool:
        return len(self.passphrase) >= 12

    @property
    def state_store_mode(self) -> str:
        return self.store.mode

    def _cleanup(self) -> None:
        self.store.cleanup()

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.store.get("client", client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.store.put(
            "client",
            client_info.client_id,
            client_info,
            client_id=client_info.client_id,
        )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        self._cleanup()
        request_id = secrets.token_urlsafe(32)
        pending = PendingAuthorization(
            client_id=client.client_id,
            params=params,
            expires_at=time.time() + PENDING_TTL_SECONDS,
        )
        self.store.put(
            "pending",
            request_id,
            pending,
            client_id=client.client_id,
            expires_at=pending.expires_at,
        )
        return f"{self.base_url}/oauth/approve?{urlencode({'request': request_id})}"

    def approval_status(self, request_id: str) -> str:
        self._cleanup()
        pending = self.store.get("pending", request_id)
        if pending is None:
            return "missing"
        if not self.configured:
            return "unconfigured"
        return "ready"

    def approve(self, request_id: str, supplied_passphrase: str) -> tuple[bool, str]:
        self._cleanup()
        pending: PendingAuthorization | None = self.store.get("pending", request_id)
        if pending is None:
            return False, "Authorization request expired or is unknown."
        if not self.configured:
            return False, "P11_OAUTH_PASSPHRASE is not configured with at least 12 characters."

        if not secrets.compare_digest(supplied_passphrase, self.passphrase):
            pending.attempts += 1
            if pending.attempts >= MAX_APPROVAL_ATTEMPTS:
                self.store.delete("pending", request_id)
                return False, "Too many failed approval attempts; restart authorization."
            self.store.put(
                "pending",
                request_id,
                pending,
                client_id=pending.client_id,
                expires_at=pending.expires_at,
            )
            return False, "Invalid authorization passphrase."

        params = pending.params
        scopes = list(params.scopes or [HWPX_SCOPE, OFFLINE_SCOPE])
        if HWPX_SCOPE not in scopes:
            scopes.append(HWPX_SCOPE)
        if OFFLINE_SCOPE not in scopes:
            scopes.append(OFFLINE_SCOPE)
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
        self.store.put(
            "code",
            code.code,
            code,
            client_id=code.client_id,
            subject=code.subject,
            expires_at=code.expires_at,
        )
        self.store.delete("pending", request_id)
        return True, construct_redirect_uri(
            str(params.redirect_uri),
            code=code.code,
            state=params.state,
        )

    def deny(self, request_id: str) -> str | None:
        self._cleanup()
        pending: PendingAuthorization | None = self.store.get("pending", request_id)
        if pending is None:
            return None
        self.store.delete("pending", request_id)
        return construct_redirect_uri(
            str(pending.params.redirect_uri),
            error="access_denied",
            state=pending.params.state,
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        self._cleanup()
        code: AuthorizationCode | None = self.store.get("code", authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        return code

    def _mint_access_token(self, *, client_id: str, scopes: list[str], resource: str, subject: str) -> AccessToken:
        return AccessToken(
            token="at_" + secrets.token_urlsafe(32),
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + ACCESS_TOKEN_TTL_SECONDS,
            resource=resource,
            subject=subject,
            claims={"iss": self.base_url},
        )

    def _mint_refresh_token(self, *, client_id: str, scopes: list[str], resource: str, subject: str) -> RefreshToken:
        return RefreshToken(
            token="rt_" + secrets.token_urlsafe(40),
            client_id=client_id,
            scopes=scopes,
            expires_at=int(time.time()) + REFRESH_TOKEN_TTL_SECONDS,
            resource=resource,
            subject=subject,
        )

    @staticmethod
    def _issued_item(kind: str, token: AccessToken | RefreshToken) -> dict:
        return {
            "kind": kind,
            "key": token.token,
            "obj": token,
            "client_id": token.client_id,
            "subject": token.subject,
            "expires_at": token.expires_at,
        }

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self._cleanup()
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
        if not self.store.consume_and_issue(
            consumed_kind="code",
            consumed_key=authorization_code.code,
            issued=[self._issued_item("access", access), self._issued_item("refresh", refresh)],
        ):
            raise ValueError("Authorization code already consumed, revoked, or expired")
        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh.token,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        self._cleanup()
        return self.store.get("access", token)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        self._cleanup()
        token: RefreshToken | None = self.store.get("refresh", refresh_token)
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
        if OFFLINE_SCOPE not in requested:
            requested.append(OFFLINE_SCOPE)

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
        if not self.store.consume_and_issue(
            consumed_kind="refresh",
            consumed_key=refresh_token.token,
            issued=[self._issued_item("access", access), self._issued_item("refresh", rotated)],
        ):
            raise ValueError("Refresh token already consumed, revoked, or expired")
        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(requested),
            refresh_token=rotated.token,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self.store.revoke_family(token.client_id, token.subject)


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
