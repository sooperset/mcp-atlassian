import json
import os
import subprocess


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
        ["uv", "run", "mcp-atlassian"],
        input=_build_probe_payload(),
        capture_output=True,
        text=True,
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
    assert any('"id":2' in line and '"tools"' in line for line in jsonrpc_lines), (
        combined_output[:1000]
    )
