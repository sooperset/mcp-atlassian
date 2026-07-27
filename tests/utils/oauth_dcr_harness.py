"""Hermetic OAuth DCR client helpers for OAuth proxy integration tests."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import socket
import ssl
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import truststore
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route
from starlette.types import ASGIApp


def build_pkce_verifier() -> tuple[str, str]:
    """Return a deterministic RFC 7636 S256 verifier and challenge pair."""
    verifier = "oauth-dcr-harness-verifier-0123456789-abcdefghijklmnopqrstuvwxyz"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_client_ssl_context(ca_path: Path) -> ssl.SSLContext:
    """Create a client context that trusts one disposable test CA."""
    return ssl.create_default_context(cafile=str(ca_path))


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _write_loopback_certificate(directory: Path) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    ca_subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "mcp-atlassian test CA")]
    )
    ca_subject_key_identifier = x509.SubjectKeyIdentifier.from_public_key(
        ca_key.public_key()
    )
    ca_certificate = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(ca_subject_key_identifier, critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf_subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "mcp-atlassian-test.local")]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(leaf_subject)
        .issuer_name(ca_subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(
                ca_subject_key_identifier
            ),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = directory / "ca.pem"
    certificate_path = directory / "certificate.pem"
    key_path = directory / "key.pem"
    ca_path.write_bytes(ca_certificate.public_bytes(serialization.Encoding.PEM))
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return ca_path, certificate_path, key_path


class LocalTLSServer:
    """Run a disposable ASGI application with a self-signed loopback certificate."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self.port = _reserve_loopback_port()
        (
            self.ca_certificate_path,
            self.certificate_path,
            self._key_path,
        ) = _write_loopback_certificate(directory)
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def base_url(self) -> str:
        """Return the HTTPS loopback base URL reserved for this server."""
        return f"https://127.0.0.1:{self.port}"

    async def start(self, app: ASGIApp) -> None:
        """Start ``app`` and wait until Uvicorn has bound its socket."""
        truststore.extract_from_ssl()
        try:
            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=self.port,
                log_level="error",
                ssl_certfile=str(self.certificate_path),
                ssl_keyfile=str(self._key_path),
            )
            self._server = uvicorn.Server(config)
            self._task = asyncio.create_task(self._server.serve())
            for _ in range(100):
                if self._server.started:
                    return
                await asyncio.sleep(0.01)
            self._server.should_exit = True
            await self._task
            raise RuntimeError("Timed out starting local TLS test server")
        finally:
            truststore.inject_into_ssl()

    async def stop(self) -> None:
        """Stop the local server if it was started."""
        if self._server is None or self._task is None:
            return
        self._server.should_exit = True
        await self._task
        self._server = None
        self._task = None


@dataclass
class FakeUpstreamIssuer:
    """Record and satisfy the OAuth proxy's upstream OAuth requests."""

    authorization_code: str = "upstream-authorization-code"
    access_token: str = "upstream-access-token"
    refresh_token: str = "upstream-refresh-token"
    authorize_requests: list[dict[str, str]] = field(default_factory=list)
    token_requests: list[dict[str, str]] = field(default_factory=list)

    def app(self) -> Starlette:
        """Build the fake OAuth authorization and token endpoints."""
        return Starlette(
            routes=[
                Route("/authorize", self.authorize, methods=["GET"]),
                Route("/token", self.token, methods=["POST"]),
            ]
        )

    async def authorize(self, request: Request) -> RedirectResponse:
        """Redirect the simulated browser back to the OAuth proxy callback."""
        request_data = dict(request.query_params)
        self.authorize_requests.append(request_data)
        redirect_uri = request_data["redirect_uri"]
        query = urlencode(
            {"code": self.authorization_code, "state": request_data["state"]}
        )
        return RedirectResponse(f"{redirect_uri}?{query}", status_code=302)

    async def token(self, request: Request) -> JSONResponse:
        """Validate the proxy's authorization-code exchange and issue fake tokens."""
        form = await request.form()
        request_data = {key: str(value) for key, value in form.items()}
        self.token_requests.append(request_data)
        if request_data.get("code") != self.authorization_code:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        return JSONResponse(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )


class LocalTLSOAuthIssuer:
    """Serve a fake upstream issuer through a real disposable TLS socket."""

    def __init__(self, directory: Path, issuer: FakeUpstreamIssuer) -> None:
        self._issuer = issuer
        self.port = _reserve_loopback_port()
        (
            self.ca_certificate_path,
            certificate_path,
            key_path,
        ) = _write_loopback_certificate(directory)
        self._certificate_path = certificate_path
        self._key_path = key_path
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        """Return the issuer's loopback HTTPS base URL."""
        return f"https://127.0.0.1:{self.port}"

    async def start(self) -> None:
        """Start the fake issuer in a daemon thread."""
        issuer = self._issuer

        class OAuthIssuerHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/authorize":
                    self.send_error(404)
                    return
                query = {
                    key: values[0] for key, values in parse_qs(parsed.query).items()
                }
                issuer.authorize_requests.append(query)
                callback_query = urlencode(
                    {"code": issuer.authorization_code, "state": query["state"]}
                )
                self.send_response(302)
                self.send_header(
                    "Location", f"{query['redirect_uri']}?{callback_query}"
                )
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/token":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                form = {
                    key: values[0]
                    for key, values in parse_qs(
                        self.rfile.read(length).decode("utf-8")
                    ).items()
                }
                issuer.token_requests.append(form)
                if form.get("code") != issuer.authorization_code:
                    body = b'{"error":"invalid_grant"}'
                    self.send_response(400)
                else:
                    body = (
                        "{"
                        f'"access_token":"{issuer.access_token}",'
                        f'"refresh_token":"{issuer.refresh_token}",'
                        '"token_type":"Bearer","expires_in":3600'
                        "}"
                    ).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                """Suppress disposable issuer access logs during tests."""

        server = ThreadingHTTPServer(("127.0.0.1", self.port), OAuthIssuerHandler)
        truststore.extract_from_ssl()
        try:
            tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls_context.load_cert_chain(self._certificate_path, self._key_path)
            server.socket = tls_context.wrap_socket(server.socket, server_side=True)
        finally:
            truststore.inject_into_ssl()
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        await asyncio.sleep(0.01)

    async def stop(self) -> None:
        """Stop the issuer thread and release its loopback socket."""
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join)
        self._server = None
        self._thread = None


@dataclass(frozen=True)
class RegisteredClient:
    """DCR registration data needed for authorization and token exchange."""

    client_id: str
    client_secret: str | None
    redirect_uri: str


class OAuthDCRClientHarness:
    """Black-box MCP OAuth client for discovery, DCR, PKCE, and token exchange."""

    def __init__(self, client: httpx.AsyncClient, upstream_ca_path: Path) -> None:
        self._client = client
        self._upstream_ca_path = upstream_ca_path

    async def discover(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch protected-resource and authorization-server metadata."""
        protected_resource = await self._client.get(
            "/.well-known/oauth-protected-resource/mcp"
        )
        protected_resource.raise_for_status()
        authorization_server = await self._client.get(
            "/.well-known/oauth-authorization-server"
        )
        authorization_server.raise_for_status()
        return protected_resource.json(), authorization_server.json()

    async def register(self, redirect_uri: str) -> RegisteredClient:
        """Dynamically register a public client for the supplied callback URI."""
        response = await self._client.post(
            "/register",
            json={
                "client_name": "mcp-atlassian OAuth DCR harness",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )
        response.raise_for_status()
        registration = response.json()
        return RegisteredClient(
            client_id=registration["client_id"],
            client_secret=registration.get("client_secret"),
            redirect_uri=redirect_uri,
        )

    async def authorize_with_pkce(
        self, registered_client: RegisteredClient
    ) -> tuple[str, str]:
        """Simulate browser authorization and return proxy code plus verifier."""
        verifier, challenge = build_pkce_verifier()
        authorize_response = await self._client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": registered_client.client_id,
                "redirect_uri": registered_client.redirect_uri,
                "scope": "read:jira-work",
                "state": "harness-client-state",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            follow_redirects=False,
        )
        assert authorize_response.status_code in {302, 307}
        upstream_authorize_url = authorize_response.headers["location"]

        async with httpx.AsyncClient(
            verify=build_client_ssl_context(self._upstream_ca_path),
            follow_redirects=False,
            trust_env=False,
        ) as browser:
            try:
                upstream_response = await browser.get(upstream_authorize_url)
            except httpx.HTTPError as exc:
                message = f"Simulated browser could not reach {upstream_authorize_url}"
                raise AssertionError(message) from exc
        assert upstream_response.status_code in {302, 307}

        callback_response = await self._client.get(
            upstream_response.headers["location"], follow_redirects=False
        )
        assert callback_response.status_code in {302, 307}
        client_callback = urlparse(callback_response.headers["location"])
        callback_values = parse_qs(client_callback.query)
        return callback_values["code"][0], verifier

    async def exchange_code(
        self,
        registered_client: RegisteredClient,
        code: str,
        verifier: str,
    ) -> httpx.Response:
        """Submit the final client-facing authorization-code token exchange."""
        request_data = {
            "grant_type": "authorization_code",
            "client_id": registered_client.client_id,
            "code": code,
            "redirect_uri": registered_client.redirect_uri,
            "code_verifier": verifier,
        }
        if registered_client.client_secret:
            request_data["client_secret"] = registered_client.client_secret
        return await self._client.post("/token", data=request_data)


__all__ = [
    "FakeUpstreamIssuer",
    "LocalTLSServer",
    "LocalTLSOAuthIssuer",
    "OAuthDCRClientHarness",
    "RegisteredClient",
    "build_client_ssl_context",
    "build_pkce_verifier",
]
