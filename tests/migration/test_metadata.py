import pytest
from fastmcp import Client
from fastmcp.client import FastMCPTransport

from src.mcp_atlassian.servers.confluence import confluence_mcp
from src.mcp_atlassian.servers.jira import jira_mcp
from tests.migration.original_metadata import ORIGINAL_METADATA


@pytest.mark.anyio
async def test_jira_tools_completeness():
    """Test that all original Jira tools have been migrated to FastMCP."""
    # Get original Jira tools
    original_jira_tools = {
        name: tool
        for name, tool in ORIGINAL_METADATA["tools"].items()
        if name.startswith("jira_")
    }

    # Get FastMCP Jira tools
    fastmcp_tools = await jira_mcp.get_tools()

    # Debug info
    print(f"DEBUG: fastmcp_tools type = {type(fastmcp_tools)}")
    print(f"DEBUG: fastmcp_tools content = {fastmcp_tools}")

    # Handle different return types from get_tools()
    fastmcp_tool_names = set()

    # FastMCP's get_tools() returns a dict where keys are the tool names
    if isinstance(fastmcp_tools, dict):
        # Tools are in a dictionary with keys as tool names
        fastmcp_tool_names = {f"jira_{name}" for name in fastmcp_tools.keys()}
    elif hasattr(fastmcp_tools, "__iter__"):
        # Fallback for iterable non-dictionary response
        try:
            tools_list = list(fastmcp_tools)
            if tools_list:
                if isinstance(tools_list[0], str):
                    # If get_tools() returns strings
                    fastmcp_tool_names = set(tools_list)
                else:
                    # If get_tools() returns objects with a name attribute
                    fastmcp_tool_names = {
                        f"jira_{tool.name}"
                        for tool in tools_list
                        if hasattr(tool, "name")
                    }
        except (IndexError, TypeError, AttributeError) as e:
            print(f"DEBUG: Error processing tools: {e}")
            # If tools is empty or can't be processed, just use empty set
            fastmcp_tool_names = set()

    # Check for missing tools
    original_tool_names = set(original_jira_tools.keys())

    missing_tools = original_tool_names - fastmcp_tool_names
    extra_tools = fastmcp_tool_names - original_tool_names

    # Print details for debugging
    print(f"DEBUG: Original tool names: {original_tool_names}")
    print(f"DEBUG: FastMCP tool names: {fastmcp_tool_names}")

    assert not missing_tools, (
        f"Missing tools in FastMCP implementation: {missing_tools}"
    )
    assert not extra_tools, f"Extra tools in FastMCP implementation: {extra_tools}"


@pytest.mark.anyio
async def test_jira_tools_parameters_match():
    """Test that the parameters for each Jira tool match between original and FastMCP."""
    # Get original Jira tools
    original_jira_tools = {
        name: tool
        for name, tool in ORIGINAL_METADATA["tools"].items()
        if name.startswith("jira_")
    }

    # Get FastMCP Jira tools with a Client to get full schemas
    # Using the async context manager pattern
    client = Client(transport=FastMCPTransport(jira_mcp))

    async with client as connected_client:
        tools = await connected_client.list_tools()

        fastmcp_tools = {f"jira_{tool.name}": tool for tool in tools}

        # Check each tool's parameters
        for tool_name, original_tool in original_jira_tools.items():
            fastmcp_tool = fastmcp_tools.get(tool_name)
            if not fastmcp_tool:
                continue  # Already checked for missing tools in previous test

            # Compare parameters
            original_params = original_tool.get("inputSchema", {}).get("properties", {})

            # The FastMCP tool structure might have input_schema instead of parameters
            input_schema = {}
            if hasattr(fastmcp_tool, "parameters"):
                input_schema = fastmcp_tool.parameters
            elif hasattr(fastmcp_tool, "input_schema"):
                input_schema = fastmcp_tool.input_schema
            else:
                # If we can't find the input schema, try to use function signature
                print(
                    f"WARNING: Could not find input schema for {tool_name}, attempting to use function signature"
                )
                if hasattr(fastmcp_tool, "func"):
                    import inspect

                    sig = inspect.signature(fastmcp_tool.func)
                    # Skip 'ctx' parameter which is added by FastMCP
                    params = {
                        param_name: {}
                        for param_name in sig.parameters
                        if param_name != "ctx"
                    }
                    input_schema = {"properties": params}
                else:
                    print(f"ERROR: Could not find function for {tool_name}")
                    continue

            fastmcp_params = input_schema.get("properties", {})

            # Check for missing parameters
            original_param_names = set(original_params.keys())
            fastmcp_param_names = set(fastmcp_params.keys())

            missing_params = original_param_names - fastmcp_param_names
            extra_params = fastmcp_param_names - original_param_names

            assert not missing_params, (
                f"Tool {tool_name} is missing parameters: {missing_params}"
            )

            # Extra parameters could be intentional, so just log them
            if extra_params:
                print(f"INFO: Tool {tool_name} has extra parameters: {extra_params}")

            # Check required parameters
            original_required = set(
                original_tool.get("inputSchema", {}).get("required", [])
            )
            fastmcp_required = set(input_schema.get("required", []))

            missing_required = original_required - fastmcp_required
            extra_required = fastmcp_required - original_required

            assert not missing_required, (
                f"Tool {tool_name} is missing required parameters: {missing_required}"
            )
            assert not extra_required, (
                f"Tool {tool_name} has extra required parameters: {extra_required}"
            )


