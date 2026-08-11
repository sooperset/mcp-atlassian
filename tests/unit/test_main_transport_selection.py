"""Unit tests for transport selection and execution."""

import asyncio
import shutil
import ssl
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_atlassian import _TLS_LISTENER_CIPHERS, _run_stdio_with_stdin_guard, main


class TestMainTransportSelection:
    """Test the main function's transport-specific execution logic."""

    @pytest.fixture
    def mock_server(self):
        """Create a mock server instance."""
        server = MagicMock()
        server.run_async = AsyncMock(return_value=None)
        return server

    @pytest.fixture
    def mock_asyncio_run(self):
        """Mock asyncio.run to capture what coroutine is executed."""
        with patch("asyncio.run") as mock_run:
            # Store the coroutine for inspection
            mock_run.side_effect = lambda coro: setattr(mock_run, "_called_with", coro)
            yield mock_run

    @pytest.mark.parametrize("transport", ["sse", "streamable-http"])
    def test_http_transports_use_direct_execution(
        self, mock_server, mock_asyncio_run, transport
    ):
        """Verify HTTP transports use direct execution without stdin monitoring.

        This is a regression test for issues #519 and #524.
        """
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch.dict("os.environ", {"TRANSPORT": transport}):
                with patch("sys.argv", ["mcp-atlassian"]):
                    try:
                        main()
                    except SystemExit:
                        pass

                    # Verify asyncio.run was called
                    assert mock_asyncio_run.called

                    # Get the coroutine info
                    called_coro = mock_asyncio_run._called_with
                    coro_repr = repr(called_coro)

                    assert "_run_stdio_with_stdin_guard" not in coro_repr
                    assert "run_async" in coro_repr or hasattr(called_coro, "cr_code")

    def test_stdio_transport_uses_stdin_guard(self, mock_server, mock_asyncio_run):
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                with patch("sys.argv", ["mcp-atlassian"]):
                    try:
                        main()
                    except SystemExit:
                        pass

                    assert mock_asyncio_run.called
                    called_coro = mock_asyncio_run._called_with
                    coro_repr = repr(called_coro)
                    assert "_run_stdio_with_stdin_guard" in coro_repr

    @pytest.mark.parametrize("stateless", ["False", "True"])
    def test_stateless_set(self, mock_asyncio_run, stateless):
        """Verify that stateless_http is passed to run_async via run_kwargs."""
        from mcp_atlassian.servers import main_mcp

        with patch.object(
            main_mcp, "run_async", new_callable=AsyncMock
        ) as mock_run_async:
            with patch.dict(
                "os.environ",
                {"STATELESS": stateless, "TRANSPORT": "streamable-http"},
            ):
                with patch("sys.argv", ["mcp-atlassian"]):
                    try:
                        main()
                    except SystemExit:
                        pass

                    # Verify run_async was called
                    assert mock_run_async.called

                    # Verify stateless_http was passed correctly
                    call_kwargs = mock_run_async.call_args[1]
                    desired = stateless.lower() == "true"
                    assert call_kwargs["stateless_http"] == desired

    @pytest.mark.parametrize("transport", ["stdio", "sse"])
    def test_stateless_rejects_non_streamable_http(self, mock_asyncio_run, transport):
        """Verify that --stateless flag errors when used with non-streamable-http transport."""
        with patch.dict("os.environ", {"STATELESS": "true", "TRANSPORT": transport}):
            with patch("sys.argv", ["mcp-atlassian"]):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Should exit with code 1 (error)
                assert exc_info.value.code == 1

    def test_cli_overrides_env_transport(self, mock_server, mock_asyncio_run):
        """Test that CLI transport argument overrides environment variable."""
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch.dict("os.environ", {"TRANSPORT": "sse"}):
                # Simulate CLI args with --transport stdio
                with patch("sys.argv", ["mcp-atlassian", "--transport", "stdio"]):
                    try:
                        main()
                    except SystemExit:
                        pass

                    called_coro = mock_asyncio_run._called_with
                    coro_repr = repr(called_coro)
                    assert "_run_stdio_with_stdin_guard" in coro_repr

    @pytest.mark.asyncio
    async def test_stdio_guard_cancels_server_when_parent_exits(self):
        server_started = asyncio.Event()
        server_cancelled = asyncio.Event()

        async def fake_run_async(**kwargs):
            del kwargs
            server_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                server_cancelled.set()
                raise

        async def fake_watch_parent(_stop_event) -> None:
            await server_started.wait()

        with patch(
            "mcp_atlassian.servers.main_mcp.run_async", side_effect=fake_run_async
        ):
            with patch(
                "mcp_atlassian._watch_parent_exit", side_effect=fake_watch_parent
            ):
                await _run_stdio_with_stdin_guard({"transport": "stdio"})

        assert server_cancelled.is_set()

    def test_signal_handlers_always_setup(self, mock_server):
        """Test that signal handlers are set up regardless of transport."""
        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch("asyncio.run"):
                # Patch where it's imported in the main module
                with patch("mcp_atlassian.setup_signal_handlers") as mock_setup:
                    with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                        with patch("sys.argv", ["mcp-atlassian"]):
                            try:
                                main()
                            except SystemExit:
                                pass

                            # Signal handlers should always be set up
                            mock_setup.assert_called_once()

    def test_error_handling_preserved(self, mock_server):
        """Test that error handling works correctly for all transports."""
        # Make the server's run_async raise an exception when awaited
        error = RuntimeError("Server error")

        async def failing_run_async(**kwargs):
            raise error

        mock_server.run_async = failing_run_async

        with patch("mcp_atlassian.servers.main.AtlassianMCP", return_value=mock_server):
            with patch("asyncio.run") as mock_run:
                # Simulate the exception propagating through asyncio.run
                mock_run.side_effect = error

                with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        # The main function logs the error and exits with code 1
                        with patch("sys.exit") as mock_exit:
                            main()
                            # Verify error was handled - sys.exit called with 1 for error
                            # and then with 0 in the finally block
                            assert mock_exit.call_count == 2
                            assert mock_exit.call_args_list[0][0][0] == 1  # Error exit
                            assert (
                                mock_exit.call_args_list[1][0][0] == 0
                            )  # Finally exit


