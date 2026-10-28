import contextlib
import json
import os
import select
import signal
import subprocess
import sys
import time

import pytest

from mcp_atlassian.utils import lifecycle


def _build_probe_payload() -> str:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "homebrew-probe", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    return "\n".join(json.dumps(message) for message in messages) + "\n"


def test_stdio_homebrew_probe_exits_after_stdin_close() -> None:
    env = os.environ.copy()
    env.update(
        {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "user@example.com",
            "JIRA_API_TOKEN": "x",
        }
    )

    result = subprocess.run(
        ["uv", "run", "--frozen", "mcp-atlassian"],
        input=_build_probe_payload(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        timeout=15,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"
    jsonrpc_lines = [
        line for line in combined_output.splitlines() if line.startswith('{"jsonrpc"')
    ]

    assert result.returncode == 0, combined_output[:1000]
    assert any('"id":1' in line for line in jsonrpc_lines), combined_output[:1000]
    # As of mcp-sdk 1.27, in-flight handlers are cancelled when the transport
    # closes. Since stdin reaches EOF immediately after the last message, the
    # tools/list response may be cancelled before reaching stdout. A clean exit
    # and initialize response are sufficient to verify shutdown behavior.


def _server_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "user@example.com",
            "JIRA_API_TOKEN": "x",
        }
    )
    return env


def _initialize(proc: subprocess.Popen[bytes]) -> None:
    """Send initialize and wait for the response, leaving stdin open."""
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(_build_probe_payload().splitlines()[0].encode() + b"\n")
    proc.stdin.flush()
    ready, _, _ = select.select([proc.stdout], [], [], 30)
    assert ready, "server did not answer initialize"
    assert b'"id":1' in proc.stdout.readline()


def _is_running(pid: int) -> bool:
    """True if pid is alive and not a zombie awaiting reaping by its new parent."""
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_stdio_exits_on_sigterm_while_stdin_open() -> None:
    with subprocess.Popen(
        [sys.executable, "-c", "from mcp_atlassian import main; main()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_server_env(),
    ) as proc:
        try:
            _initialize(proc)
            proc.send_signal(signal.SIGTERM)
            assert proc.wait(timeout=15) == 0
        finally:
            proc.kill()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX reparenting")
def test_stdio_exits_when_parent_exits_while_stdin_open() -> None:
    # The shell starts the server in the background; killing the shell once the
    # server is up reparents it while this test still holds the write end of
    # its stdin. stdin goes through fd 3 because sh points background jobs'
    # stdin at /dev/null.
    with subprocess.Popen(
        [
            "sh",
            "-c",
            'exec 3<&0; "$0" -c "from mcp_atlassian import main; main()" <&3 3<&- &'
            " echo $!; sleep 60",
            sys.executable,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_server_env(),
    ) as proc:
        assert proc.stdout is not None
        server_pid = int(proc.stdout.readline())
        try:
            _initialize(proc)
            proc.kill()
            proc.wait(timeout=15)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if not _is_running(server_pid):
                    break
                time.sleep(0.5)
            else:
                pytest.fail("server still running after its parent exited")
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.kill(server_pid, signal.SIGKILL)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_stdio_sigterm_exit_is_bounded_when_stdout_is_blocked() -> None:
    # Pre-fill stdout and never drain it, so writing the initialize response
    # blocks and graceful shutdown cannot finish on its own.
    out_r, out_w = os.pipe()
    os.set_blocking(out_w, False)
    with contextlib.suppress(BlockingIOError):
        while True:
            os.write(out_w, b"x" * 4096)
    os.set_blocking(out_w, True)
    with subprocess.Popen(
        [sys.executable, "-c", "from mcp_atlassian import main; main()"],
        stdin=subprocess.PIPE,
        stdout=out_w,
        stderr=subprocess.PIPE,
        env={**_server_env(), "MCP_VERBOSE": "true"},
    ) as proc:
        os.close(out_w)
        assert proc.stdin is not None and proc.stderr is not None
        try:
            started = b""
            while b"Starting MCP server" not in started:
                ready, _, _ = select.select([proc.stderr], [], [], 30)
                assert ready, "server did not start"
                started += os.read(proc.stderr.fileno(), 4096)
            proc.stdin.write(_build_probe_payload().splitlines()[0].encode() + b"\n")
            proc.stdin.flush()
            time.sleep(1)
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=lifecycle.SHUTDOWN_DEADLINE_SECONDS + 10)
        finally:
            proc.kill()
            os.close(out_r)