@pytest.mark.anyio
async def test_jira_resources_completeness():
    """Test that all original Jira resources have been migrated to FastMCP."""
    # Get original Jira resources
    original_jira_resources = {
        uri: resource
        for uri, resource in ORIGINAL_METADATA["resources"].items()
        if uri.startswith("jira://")
    }

    # Get FastMCP Jira resources
    fastmcp_resources = await jira_mcp.get_resources()

    # Get URI templates from resources
    original_uris = set(original_jira_resources.keys())
    fastmcp_uris = {resource.uri_template for resource in fastmcp_resources}

    # Create a function to normalize URI templates for comparison
    def normalize_uri(uri):
        # Replace dynamic parts like {id} with a placeholder
        # This is needed because variable names might differ between original and FastMCP
        return uri.replace("{", "{_").replace("}", "}_")

    # Normalize URIs for comparison
    normalized_original = {normalize_uri(uri) for uri in original_uris}
    normalized_fastmcp = {normalize_uri(uri) for uri in fastmcp_uris}

    missing_resources = normalized_original - normalized_fastmcp

    assert not missing_resources, (
        f"Missing resources in FastMCP implementation: {missing_resources}"
    )


@pytest.mark.anyio
async def test_confluence_tools_completeness():
    """Test that all original Confluence tools have been migrated to FastMCP."""
    # Get original Confluence tools
    original_confluence_tools = {
        name: tool
        for name, tool in ORIGINAL_METADATA["tools"].items()
        if name.startswith("confluence_")
    }

    # Get FastMCP Confluence tools
    fastmcp_tools = await confluence_mcp.get_tools()

    # Debug info
    print(f"DEBUG: fastmcp_tools type = {type(fastmcp_tools)}")
    print(f"DEBUG: fastmcp_tools content = {fastmcp_tools}")

    # Handle different return types from get_tools()
    fastmcp_tool_names = set()

    # FastMCP's get_tools() returns a dict where keys are the tool names
    if isinstance(fastmcp_tools, dict):
        # Tools are in a dictionary with keys as tool names
        fastmcp_tool_names = {f"confluence_{name}" for name in fastmcp_tools.keys()}
    elif hasattr(fastmcp_tools, "__iter__"):
        # Fallback for iterable non-dictionary response
        try:
            # Try to convert to list to safely check
            tools_list = list(fastmcp_tools)
            if tools_list:
                if isinstance(tools_list[0], str):
                    # If get_tools() returns strings
                    fastmcp_tool_names = set(tools_list)
                else:
                    # If get_tools() returns objects with a name attribute
                    fastmcp_tool_names = {
                        f"confluence_{tool.name}"
                        for tool in tools_list
                        if hasattr(tool, "name")
                    }
        except (IndexError, TypeError, AttributeError) as e:
            print(f"DEBUG: Error processing tools: {e}")
            # If tools is empty or can't be processed, just use empty set
            fastmcp_tool_names = set()

    # Check for missing tools
    original_tool_names = set(original_confluence_tools.keys())

    missing_tools = original_tool_names - fastmcp_tool_names
    extra_tools = fastmcp_tool_names - original_tool_names

    # Print details for debugging
    print(f"DEBUG: Original tool names: {original_tool_names}")
    print(f"DEBUG: FastMCP tool names: {fastmcp_tool_names}")

    assert not missing_tools, (
        f"Missing tools in FastMCP implementation: {missing_tools}"
    )
    assert not extra_tools, f"Extra tools in FastMCP implementation: {extra_tools}"


