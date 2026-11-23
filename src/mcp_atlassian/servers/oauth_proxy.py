"""OAuth proxy extensions and configuration helpers."""

from __future__ import annotations

import ipaddress
import json
import logging
import posixpath
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import SupportsFloat
from urllib.parse import unquote, urlsplit, urlunsplit

from cachetools import TLRUCache
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.oauth_proxy.models import (
    ClientCode,
    OAuthTransaction,
    ProxyDCRClient,
)
from key_value.aio.adapters.pydantic import PydanticAdapter
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.stores.memory.store import (
    MemoryCollection,
    _memory_cache_getsizeof,
    _memory_cache_ttu,
)
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthClientInformationFull,
    RefreshToken,
    RegistrationError,
)
from mcp.shared.auth import OAuthToken
from pydantic import AnyHttpUrl
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mcp_atlassian.utils.token_verifier import principal_subject

logger = logging.getLogger("mcp-atlassian.server.oauth_proxy")


def _normalize_list(values: Iterable[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [value.strip() for value in values if value and value.strip()]


def parse_env_list(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    if not raw.strip():
        return []
    normalized = raw.replace(",", " ")
    return [item.strip() for item in normalized.split() if item.strip()]


def _redirect_target(uri: str) -> tuple[str, str, int | None, str] | None:
    """Return the origin and route used by a redirect URI."""
    try:
        parsed = urlsplit(uri)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not hostname:
        return None

    scheme = parsed.scheme.lower()
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None

    hostname = hostname.rstrip(".").lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    try:
        hostname = str(ipaddress.ip_address(hostname))
    except ValueError:
        pass

    path = posixpath.normpath(unquote(parsed.path or "/"))
    if not path.startswith("/"):
        path = f"/{path}"

    return scheme, hostname, port, path.rstrip("/") or "/"


# Dynamic client registration is unauthenticated and each record is kept,
# so one record is bounded. Real client metadata is well under these limits.
_MAX_CLIENT_NAME_CHARS = 256
_MAX_CLIENT_METADATA_BYTES = 16 * 1024


def _check_registration_size(client_info: OAuthClientInformationFull) -> None:
    name = client_info.client_name or ""
    if len(name) > _MAX_CLIENT_NAME_CHARS:
        raise RegistrationError(
            "invalid_client_metadata",
            f"client_name is longer than {_MAX_CLIENT_NAME_CHARS} characters",
        )
    size = len(client_info.model_dump_json(exclude_none=True).encode())
    if size > _MAX_CLIENT_METADATA_BYTES:
        raise RegistrationError(
            "invalid_client_metadata",
            f"Client metadata is larger than {_MAX_CLIENT_METADATA_BYTES} bytes",
        )


# /authorize is reached before any authentication and FastMCP stores its
# fields in a transaction. Real clients send far less: the MCP SDK client sends
# a 43-character state (secrets.token_urlsafe(32)) and a 43-character S256
# challenge, and client callbacks such as http://127.0.0.1:<port>/callback or
# https://claude.ai/api/mcp/auth_callback are under 100 characters.
_MIN_CODE_CHALLENGE_CHARS = 43  # RFC 7636: S256 is 43, a plain verifier 43-128
_MAX_CODE_CHALLENGE_CHARS = 128
_MAX_STATE_CHARS = 2048
_MAX_REDIRECT_URI_CHARS = 2048
# A normal /authorize form or query is about 1 KiB; this bounds form parsing.
_MAX_AUTHORIZE_BODY_BYTES = 16 * 1024
# Default storage only: pending logins live 15 minutes and codes 5 minutes, so
# they are kept in memory, bounded, and dropped when they expire.
_MAX_PENDING_LOGIN_RECORDS = 2000
# Registration is unauthenticated, so a record starts with a short lifetime
# and only a completed authorization (code or refresh token exchange) gives it
# the long one. Each exchange renews it. Atlassian refresh tokens also expire
# after 90 days without use.
_UNUSED_CLIENT_TTL_SECONDS = 24 * 60 * 60
_USED_CLIENT_TTL_SECONDS = 90 * 24 * 60 * 60
# Default file storage keeps expired records on disk; they are deleted at start
# and at most this often when clients register.
_EXPIRED_SWEEP_INTERVAL_SECONDS = 60 * 60
# A record file is deleted only this long after it expired.
_EXPIRED_GRACE_SECONDS = 60 * 60


def _check_authorize_size(params: AuthorizationParams) -> None:
    challenge = params.code_challenge or ""
    if not _MIN_CODE_CHALLENGE_CHARS <= len(challenge) <= _MAX_CODE_CHALLENGE_CHARS:
        raise AuthorizeError(
            "invalid_request",
            f"code_challenge must be {_MIN_CODE_CHALLENGE_CHARS} to "
            f"{_MAX_CODE_CHALLENGE_CHARS} characters",
        )
    if len(params.state or "") > _MAX_STATE_CHARS:
        raise AuthorizeError(
            "invalid_request", f"state is longer than {_MAX_STATE_CHARS} characters"
        )
    if len(str(params.redirect_uri or "")) > _MAX_REDIRECT_URI_CHARS:
        raise AuthorizeError(
            "invalid_request",
            f"redirect_uri is longer than {_MAX_REDIRECT_URI_CHARS} characters",
        )


class _BodySizeLimit:
    """ASGI wrapper that answers 413 once a request body exceeds ``max_bytes``."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        too_large = PlainTextResponse("Request body too large", status_code=413)
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = self.max_bytes + 1
                if declared > self.max_bytes:
                    await too_large(scope, receive, send)
                    return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLargeError:
            await too_large(scope, receive, send)


class _BodyTooLargeError(Exception):
    pass


class _ExpiringClientStore(PydanticAdapter[ProxyDCRClient]):
    """Client store whose records get the unused-client lifetime by default."""

    async def put(
        self,
        key: str,
        value: ProxyDCRClient,
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        await super().put(
            key,
            value,
            collection=collection,
            ttl=_UNUSED_CLIENT_TTL_SECONDS if ttl is None else ttl,
        )


def _now() -> float:
    return time.time()


class _TimedMemoryStore(MemoryStore):
    """MemoryStore whose expired entries actually leave memory.

    The upstream collection compares Unix expiry times with
    ``time.monotonic``, so expired entries are never evicted, only hidden.
    """

    async def _setup_collection(self, *, collection: str) -> None:
        if collection in self._cache:
            return
        collection_cache = MemoryCollection(max_entries=self.max_entries_per_collection)
        collection_cache._cache = TLRUCache(
            maxsize=self.max_entries_per_collection,
            ttu=_memory_cache_ttu,
            timer=lambda: _now(),
            getsizeof=_memory_cache_getsizeof,
        )
        self._cache[collection] = collection_cache


def _sweep_expired_files(directory: Path) -> int:
    """Delete long-expired records of FastMCP's file storage; return how many.

    Each record file carries its expiry in plain JSON beside the encrypted
    value. A file is deleted only an hour after its expiry: the store stops
    returning a record once it expires, so a renewal that read it just before
    then has long finished. Each file is read, checked and deleted with no
    ``await`` in between. Records without an expiry, unreadable files and
    collection info files are left alone; a file that cannot be deleted is
    logged and skipped, so cleanup never blocks start or registration.
    """
    cutoff = _now() - _EXPIRED_GRACE_SECONDS
    deleted = 0
    for path in directory.rglob("*.json"):
        if path.name.endswith("info.json"):
            continue
        try:
            expires_at = json.loads(path.read_text(encoding="utf-8")).get("expires_at")
            expired = (
                isinstance(expires_at, str)
                and datetime.fromisoformat(expires_at).timestamp() <= cutoff
            )
        except (OSError, ValueError, AttributeError):
            continue
        if not expired:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not delete expired OAuth record %s: %s", path, e)
            continue
        deleted += 1
    return deleted


def _callback_uri(base_url: str, redirect_path: str) -> str:
    """Build the proxy's callback URI from its public base URL and route."""
    parsed = urlsplit(base_url)
    callback_path = f"{parsed.path.rstrip('/')}/{redirect_path.lstrip('/')}"
    return urlunsplit((parsed.scheme, parsed.netloc, callback_path, "", ""))


class HardenedOAuthProxy(OAuthProxy):
    """OAuthProxy with stricter DCR controls for grants and scopes."""

    def __init__(
        self,
        *,
        base_url: AnyHttpUrl | str,
        redirect_path: str | None = None,
        allowed_grant_types: list[str] | None = None,
        forced_scopes: list[str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(base_url=base_url, redirect_path=redirect_path, **kwargs)
        self._bound_storage(default_storage=kwargs.get("client_storage") is None)
        self._allowed_grant_types = _normalize_list(allowed_grant_types)
        self._forced_scopes = _normalize_list(forced_scopes)
        self._proxy_callback_target = _redirect_target(
            _callback_uri(str(self.base_url), self._redirect_path)
        )

    async def load_access_token(self, token: str) -> AccessToken | None:  # type: ignore[override]
        """Validate a FastMCP token and name its user by the OAuth grant.

        The token verifier sees only the upstream access token, which changes
        on every refresh. FastMCP keeps one upstream token record per grant
        across refreshes, so its id names the user: the MCP SDK binds
        transport sessions to it, and a refreshed token keeps its sessions.

        If the grant cannot be read again, the token is rejected. Keeping the
        verifier's token-based subject would name a different user than the
        grant, so the request could not reach the sessions it owns and the
        identity kind would depend on a storage lookup.
        """
        access = await super().load_access_token(token)
        if access is None:
            return None
        try:
            jti = self.jwt_issuer.verify_token(token)["jti"]
            mapping = await self._jti_mapping_store.get(key=jti)
        except Exception:  # noqa: BLE001 - any failure rejects the token
            logger.warning("OAuth grant lookup failed; rejecting token")
            return None
        if mapping is None:
            logger.info("OAuth grant no longer exists; rejecting token")
            return None
        return access.model_copy(
            update={"subject": principal_subject(f"grant:{mapping.upstream_token_id}")}
        )

    def _bound_storage(self, *, default_storage: bool) -> None:
        """Bound what unauthenticated OAuth requests leave in storage.

        Each client record has its own lifetime: short until it completes an
        authorization, then a long one that each exchange renews. Records are
        written one at a time, so instances sharing a store do not overwrite
        each other. FastMCP's default file storage never deletes expired
        files, so expired records are deleted at start and on registration;
        pending logins and authorization codes are kept in a bounded in-memory
        store instead. A custom storage backend keeps them and its own expiry.
        """
        for name in (
            "_client_storage",
            "_client_store",
            "_transaction_store",
            "_code_store",
        ):
            if not hasattr(self, name):
                msg = (
                    f"FastMCP OAuthProxy has no {name}; the OAuth proxy storage "
                    "bounds cannot be applied with this FastMCP version."
                )
                raise RuntimeError(msg)
        self._client_store = _ExpiringClientStore(
            key_value=self._client_storage,
            pydantic_model=ProxyDCRClient,
            default_collection="mcp-oauth-proxy-clients",
            raise_on_validation_error=True,
        )
        self._expired_files_dir: Path | None = None
        self._next_sweep = 0.0
        if not default_storage:
            return
        file_store = getattr(self._client_storage, "key_value", None)
        data_dir = getattr(file_store, "_data_directory", None)
        if data_dir is None:
            msg = (
                "FastMCP OAuthProxy default storage has no data directory; expired "
                "OAuth records cannot be cleaned up with this FastMCP version."
            )
            raise RuntimeError(msg)
        self._expired_files_dir = Path(str(data_dir))
        self._sweep_expired()
        pending = _TimedMemoryStore(
            max_entries_per_collection=_MAX_PENDING_LOGIN_RECORDS
        )
        self._transaction_store = PydanticAdapter[OAuthTransaction](
            key_value=pending,
            pydantic_model=OAuthTransaction,
            default_collection="mcp-oauth-transactions",
            raise_on_validation_error=True,
        )
        self._code_store = PydanticAdapter[ClientCode](
            key_value=pending,
            pydantic_model=ClientCode,
            default_collection="mcp-authorization-codes",
            raise_on_validation_error=True,
        )

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        """Return FastMCP's OAuth routes with a body limit on /authorize."""
        routes = super().get_routes(mcp_path)
        for route in routes:
            if isinstance(route, Route) and route.path == "/authorize":
                route.app = _BodySizeLimit(route.app, _MAX_AUTHORIZE_BODY_BYTES)
        return routes

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        _check_registration_size(client_info)
        for redirect_uri in client_info.redirect_uris or []:
            if _redirect_target(str(redirect_uri)) == self._proxy_callback_target:
                raise RegistrationError(
                    "invalid_redirect_uri",
                    "DCR redirect_uri must not target the OAuth proxy callback",
                )

        updates: dict[str, object] = {"response_types": ["code"]}

        if self._allowed_grant_types is not None:
            requested = list(client_info.grant_types or [])
            filtered = [gt for gt in requested if gt in self._allowed_grant_types]
            if requested and set(requested) - set(filtered):
                logger.warning(
                    "DCR requested unsupported grant types %s; enforcing %s",
                    sorted(set(requested) - set(filtered)),
                    self._allowed_grant_types,
                )
            if not filtered:
                filtered = list(self._allowed_grant_types)
            updates["grant_types"] = filtered

        if self._forced_scopes is not None:
            forced_scope = " ".join(self._forced_scopes).strip()
            updates["scope"] = forced_scope or None
            if client_info.scope and client_info.scope != forced_scope:
                logger.warning(
                    "DCR requested scope '%s'; enforcing '%s'",
                    client_info.scope,
                    forced_scope,
                )

        client_info = client_info.model_copy(update=updates)
        await super().register_client(client_info)
        self._sweep_expired()

    def _sweep_expired(self) -> None:
        """Delete expired default-storage files, at most once an hour."""
        if self._expired_files_dir is None or _now() < self._next_sweep:
            return
        self._next_sweep = _now() + _EXPIRED_SWEEP_INTERVAL_SECONDS
        deleted = _sweep_expired_files(self._expired_files_dir)
        if deleted:
            logger.info("Deleted %d expired OAuth proxy records", deleted)

    async def _renew_client(self, client_id: str) -> None:
        """Give a client the long lifetime after a completed exchange."""
        stored = await self._client_store.get(key=client_id)
        if stored is not None:
            await self._client_store.put(
                key=client_id, value=stored, ttl=_USED_CLIENT_TTL_SECONDS
            )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        token = await super().exchange_authorization_code(client, authorization_code)
        await self._renew_client(str(client.client_id))
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        token = await super().exchange_refresh_token(client, refresh_token, scopes)
        await self._renew_client(str(client.client_id))
        return token

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Request the forced scopes from the upstream IdP on every authorization.

        A client may request a subset of its registered scopes, for example
        one that registered before the operator extended the scope list.
        Without this override the upstream IdP issues a token that lacks the
        missing scopes, and the tools that need them fail.

        Oversized fields are rejected first: the transaction that stores them
        is created before any authentication.
        """
        _check_authorize_size(params)
        if self._forced_scopes is not None:
            requested = params.scopes or []
            if set(requested) != set(self._forced_scopes):
                logger.info(
                    "Authorize requested scope %s; enforcing %s",
                    requested,
                    self._forced_scopes,
                )
            params = params.model_copy(update={"scopes": list(self._forced_scopes)})
        return await super().authorize(client, params)


__all__ = ["HardenedOAuthProxy", "parse_env_list"]
