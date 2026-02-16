"""Zephyr Scale FastMCP server instance and tool definitions."""

import json
import logging
from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field
from requests.exceptions import HTTPError

from mcp_atlassian.exceptions import MCPAtlassianAuthenticationError
from mcp_atlassian.servers.dependencies import get_zephyr_fetcher
from mcp_atlassian.utils.decorators import check_write_access

logger = logging.getLogger(__name__)

zephyr_mcp = FastMCP(
    name="Zephyr Scale MCP Service",
    instructions="Provides tools for interacting with Zephyr Scale test management.",
)


@zephyr_mcp.tool(
    tags={"zephyr", "read"},
    annotations={"title": "Get Test Case", "readOnlyHint": True},
)
async def zephyr_get_test_case(
    ctx: Context,
    test_case_key: Annotated[str, Field(description="Test case key (e.g., 'PROJ-T1')")],
) -> str:
    """
    Get details of a specific Zephyr Scale test case.

    Args:
        ctx: The FastMCP context.
        test_case_key: Test case key.

    Returns:
        JSON string representing the test case object.

    Raises:
        ValueError: If the Zephyr client is not configured or available.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        test_case = zephyr.get_test_case(test_case_key)
        response_data = {"success": True, "testCase": test_case}
    except Exception as e:
        error_message = ""
        log_level = logging.ERROR
        if isinstance(e, ValueError) and "not found" in str(e).lower():
            log_level = logging.WARNING
            error_message = str(e)
        elif isinstance(e, MCPAtlassianAuthenticationError):
            error_message = f"Authentication/Permission Error: {str(e)}"
        elif isinstance(e, OSError | HTTPError):
            error_message = f"Network or API Error: {str(e)}"
        else:
            error_message = "An unexpected error occurred while fetching the test case."
            logger.exception(
                f"Unexpected error in zephyr_get_test_case for '{test_case_key}':"
            )
        error_result = {
            "success": False,
            "error": str(e),
            "test_case_key": test_case_key,
        }
        logger.log(
            log_level,
            f"zephyr_get_test_case failed for '{test_case_key}': {error_message}",
        )
        response_data = error_result
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "read"},
    annotations={"title": "Search Test Cases", "readOnlyHint": True},
)
async def zephyr_search_test_cases(
    ctx: Context,
    project_key: Annotated[str, Field(description="Project key (e.g., 'PROJ')")],
    folder_id: Annotated[
        int | None, Field(description="Optional folder ID to filter by")
    ] = None,
    max_results: Annotated[
        int, Field(description="Maximum number of results (1-100)")
    ] = 50,
) -> str:
    """
    Search for test cases in a Zephyr Scale project.

    Args:
        ctx: The FastMCP context.
        project_key: Project key.
        folder_id: Optional folder ID to filter by.
        max_results: Maximum number of results.

    Returns:
        JSON string representing the search results.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        results = zephyr.search_test_cases(project_key, folder_id, max_results)
        response_data = {"success": True, "results": results}
    except Exception as e:
        logger.exception(f"Error searching test cases in project '{project_key}':")
        response_data = {
            "success": False,
            "error": str(e),
            "project_key": project_key,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "write"},
    annotations={"title": "Create Test Case", "readOnlyHint": False},
)
@check_write_access
async def zephyr_create_test_case(
    ctx: Context,
    project_key: Annotated[str, Field(description="Project key (e.g., 'PROJ')")],
    name: Annotated[str, Field(description="Test case name")],
    objective: Annotated[
        str | None, Field(description="Test objective/description")
    ] = None,
    precondition: Annotated[
        str | None, Field(description="Preconditions for the test")
    ] = None,
    priority: Annotated[
        str | None, Field(description="Priority (e.g., 'High', 'Medium', 'Low')")
    ] = None,
    status: Annotated[
        str | None, Field(description="Status (e.g., 'Draft', 'Approved')")
    ] = None,
) -> str:
    """
    Create a new test case in Zephyr Scale.

    Args:
        ctx: The FastMCP context.
        project_key: Project key.
        name: Test case name.
        objective: Test objective/description.
        precondition: Preconditions for the test.
        priority: Priority.
        status: Status.

    Returns:
        JSON string representing the created test case.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        test_case = zephyr.create_test_case(
            project_key=project_key,
            name=name,
            objective=objective,
            precondition=precondition,
            priority=priority,
            status=status,
        )
        response_data = {"success": True, "testCase": test_case}
    except Exception as e:
        logger.exception(
            f"Error creating test case '{name}' in project '{project_key}':"
        )
        response_data = {
            "success": False,
            "error": str(e),
            "project_key": project_key,
            "name": name,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "write"},
    annotations={"title": "Update Test Case", "readOnlyHint": False},
)
@check_write_access
async def zephyr_update_test_case(
    ctx: Context,
    test_case_key: Annotated[str, Field(description="Test case key (e.g., 'PROJ-T1')")],
    name: Annotated[str | None, Field(description="Test case name")] = None,
    objective: Annotated[
        str | None, Field(description="Test objective/description")
    ] = None,
    precondition: Annotated[
        str | None, Field(description="Preconditions for the test")
    ] = None,
    priority: Annotated[str | None, Field(description="Priority")] = None,
    status: Annotated[str | None, Field(description="Status")] = None,
) -> str:
    """
    Update an existing test case in Zephyr Scale.

    Args:
        ctx: The FastMCP context.
        test_case_key: Test case key.
        name: Test case name.
        objective: Test objective/description.
        precondition: Preconditions for the test.
        priority: Priority.
        status: Status.

    Returns:
        JSON string representing the updated test case.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        test_case = zephyr.update_test_case(
            test_case_key=test_case_key,
            name=name,
            objective=objective,
            precondition=precondition,
            priority=priority,
            status=status,
        )
        response_data = {"success": True, "testCase": test_case}
    except Exception as e:
        logger.exception(f"Error updating test case '{test_case_key}':")
        response_data = {
            "success": False,
            "error": str(e),
            "test_case_key": test_case_key,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "read"},
    annotations={"title": "Get Test Cycle", "readOnlyHint": True},
)
async def zephyr_get_test_cycle(
    ctx: Context,
    test_cycle_key: Annotated[
        str, Field(description="Test cycle key (e.g., 'PROJ-C1')")
    ],
) -> str:
    """
    Get details of a specific Zephyr Scale test cycle.

    Args:
        ctx: The FastMCP context.
        test_cycle_key: Test cycle key.

    Returns:
        JSON string representing the test cycle object.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        test_cycle = zephyr.get_test_cycle(test_cycle_key)
        response_data = {"success": True, "testCycle": test_cycle}
    except Exception as e:
        logger.exception(f"Error fetching test cycle '{test_cycle_key}':")
        response_data = {
            "success": False,
            "error": str(e),
            "test_cycle_key": test_cycle_key,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "write"},
    annotations={"title": "Create Test Cycle", "readOnlyHint": False},
)
@check_write_access
async def zephyr_create_test_cycle(
    ctx: Context,
    project_key: Annotated[str, Field(description="Project key (e.g., 'PROJ')")],
    name: Annotated[str, Field(description="Test cycle name")],
    description: Annotated[
        str | None, Field(description="Test cycle description")
    ] = None,
    planned_start_date: Annotated[
        str | None, Field(description="Start date (ISO 8601 format)")
    ] = None,
    planned_end_date: Annotated[
        str | None, Field(description="End date (ISO 8601 format)")
    ] = None,
) -> str:
    """
    Create a new test cycle in Zephyr Scale.

    Args:
        ctx: The FastMCP context.
        project_key: Project key.
        name: Test cycle name.
        description: Test cycle description.
        planned_start_date: Start date.
        planned_end_date: End date.

    Returns:
        JSON string representing the created test cycle.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        test_cycle = zephyr.create_test_cycle(
            project_key=project_key,
            name=name,
            description=description,
            planned_start_date=planned_start_date,
            planned_end_date=planned_end_date,
        )
        response_data = {"success": True, "testCycle": test_cycle}
    except Exception as e:
        logger.exception(
            f"Error creating test cycle '{name}' in project '{project_key}':"
        )
        response_data = {
            "success": False,
            "error": str(e),
            "project_key": project_key,
            "name": name,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "read"},
    annotations={"title": "Get Test Execution", "readOnlyHint": True},
)
async def zephyr_get_test_execution(
    ctx: Context,
    test_execution_key: Annotated[
        str, Field(description="Test execution key (e.g., 'PROJ-E1')")
    ],
) -> str:
    """
    Get details of a specific Zephyr Scale test execution.

    Args:
        ctx: The FastMCP context.
        test_execution_key: Test execution key.

    Returns:
        JSON string representing the test execution object.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        test_execution = zephyr.get_test_execution(test_execution_key)
        response_data = {"success": True, "testExecution": test_execution}
    except Exception as e:
        logger.exception(f"Error fetching test execution '{test_execution_key}':")
        response_data = {
            "success": False,
            "error": str(e),
            "test_execution_key": test_execution_key,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "write"},
    annotations={"title": "Create Test Execution", "readOnlyHint": False},
)
@check_write_access
async def zephyr_create_test_execution(
    ctx: Context,
    project_key: Annotated[str, Field(description="Project key (e.g., 'PROJ')")],
    test_case_key: Annotated[str, Field(description="Test case key (e.g., 'PROJ-T1')")],
    test_cycle_key: Annotated[
        str | None, Field(description="Optional test cycle key")
    ] = None,
    status: Annotated[
        str | None,
        Field(
            description="Execution status (e.g., 'Pass', 'Fail', 'Blocked', "
            "'Not Executed')"
        ),
    ] = None,
    comment: Annotated[str | None, Field(description="Execution comment/notes")] = None,
) -> str:
    """
    Create a new test execution in Zephyr Scale.

    Args:
        ctx: The FastMCP context.
        project_key: Project key.
        test_case_key: Test case key.
        test_cycle_key: Optional test cycle key.
        status: Execution status.
        comment: Execution comment/notes.

    Returns:
        JSON string representing the created test execution.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        test_execution = zephyr.create_test_execution(
            project_key=project_key,
            test_case_key=test_case_key,
            test_cycle_key=test_cycle_key,
            status=status,
            comment=comment,
        )
        response_data = {"success": True, "testExecution": test_execution}
    except Exception as e:
        logger.exception(
            f"Error creating test execution for '{test_case_key}' in project "
            f"'{project_key}':"
        )
        response_data = {
            "success": False,
            "error": str(e),
            "project_key": project_key,
            "test_case_key": test_case_key,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "write"},
    annotations={"title": "Update Test Execution", "readOnlyHint": False},
)
@check_write_access
async def zephyr_update_test_execution(
    ctx: Context,
    test_execution_key: Annotated[
        str, Field(description="Test execution key (e.g., 'PROJ-E1')")
    ],
    status: Annotated[str | None, Field(description="Execution status")] = None,
    comment: Annotated[str | None, Field(description="Execution comment/notes")] = None,
) -> str:
    """
    Update an existing test execution in Zephyr Scale.

    Args:
        ctx: The FastMCP context.
        test_execution_key: Test execution key.
        status: Execution status.
        comment: Execution comment/notes.

    Returns:
        JSON string representing the updated test execution.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        test_execution = zephyr.update_test_execution(
            test_execution_key=test_execution_key,
            status=status,
            comment=comment,
        )
        response_data = {"success": True, "testExecution": test_execution}
    except Exception as e:
        logger.exception(f"Error updating test execution '{test_execution_key}':")
        response_data = {
            "success": False,
            "error": str(e),
            "test_execution_key": test_execution_key,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)


@zephyr_mcp.tool(
    tags={"zephyr", "write"},
    annotations={"title": "Link Test Case to Issue", "readOnlyHint": False},
)
@check_write_access
async def zephyr_link_test_case_to_issue(
    ctx: Context,
    test_case_key: Annotated[str, Field(description="Test case key (e.g., 'PROJ-T1')")],
    issue_key: Annotated[str, Field(description="Jira issue key (e.g., 'PROJ-123')")],
) -> str:
    """
    Link a test case to a Jira issue in Zephyr Scale.

    Args:
        ctx: The FastMCP context.
        test_case_key: Test case key.
        issue_key: Jira issue key.

    Returns:
        JSON string indicating success or failure.
    """
    zephyr = await get_zephyr_fetcher(ctx)
    try:
        result = zephyr.link_test_case_to_issue(test_case_key, issue_key)
        response_data = {
            "success": True,
            "message": f"Linked test case {test_case_key} to issue {issue_key}",
            "link": result,
        }
    except Exception as e:
        logger.exception(
            f"Error linking test case '{test_case_key}' to issue '{issue_key}':"
        )
        response_data = {
            "success": False,
            "error": str(e),
            "test_case_key": test_case_key,
            "issue_key": issue_key,
        }
    return json.dumps(response_data, indent=2, ensure_ascii=False)
