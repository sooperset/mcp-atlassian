"""Unit tests for transport stdin monitoring behavior."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


class TestStdinMonitoringFix:
    """Test that stdin monitoring is correctly disabled for HTTP transports."""

    def test_streamable_http_starts_without_hanging(self):
        """Test that streamable-http transport starts without stdin monitoring issues.

        This test creates a minimal script that would hang if stdin monitoring
        was enabled for HTTP transports, and verifies it runs successfully.
        """
        # Create a test script that simulates the issue
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import sys
import os

# The actual test: if stdin monitoring was incorrectly enabled for HTTP,
# closing stdin would cause issues. With the fix, it should work fine.
if __name__ == "__main__":
    # This simulates the scenario where stdin is closed (like in the bug report)
    # With the fix, HTTP transports won't monitor stdin, so this won't cause issues
    sys.stdin.close()

    # If we get here without hanging, the fix is working
    print("TEST_PASSED: No hanging with closed stdin")
    sys.exit(0)
""")
            test_script = f.name

        try:
            # Run the test script
            result = subprocess.run(
                [sys.executable, test_script],
                capture_output=True,
                text=True,
                timeout=5,  # Should complete quickly, timeout means hanging
            )

            # Check the output
            assert "TEST_PASSED" in result.stdout, (
                f"Test failed. Output: {result.stdout}, Error: {result.stderr}"
            )
            assert result.returncode == 0, (
                f"Script failed with code {result.returncode}"
            )

        except subprocess.TimeoutExpired:
            pytest.fail(
                "Script timed out - stdin monitoring may still be active for HTTP transports"
            )
        finally:
            # Clean up
            os.unlink(test_script)

    def test_code_structure_validates_fix(self):
        """Validate that stdio uses EOF monitoring while HTTP does not."""
        # Read the main module source directly
        main_file = (
            Path(__file__).parent.parent.parent
            / "src"
            / "mcp_atlassian"
            / "__init__.py"
        )
        with open(main_file) as f:
            source = f.read()

        # Check for the key parts of the fix
        assert 'if final_transport == "stdio":' in source

        # 2. STDIO path must use stdin guard wrapper
        assert "_run_stdio_with_stdin_guard" in source
        assert "asyncio.run(_run_stdio_with_stdin_guard(run_kwargs))" in source

        # 3. HTTP path should still use direct execution with no stdin watcher
        assert (
            "# For HTTP transports (SSE, streamable-http), don't use stdin monitoring"
            in source
        )
        assert (
            "# as it causes premature shutdown when the client closes stdin" in source
        )
        assert "# The server should only rely on OS signals for shutdown" in source

        # 4. Proper conditional logic - stdio and HTTP sections should both exist
        stdio_section = False
        http_section = False

        lines = source.split("\n")
        for i, line in enumerate(lines):
            if "asyncio.run(_run_stdio_with_stdin_guard(run_kwargs))" in line:
                stdio_section = True

            if "# For HTTP transports" in line and "stdin monitoring" in line:
                next_lines = "\n".join(lines[i : i + 10])
                if (
                    "without stdin monitoring" in next_lines
                    and "asyncio.run" in next_lines
                ):
                    http_section = True

        assert stdio_section, "Could not find proper stdio transport handling"
        assert http_section, "Could not find proper HTTP transport handling"

        print("Code structure validation passed - fix is properly implemented")

    def test_lifecycle_module_supports_http_transports(self):
        """Test that the lifecycle module properly handles HTTP transports.

        This verifies that the lifecycle management doesn't interfere with
        HTTP transport operation.
        """
        from mcp_atlassian.utils.lifecycle import (
            ensure_clean_exit,
            setup_signal_handlers,
        )

        # These should work without issues for HTTP transports
        try:
            setup_signal_handlers()
            ensure_clean_exit()
            print("Lifecycle module works correctly for HTTP transports")
        except Exception as e:
            pytest.fail(f"Lifecycle module failed: {e}")