class TestServerTLSConfiguration:
    """The server's own HTTPS listener (--ssl-certfile / --ssl-keyfile)."""

    @pytest.fixture(autouse=True)
    def _no_truststore_injection(self):
        """Pin the truststore-injection flag to a known False for every test,
        regardless of how the test process was launched. Tests for the guard
        itself re-patch the flag to True explicitly."""
        with patch("mcp_atlassian._TRUSTSTORE_INJECTED", new=False):
            yield

    @pytest.fixture
    def preflight_ok(self):
        """Bypass the real cert/key load for tests that use dummy PEM files;
        yields the mock so tests can assert the preflight path executed."""
        with patch("mcp_atlassian._preflight_tls_certificates") as mock_preflight:
            yield mock_preflight

    @staticmethod
    def _make_pair(tmp_path, prefix=""):
        """Create dummy cert/key files (not loadable PEM; tests that reach the
        preflight must either patch it via preflight_ok or expect the abort)."""
        cert = tmp_path / f"{prefix}server-cert.pem"
        key = tmp_path / f"{prefix}server-key.pem"
        cert.write_text("cert")
        key.write_text("key")
        return cert, key

    @pytest.fixture
    def cert_key(self, tmp_path):
        return self._make_pair(tmp_path)

    @staticmethod
    def _run_main():
        try:
            main()
        except SystemExit:
            pass

    @pytest.mark.parametrize("transport", ["sse", "streamable-http"])
    def test_tls_env_forwards_uvicorn_config(self, cert_key, preflight_ok, transport):
        """Both certs via env -> uvicorn_config reaches run_async, for both
        HTTP transports, with the cipher pin included."""
        from mcp_atlassian.servers import main_mcp

        cert, key = cert_key
        with patch.object(
            main_mcp, "run_async", new_callable=AsyncMock
        ) as mock_run_async:
            with patch.dict(
                "os.environ",
                {
                    "TRANSPORT": transport,
                    "MCP_SSL_CERTFILE": str(cert),
                    "MCP_SSL_KEYFILE": str(key),
                },
            ):
                with patch("sys.argv", ["mcp-atlassian"]):
                    self._run_main()

        assert preflight_ok.called
        assert mock_run_async.called
        assert mock_run_async.call_args[1]["uvicorn_config"] == {
            "ssl_certfile": str(cert),
            "ssl_keyfile": str(key),
            "ssl_ciphers": _TLS_LISTENER_CIPHERS,
        }

    def test_tls_cli_overrides_env(self, tmp_path, preflight_ok):
        """CLI --ssl-* wins over a valid env pair and forwards the CLI paths."""
        from mcp_atlassian.servers import main_mcp

        cli_cert, cli_key = self._make_pair(tmp_path, "cli-")
        env_cert, env_key = self._make_pair(tmp_path, "env-")
        with patch.object(
            main_mcp, "run_async", new_callable=AsyncMock
        ) as mock_run_async:
            with patch.dict(
                "os.environ",
                {
                    "TRANSPORT": "streamable-http",
                    "MCP_SSL_CERTFILE": str(env_cert),
                    "MCP_SSL_KEYFILE": str(env_key),
                },
            ):
                with patch(
                    "sys.argv",
                    [
                        "mcp-atlassian",
                        "--ssl-certfile",
                        str(cli_cert),
                        "--ssl-keyfile",
                        str(cli_key),
                    ],
                ):
                    self._run_main()

        assert mock_run_async.called
        assert mock_run_async.call_args[1]["uvicorn_config"] == {
            "ssl_certfile": str(cli_cert),
            "ssl_keyfile": str(cli_key),
            "ssl_ciphers": _TLS_LISTENER_CIPHERS,
        }

    def test_tls_cli_cert_with_env_key(self, tmp_path, preflight_ok):
        """A cross-source pair (cert via CLI, key via env) resolves and
        forwards both — the two paths resolve independently."""
        from mcp_atlassian.servers import main_mcp

        cli_cert, _ = self._make_pair(tmp_path, "cli-")
        _, env_key = self._make_pair(tmp_path, "env-")
        with patch.object(
            main_mcp, "run_async", new_callable=AsyncMock
        ) as mock_run_async:
            with patch.dict(
                "os.environ",
                {
                    "TRANSPORT": "streamable-http",
                    "MCP_SSL_KEYFILE": str(env_key),
                },
            ):
                with patch(
                    "sys.argv",
                    ["mcp-atlassian", "--ssl-certfile", str(cli_cert)],
                ):
                    self._run_main()

        assert mock_run_async.called
        assert mock_run_async.call_args[1]["uvicorn_config"] == {
            "ssl_certfile": str(cli_cert),
            "ssl_keyfile": str(env_key),
            "ssl_ciphers": _TLS_LISTENER_CIPHERS,
        }

    @pytest.mark.parametrize("transport", ["sse", "streamable-http"])
    def test_no_tls_omits_uvicorn_config(self, transport, monkeypatch):
        """Without TLS configured, run_kwargs carries no uvicorn_config."""
        from mcp_atlassian.servers import main_mcp

        monkeypatch.delenv("MCP_SSL_CERTFILE", raising=False)
        monkeypatch.delenv("MCP_SSL_KEYFILE", raising=False)
        with patch.object(
            main_mcp, "run_async", new_callable=AsyncMock
        ) as mock_run_async:
            with patch.dict("os.environ", {"TRANSPORT": transport}):
                with patch("sys.argv", ["mcp-atlassian"]):
                    self._run_main()

        assert mock_run_async.called
        assert "uvicorn_config" not in mock_run_async.call_args[1]

    @pytest.mark.parametrize("provided", ["cert", "key"])
    def test_half_configured_tls_aborts(self, cert_key, provided, monkeypatch):
        """Setting only one of cert/key exits with code 1 via the
        both-or-neither guard — before the server starts, not via some later
        uvicorn failure."""
        from mcp_atlassian.servers import main_mcp

        monkeypatch.delenv("MCP_SSL_CERTFILE", raising=False)
        monkeypatch.delenv("MCP_SSL_KEYFILE", raising=False)
        cert, key = cert_key
        env = {"TRANSPORT": "streamable-http"}
        if provided == "cert":
            env["MCP_SSL_CERTFILE"] = str(cert)
        else:
            env["MCP_SSL_KEYFILE"] = str(key)

        mock_logger = MagicMock()
        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch.object(
                main_mcp, "run_async", new_callable=AsyncMock
            ) as mock_run_async:
                with patch.dict("os.environ", env):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        assert not mock_run_async.called  # aborted before the server started
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "must be provided together" in errors

    @pytest.mark.parametrize("missing", ["cert", "key"])
    def test_env_path_not_found_aborts(self, tmp_path, missing):
        """A cert/key path from env that isn't a file exits with code 1 via the
        existence guard before the server starts (env paths bypass click's
        existence check)."""
        from mcp_atlassian.servers import main_mcp

        cert, key = self._make_pair(tmp_path)
        env = {"TRANSPORT": "streamable-http"}
        if missing == "cert":
            env["MCP_SSL_CERTFILE"] = str(tmp_path / "nope-cert.pem")
            env["MCP_SSL_KEYFILE"] = str(key)
        else:
            env["MCP_SSL_CERTFILE"] = str(cert)
            env["MCP_SSL_KEYFILE"] = str(tmp_path / "nope-key.pem")

        mock_logger = MagicMock()
        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch.object(
                main_mcp, "run_async", new_callable=AsyncMock
            ) as mock_run_async:
                with patch.dict("os.environ", env):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        assert not mock_run_async.called
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "not found" in errors

    def test_tls_under_stdio_warns_and_skips_uvicorn_config(self, cert_key):
        """Under stdio the certs are ignored (no HTTP listener) but the
        operator is warned rather than silently served plaintext, and
        run_kwargs never carries uvicorn_config."""
        cert, key = cert_key
        mock_logger = MagicMock()
        captured_kwargs: dict = {}

        async def _capture_guard(run_kwargs):
            captured_kwargs.update(run_kwargs)

        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch(
                "mcp_atlassian._run_stdio_with_stdin_guard",
                side_effect=_capture_guard,
            ) as mock_guard:
                with patch.dict(
                    "os.environ",
                    {
                        "TRANSPORT": "stdio",
                        "MCP_SSL_CERTFILE": str(cert),
                        "MCP_SSL_KEYFILE": str(key),
                    },
                ):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        # click always exits in standalone mode; a clean run
                        # exits 0, an abort would exit 1 and fail here.
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code in (0, None)
        assert mock_guard.called  # the stdio run path actually executed
        assert captured_kwargs.get("transport") == "stdio"
        warnings = " ".join(
            str(call.args[0]) for call in mock_logger.warning.call_args_list
        )
        assert "ignored" in warnings  # the cert-configured-under-stdio warning
        assert "uvicorn_config" not in captured_kwargs

    @pytest.mark.parametrize("transport", ["sse", "streamable-http"])
    def test_tls_with_truststore_injection_aborts(self, cert_key, transport):
        """With the OS trust store injected, enabling the HTTPS listener exits
        with code 1 before the server starts: truststore's client-side-only
        SSLContext would reject every inbound TLS handshake."""
        from mcp_atlassian.servers import main_mcp

        cert, key = cert_key
        mock_logger = MagicMock()
        with patch("mcp_atlassian._TRUSTSTORE_INJECTED", new=True):
            with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
                with patch.object(
                    main_mcp, "run_async", new_callable=AsyncMock
                ) as mock_run_async:
                    with patch.dict(
                        "os.environ",
                        {
                            "TRANSPORT": transport,
                            "MCP_SSL_CERTFILE": str(cert),
                            "MCP_SSL_KEYFILE": str(key),
                        },
                    ):
                        with patch("sys.argv", ["mcp-atlassian"]):
                            with pytest.raises(SystemExit) as exc_info:
                                main()

        assert exc_info.value.code == 1
        assert not mock_run_async.called
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE" in errors

    def test_tls_under_stdio_with_truststore_injection_does_not_abort(self, cert_key):
        """stdio ignores the TLS options, so the truststore guard must not
        trip: there is no HTTPS listener for the injection to break."""
        cert, key = cert_key
        mock_logger = MagicMock()

        async def _noop_guard(run_kwargs):
            return None

        with patch("mcp_atlassian._TRUSTSTORE_INJECTED", new=True):
            with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
                with patch(
                    "mcp_atlassian._run_stdio_with_stdin_guard",
                    side_effect=_noop_guard,
                ) as mock_guard:
                    with patch.dict(
                        "os.environ",
                        {
                            "TRANSPORT": "stdio",
                            "MCP_SSL_CERTFILE": str(cert),
                            "MCP_SSL_KEYFILE": str(key),
                        },
                    ):
                        with patch("sys.argv", ["mcp-atlassian"]):
                            # A clean run exits 0; the guard tripping would
                            # exit 1 and fail the assertion below.
                            with pytest.raises(SystemExit) as exc_info:
                                main()

        assert exc_info.value.code in (0, None)
        assert mock_guard.called  # the stdio run path actually executed
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "MCP_ATLASSIAN_USE_SYSTEM_TRUSTSTORE" not in errors

    def test_stdio_cli_tls_warns(self, cert_key):
        """The stdio warning also fires when the certs arrive via CLI flags
        rather than env vars."""
        cert, key = cert_key
        mock_logger = MagicMock()

        async def _noop_guard(run_kwargs):
            return None

        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch(
                "mcp_atlassian._run_stdio_with_stdin_guard",
                side_effect=_noop_guard,
            ) as mock_guard:
                with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                    with patch(
                        "sys.argv",
                        [
                            "mcp-atlassian",
                            "--ssl-certfile",
                            str(cert),
                            "--ssl-keyfile",
                            str(key),
                        ],
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code in (0, None)
        assert mock_guard.called
        warnings = " ".join(
            str(call.args[0]) for call in mock_logger.warning.call_args_list
        )
        assert "ignored" in warnings

    @pytest.mark.parametrize("blank", ["cert", "key", "both"])
    def test_blank_tls_env_aborts(self, cert_key, blank):
        """A TLS env var that is set but blank is a configuration error (e.g.
        a template rendering an unset value as \"\"), not \"TLS off\": exit 1
        instead of silently serving plaintext."""
        from mcp_atlassian.servers import main_mcp

        cert, key = cert_key
        env = {"TRANSPORT": "streamable-http"}
        env["MCP_SSL_CERTFILE"] = "" if blank in ("cert", "both") else str(cert)
        env["MCP_SSL_KEYFILE"] = "" if blank in ("key", "both") else str(key)

        mock_logger = MagicMock()
        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch.object(
                main_mcp, "run_async", new_callable=AsyncMock
            ) as mock_run_async:
                with patch.dict("os.environ", env):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        assert not mock_run_async.called
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "set but empty" in errors

    def test_tls_preflight_rejects_unloadable_pair(self, cert_key):
        """A pair that exists but cannot be loaded (non-PEM content here;
        same path catches mismatched pairs and encrypted keys) exits with a
        clear error before the server starts."""
        from mcp_atlassian.servers import main_mcp

        cert, key = cert_key  # dummy text files: not loadable PEM
        mock_logger = MagicMock()
        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch.object(
                main_mcp, "run_async", new_callable=AsyncMock
            ) as mock_run_async:
                with patch.dict(
                    "os.environ",
                    {
                        "TRANSPORT": "streamable-http",
                        "MCP_SSL_CERTFILE": str(cert),
                        "MCP_SSL_KEYFILE": str(key),
                    },
                ):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        assert not mock_run_async.called
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "could not be loaded" in errors

    def test_tls_startup_log_uses_https_scheme(self, cert_key, preflight_ok):
        """The startup log line is the operator's confirmation TLS is active;
        pin the https:// scheme."""
        from mcp_atlassian.servers import main_mcp

        cert, key = cert_key
        mock_logger = MagicMock()
        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch.object(main_mcp, "run_async", new_callable=AsyncMock):
                with patch.dict(
                    "os.environ",
                    {
                        "TRANSPORT": "streamable-http",
                        "MCP_SSL_CERTFILE": str(cert),
                        "MCP_SSL_KEYFILE": str(key),
                    },
                ):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        self._run_main()

        infos = " ".join(str(call.args[0]) for call in mock_logger.info.call_args_list)
        assert "https://" in infos

    def test_truststore_detection_assumption_holds(self):
        """The guard detects injection via ssl.SSLContext.__module__; pin the
        truststore layout that detection depends on, so a relocation fails
        loudly here rather than silently disabling the guard."""
        truststore = pytest.importorskip("truststore")
        assert truststore.SSLContext.__module__.startswith("truststore")

    def test_cli_pair_overrides_blank_env(self, tmp_path, preflight_ok):
        """A complete CLI pair wins over blank env vars — CLI-over-env
        precedence holds; the blank-env abort applies only when the env value
        is the selected source."""
        from mcp_atlassian.servers import main_mcp

        cert, key = self._make_pair(tmp_path)
        with patch.object(
            main_mcp, "run_async", new_callable=AsyncMock
        ) as mock_run_async:
            with patch.dict(
                "os.environ",
                {
                    "TRANSPORT": "streamable-http",
                    "MCP_SSL_CERTFILE": "",
                    "MCP_SSL_KEYFILE": "",
                },
            ):
                with patch(
                    "sys.argv",
                    [
                        "mcp-atlassian",
                        "--ssl-certfile",
                        str(cert),
                        "--ssl-keyfile",
                        str(key),
                    ],
                ):
                    self._run_main()

        assert mock_run_async.called
        assert mock_run_async.call_args[1]["uvicorn_config"]["ssl_certfile"] == str(
            cert
        )

    def test_tls_under_stdio_skips_all_validation(self, tmp_path):
        """Under stdio the TLS options are ignored entirely: even values that
        would abort on an HTTP transport (missing files here) only warn."""
        mock_logger = MagicMock()

        async def _noop_guard(run_kwargs):
            return None

        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch(
                "mcp_atlassian._run_stdio_with_stdin_guard",
                side_effect=_noop_guard,
            ) as mock_guard:
                with patch.dict(
                    "os.environ",
                    {
                        "TRANSPORT": "stdio",
                        "MCP_SSL_CERTFILE": str(tmp_path / "missing-cert.pem"),
                        "MCP_SSL_KEYFILE": str(tmp_path / "missing-key.pem"),
                    },
                ):
                    with patch("sys.argv", ["mcp-atlassian"]):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code in (0, None)
        assert mock_guard.called
        warnings = " ".join(
            str(call.args[0]) for call in mock_logger.warning.call_args_list
        )
        assert "ignored" in warnings
        assert not mock_logger.error.called

    def test_tls_under_stdio_missing_cli_paths_ignored(self, tmp_path):
        """Missing CLI paths must also be ignorable under stdio — click does
        no existence check at parse time, so stdio starts with a warning."""
        mock_logger = MagicMock()

        async def _noop_guard(run_kwargs):
            return None

        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch(
                "mcp_atlassian._run_stdio_with_stdin_guard",
                side_effect=_noop_guard,
            ) as mock_guard:
                with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                    with patch(
                        "sys.argv",
                        [
                            "mcp-atlassian",
                            "--ssl-certfile",
                            str(tmp_path / "missing-cert.pem"),
                            "--ssl-keyfile",
                            str(tmp_path / "missing-key.pem"),
                        ],
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code in (0, None)
        assert mock_guard.called
        warnings = " ".join(
            str(call.args[0]) for call in mock_logger.warning.call_args_list
        )
        assert "ignored" in warnings

    def test_tls_under_stdio_directory_cli_paths_ignored(self, tmp_path):
        """Even directory values for the CLI flags must be ignorable under
        stdio — the options carry no click-level path validation at all."""
        mock_logger = MagicMock()

        async def _noop_guard(run_kwargs):
            return None

        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch(
                "mcp_atlassian._run_stdio_with_stdin_guard",
                side_effect=_noop_guard,
            ) as mock_guard:
                with patch.dict("os.environ", {"TRANSPORT": "stdio"}):
                    with patch(
                        "sys.argv",
                        [
                            "mcp-atlassian",
                            "--ssl-certfile",
                            str(tmp_path),
                            "--ssl-keyfile",
                            str(tmp_path),
                        ],
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code in (0, None)
        assert mock_guard.called
        warnings = " ".join(
            str(call.args[0]) for call in mock_logger.warning.call_args_list
        )
        assert "ignored" in warnings

    def test_missing_cli_path_aborts_on_http_transport(self, cert_key, tmp_path):
        """With click no longer existence-checking, a missing CLI path on an
        HTTP transport must still fail fast via the manual file check."""
        from mcp_atlassian.servers import main_mcp

        cert, _key = cert_key
        mock_logger = MagicMock()
        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch.object(
                main_mcp, "run_async", new_callable=AsyncMock
            ) as mock_run_async:
                with patch.dict("os.environ", {"TRANSPORT": "streamable-http"}):
                    with patch(
                        "sys.argv",
                        [
                            "mcp-atlassian",
                            "--ssl-certfile",
                            str(cert),
                            "--ssl-keyfile",
                            str(tmp_path / "missing-key.pem"),
                        ],
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        assert not mock_run_async.called
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "not found" in errors

    def test_blank_cli_tls_flag_aborts(self, cert_key):
        """A blank CLI value is a configuration error on HTTP transports, the
        same as a blank env var (click no longer rejects empty strings)."""
        from mcp_atlassian.servers import main_mcp

        _cert, key = cert_key
        mock_logger = MagicMock()
        with patch("mcp_atlassian.setup_logging", return_value=mock_logger):
            with patch.object(
                main_mcp, "run_async", new_callable=AsyncMock
            ) as mock_run_async:
                with patch.dict("os.environ", {"TRANSPORT": "streamable-http"}):
                    with patch(
                        "sys.argv",
                        [
                            "mcp-atlassian",
                            "--ssl-certfile",
                            "",
                            "--ssl-keyfile",
                            str(key),
                        ],
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code == 1
        assert not mock_run_async.called
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "set but empty" in errors


@pytest.fixture(scope="module")
def real_cert_pairs(tmp_path_factory):
    """Two real self-signed cert/key pairs, generated with the openssl binary
    (skipped where openssl is unavailable; present on the CI runners)."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl binary not available")
    directory = tmp_path_factory.mktemp("tls-real")
    pairs = []
    for name in ("a", "b"):
        cert = directory / f"{name}-cert.pem"
        key = directory / f"{name}-key.pem"
        subprocess.run(
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "1",
                "-nodes",
                "-subj",
                "/CN=localhost",
            ],
            check=True,
            capture_output=True,
        )
        pairs.append((cert, key))
    return pairs


@pytest.fixture
def stdlib_ssl():
    """Temporarily undo truststore injection so handshakes use stdlib SSL —
    matching a real TLS-serving process, where the startup guard requires the
    injection to be off."""
    try:
        import truststore
    except ImportError:
        yield
        return
    was_injected = ssl.SSLContext.__module__.startswith("truststore")
    if was_injected:
        truststore.extract_from_ssl()
    try:
        yield
    finally:
        if was_injected:
            truststore.inject_into_ssl()


class TestServerTLSRealCertificates:
    """Real-SSL coverage: the cipher pin resolves, a valid pair passes the
    preflight, and the listener context negotiates the intended protocols —
    without mocking the SSL layer."""

    def test_cipher_pin_is_a_valid_openssl_expression(self):
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).set_ciphers(_TLS_LISTENER_CIPHERS)

    def test_preflight_accepts_valid_pair(self, real_cert_pairs):
        from mcp_atlassian import _preflight_tls_certificates

        cert, key = real_cert_pairs[0]
        _preflight_tls_certificates(str(cert), str(key))  # must not exit

    def test_preflight_rejects_mismatched_pair(self, real_cert_pairs):
        from mcp_atlassian import _preflight_tls_certificates

        cert_a, _ = real_cert_pairs[0]
        _, key_b = real_cert_pairs[1]
        mock_logger = MagicMock()
        with patch("mcp_atlassian.logger", mock_logger):
            with pytest.raises(SystemExit) as exc_info:
                _preflight_tls_certificates(str(cert_a), str(key_b))
        assert exc_info.value.code == 1
        errors = " ".join(
            str(call.args[0]) for call in mock_logger.error.call_args_list
        )
        assert "could not be loaded" in errors

    @staticmethod
    def _server_context(cert, key):
        """Build the listener context the way uvicorn does, with the pin."""
        from uvicorn.config import create_ssl_context

        return create_ssl_context(
            certfile=str(cert),
            keyfile=str(key),
            password=None,
            ssl_version=ssl.PROTOCOL_TLS_SERVER,
            cert_reqs=ssl.CERT_NONE,
            ca_certs=None,
            ciphers=_TLS_LISTENER_CIPHERS,
        )

    @staticmethod
    def _client_context(minimum=None, maximum=None):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        if minimum is not None:
            ctx.minimum_version = minimum
        if maximum is not None:
            ctx.maximum_version = maximum
        return ctx

    @staticmethod
    def _handshake(server_ctx, client_ctx):
        """In-memory TLS handshake between the two contexts."""
        c_in, c_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        s_in, s_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        client = client_ctx.wrap_bio(c_in, c_out, server_hostname="localhost")
        server = server_ctx.wrap_bio(s_in, s_out, server_side=True)
        client_done = server_done = False
        for _ in range(10):
            if not client_done:
                try:
                    client.do_handshake()
                    client_done = True
                except ssl.SSLWantReadError:
                    pass
            s_in.write(c_out.read())
            if not server_done:
                try:
                    server.do_handshake()
                    server_done = True
                except ssl.SSLWantReadError:
                    pass
            c_in.write(s_out.read())
            if client_done and server_done:
                return client
        raise AssertionError("handshake did not complete")

    def test_tls13_negotiates(self, real_cert_pairs, stdlib_ssl):
        cert, key = real_cert_pairs[0]
        client = self._handshake(
            self._server_context(cert, key), self._client_context()
        )
        assert client.version() == "TLSv1.3"

    def test_tls12_negotiates_aead_suite(self, real_cert_pairs, stdlib_ssl):
        cert, key = real_cert_pairs[0]
        client = self._handshake(
            self._server_context(cert, key),
            self._client_context(
                minimum=ssl.TLSVersion.TLSv1_2, maximum=ssl.TLSVersion.TLSv1_2
            ),
        )
        assert client.version() == "TLSv1.2"
        cipher_name = client.cipher()[0]
        assert "GCM" in cipher_name or "CHACHA20" in cipher_name

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    @pytest.mark.parametrize("legacy", [ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1_1])
    def test_legacy_tls_is_refused_by_server(self, real_cert_pairs, stdlib_ssl, legacy):
        """A client genuinely offering TLS 1.0/1.1 must be refused by the
        SERVER. The handshake is driven step by step so the rejection is
        attributable: the test skips unless a non-empty ClientHello was
        actually produced and handed to the server, and the assertion is on
        the server side of the handshake — a client-side failure (restricted
        or FIPS builds) can therefore never pass as server rejection."""
        cert, key = real_cert_pairs[0]
        client_ctx = self._client_context(minimum=legacy, maximum=legacy)
        try:
            # Modern OpenSSL disables TLS < 1.2 at SECLEVEL >= 1.
            client_ctx.set_ciphers("DEFAULT@SECLEVEL=0")
        except ssl.SSLError as exc:
            pytest.skip(f"runtime cannot configure a legacy TLS client: {exc}")

        c_in, c_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        s_in, s_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        client = client_ctx.wrap_bio(c_in, c_out, server_hostname="localhost")
        server = self._server_context(cert, key).wrap_bio(s_in, s_out, server_side=True)
        try:
            client.do_handshake()
        except ssl.SSLWantReadError:
            pass  # normal: the ClientHello is written, awaiting the server
        except ssl.SSLError as exc:
            pytest.skip(f"runtime cannot offer legacy TLS client-side: {exc}")
        client_hello = c_out.read()
        if not client_hello:
            pytest.skip("no ClientHello produced; server rejection not provable")

        s_in.write(client_hello)
        with pytest.raises(ssl.SSLError) as exc_info:
            server.do_handshake()  # the server itself must refuse the offer
        # SSLWantRead/WriteError are SSLError subclasses that mean the server
        # ACCEPTED the hello and wants more I/O — that is the regression this
        # test exists to catch, not a pass.
        assert not isinstance(
            exc_info.value, ssl.SSLWantReadError | ssl.SSLWantWriteError
        ), "server continued the legacy handshake instead of rejecting it"