@pytest.mark.anyio
async def test_confluence_tools_parameters_match():
    """Test that the parameters for each Confluence tool match between original and FastMCP."""
    # Get original Confluence tools
    original_confluence_tools = {
        name: tool
        for name, tool in ORIGINAL_METADATA["tools"].items()
        if name.startswith("confluence_")
    }

    # Get FastMCP Confluence tools with a Client to get full schemas
    # Using the async context manager pattern
    client = Client(transport=FastMCPTransport(confluence_mcp))

    async with client as connected_client:
        tools = await connected_client.list_tools()

        fastmcp_tools = {f"confluence_{tool.name}": tool for tool in tools}

        # Check each tool's parameters
        for tool_name, original_tool in original_confluence_tools.items():
            fastmcp_tool = fastmcp_tools.get(tool_name)
            if not fastmcp_tool:
                continue  # Already checked for missing tools in previous test

            # Compare parameters
            original_params = original_tool.get("inputSchema", {}).get("properties", {})

            # The FastMCP tool structure might have input_schema instead of parameters
            input_schema = {}
            if hasattr(fastmcp_tool, "parameters"):
                input_schema = fastmcp_tool.parameters
            elif hasattr(fastmcp_tool, "input_schema"):
                input_schema = fastmcp_tool.input_schema
            else:
                # If we can't find the input schema, try to use function signature
                print(
                    f"WARNING: Could not find input schema for {tool_name}, attempting to use function signature"
                )
                if hasattr(fastmcp_tool, "func"):
                    import inspect

                    sig = inspect.signature(fastmcp_tool.func)
                    # Skip 'ctx' parameter which is added by FastMCP
                    params = {
                        param_name: {}
                        for param_name in sig.parameters
                        if param_name != "ctx"
                    }
                    input_schema = {"properties": params}
                else:
                    print(f"ERROR: Could not find function for {tool_name}")
                    continue

            fastmcp_params = input_schema.get("properties", {})

            # Check for missing parameters
            original_param_names = set(original_params.keys())
            fastmcp_param_names = set(fastmcp_params.keys())

            missing_params = original_param_names - fastmcp_param_names
            extra_params = fastmcp_param_names - original_param_names

            assert not missing_params, (
                f"Tool {tool_name} is missing parameters: {missing_params}"
            )

            # Extra parameters could be intentional, so just log them
            if extra_params:
                print(f"INFO: Tool {tool_name} has extra parameters: {extra_params}")

            # Check required parameters
            original_required = set(
                original_tool.get("inputSchema", {}).get("required", [])
            )
            fastmcp_required = set(input_schema.get("required", []))

            missing_required = original_required - fastmcp_required
            extra_required = fastmcp_required - original_required

            assert not missing_required, (
                f"Tool {tool_name} is missing required parameters: {missing_required}"
            )
            assert not extra_required, (
                f"Tool {tool_name} has extra required parameters: {extra_required}"
            )


@pytest.mark.anyio
async def test_confluence_resources_completeness():
    """Test that all original Confluence resources have been migrated to FastMCP."""
    # Get original Confluence resources
    original_confluence_resources = {
        uri: resource
        for uri, resource in ORIGINAL_METADATA["resources"].items()
        if uri.startswith("confluence://")
    }

    # Get FastMCP Confluence resources
    fastmcp_resources = await confluence_mcp.get_resources()

    # Get URI templates from resources
    original_uris = set(original_confluence_resources.keys())
    fastmcp_uris = {resource.uri_template for resource in fastmcp_resources}

    # Create a function to normalize URI templates for comparison
    def normalize_uri(uri):
        # Replace dynamic parts like {id} with a placeholder
        # This is needed because variable names might differ between original and FastMCP
        return uri.replace("{", "{_").replace("}", "}_")

    # Normalize URIs for comparison
    normalized_original = {normalize_uri(uri) for uri in original_uris}
    normalized_fastmcp = {normalize_uri(uri) for uri in fastmcp_uris}

    missing_resources = normalized_original - normalized_fastmcp

    assert not missing_resources, (
        f"Missing resources in FastMCP implementation: {missing_resources}"
    )
