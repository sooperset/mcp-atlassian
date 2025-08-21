#!/usr/bin/env python3
"""
Debug script to diagnose read-only mode configuration issues.
This script will test the exact same logic the MCP server uses.
"""

import os
import sys
sys.path.insert(0, 'src')

from mcp_atlassian.utils.env import is_env_extended_truthy
from mcp_atlassian.utils.io import is_read_only_mode

def main():
    print("=== READ-ONLY MODE DIAGNOSTIC ===")
    print()
    
    # Check raw environment variable
    raw_value = os.getenv("READ_ONLY_MODE")
    print(f"1. Raw READ_ONLY_MODE environment variable: {repr(raw_value)}")
    
    # Check with default
    with_default = os.getenv("READ_ONLY_MODE", "false")
    print(f"2. READ_ONLY_MODE with 'false' default: {repr(with_default)}")
    
    # Check lowercased
    lowercased = with_default.lower()
    print(f"3. Lowercased value: {repr(lowercased)}")
    
    # Check if it's in truthy values
    truthy_values = ("true", "1", "yes", "y", "on")
    is_in_truthy = lowercased in truthy_values
    print(f"4. Is '{lowercased}' in {truthy_values}? {is_in_truthy}")
    
    # Test the actual functions
    print()
    print("=== FUNCTION TESTS ===")
    extended_truthy_result = is_env_extended_truthy("READ_ONLY_MODE", "false")
    print(f"5. is_env_extended_truthy('READ_ONLY_MODE', 'false'): {extended_truthy_result}")
    
    read_only_mode_result = is_read_only_mode()
    print(f"6. is_read_only_mode(): {read_only_mode_result}")
    
    print()
    print("=== ENVIRONMENT VARIABLES DUMP ===")
    relevant_vars = {}
    for key, value in os.environ.items():
        if "READ" in key.upper() or "ONLY" in key.upper() or "MODE" in key.upper():
            relevant_vars[key] = value
    
    if relevant_vars:
        print("Environment variables containing 'READ', 'ONLY', or 'MODE':")
        for key, value in sorted(relevant_vars.items()):
            print(f"  {key}={repr(value)}")
    else:
        print("No environment variables found containing 'READ', 'ONLY', or 'MODE'")
    
    print()
    print("=== CONCLUSION ===")
    if read_only_mode_result:
        print("❌ READ-ONLY MODE IS ENABLED")
        print("This explains why write operations are failing!")
        if raw_value is None:
            print("The READ_ONLY_MODE environment variable is not set, but the server thinks it's enabled.")
            print("This suggests a logic bug in the environment variable handling.")
        else:
            print(f"The READ_ONLY_MODE environment variable is set to: {repr(raw_value)}")
            print("Check if this value is being interpreted as truthy.")
    else:
        print("✅ READ-ONLY MODE IS DISABLED")
        print("The environment variable logic is working correctly.")
        print("The problem must be elsewhere (e.g., server initialization logic).")

if __name__ == "__main__":
    main()