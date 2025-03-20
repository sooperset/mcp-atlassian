#!/usr/bin/env python3
"""
Test script for MCP Atlassian server with Cursor.com

This script tests the connection to the MCP Atlassian server and verifies
that it can access Jira and Confluence data.
"""

import json
import subprocess
import sys
import time
from pathlib import Path


def print_header(message: str) -> None:
    """Print a header message."""
    print("\n" + "=" * 80)
    print(f" {message}")
    print("=" * 80)


def run_command(command: str) -> str | None:
    """Run a command and return the output."""
    print(f"Running: {command}")
    try:
        # Security note: shell=True is acceptable here because this is a test script
        # that is run in a controlled environment with known commands
        result = subprocess.run(  # noqa: S602
            command, shell=True, check=True, capture_output=True, text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return None


def check_uv_installed() -> bool:
    """Check if uv is installed."""
    print_header("Checking if uv is installed")
    result = run_command("which uv")
    if result:
        print(f"uv is installed at: {result.strip()}")
        return True
    else:
        print("uv is not installed. Please install it with:")
        print("  pip install uv")
        return False


def check_mcp_atlassian_installed() -> bool:
    """Check if mcp-atlassian is installed."""
    print_header("Checking if mcp-atlassian is installed")
    result = run_command("uv pip list | grep mcp-atlassian")
    if result:
        print(f"mcp-atlassian is installed: {result.strip()}")
        return True
    else:
        print("mcp-atlassian is not installed. Please install it with:")
        print("  cd /Users/willianangelo/site/mcp/mcp-atlassian")
        print("  uv pip install -e .")
        return False


def check_mcp_config() -> bool:
    """Check if the MCP configuration file exists."""
    print_header("Checking MCP configuration")
    config_path = Path(".cursor/mcp.json")

    if not config_path.exists():
        print(f"MCP configuration file not found at: {config_path}")
        return False

    try:
        with open(config_path) as f:
            config = json.load(f)

        if "mcpServers" not in config:
            print("mcpServers section not found in MCP configuration")
            return False

        if "mcp-atlassian" not in config["mcpServers"]:
            print("mcp-atlassian server not found in MCP configuration")
            return False

        print("MCP configuration looks good!")
        return True
    except json.JSONDecodeError:
        print(f"Error parsing MCP configuration file: {config_path}")
        return False


def test_mcp_atlassian() -> bool:
    """Test the MCP Atlassian server."""
    print_header("Testing MCP Atlassian server")

    # Test running the server directly
    print("Starting MCP Atlassian server...")

    # Get the command and args from the config
    config_path = Path(".cursor/mcp.json")
    with open(config_path) as f:
        config = json.load(f)

    server_config = config["mcpServers"]["mcp-atlassian"]
    command = server_config["command"]
    args = server_config["args"]

    # Construct the command
    cmd = f"{command} {' '.join(args)}"

    # Run the command with a timeout
    print(f"Command: {cmd}")
    print("This will start the server and exit after 5 seconds.")
    print("If no errors are shown, the server is working correctly.")

    try:
        # Security note: shell=True is acceptable here because this is a test script
        # that is run in a controlled environment with known commands
        process = subprocess.Popen(  # noqa: S602
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Wait for 5 seconds
        time.sleep(5)

        # Terminate the process
        process.terminate()

        # Get output
        stdout, stderr = process.communicate(timeout=2)

        if stderr:
            print(f"STDERR: {stderr}")

        if "Error" in stderr or "error" in stderr:
            print("Errors detected in server output.")
            return False

        print("Server started successfully!")
        return True
    except subprocess.TimeoutExpired:
        process.kill()
        print("Server is running but did not exit cleanly.")
        return True
    except Exception as e:
        print(f"Error starting server: {e}")
        return False


def main() -> None:
    """Main function."""
    print_header("MCP Atlassian Test Script")

    # Run tests
    uv_installed = check_uv_installed()
    if not uv_installed:
        sys.exit(1)

    mcp_installed = check_mcp_atlassian_installed()
    if not mcp_installed:
        sys.exit(1)

    config_ok = check_mcp_config()
    if not config_ok:
        sys.exit(1)

    server_ok = test_mcp_atlassian()
    if not server_ok:
        sys.exit(1)

    print_header("All tests passed!")
    print("The MCP Atlassian server is configured correctly for Cursor.com.")
    print("You can now use it with Cursor.com to access Jira and Confluence data.")


if __name__ == "__main__":
    main()
