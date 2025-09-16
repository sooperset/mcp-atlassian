#!/usr/bin/env python3
"""Simple verification that FormsMixin is properly integrated."""

import sys
from pathlib import Path


def check_forms_integration() -> bool:
    """Check if FormsMixin is properly integrated."""

    # Check if FormsMixin is in __init__.py
    init_file = Path("src/mcp_atlassian/jira/__init__.py")
    if not init_file.exists():
        print("ERROR: __init__.py not found")
        return False

    with open(init_file) as f:
        content = f.read()

    if "FormsMixin" not in content:
        print("ERROR: FormsMixin not imported in __init__.py")
        return False

    if "FormsMixin" not in content.split("class JiraFetcher")[1]:
        print("ERROR: FormsMixin not in JiraFetcher inheritance")
        return False

    print("SUCCESS: FormsMixin is properly integrated in JiraFetcher")

    # Check if forms tools are in server
    server_file = Path("src/mcp_atlassian/servers/jira.py")
    if not server_file.exists():
        print("ERROR: jira.py server file not found")
        return False

    with open(server_file) as f:
        server_content = f.read()

    forms_tools = [
        "get_form",
        "get_issue_forms",
        "submit_form",
        "get_form_answers",
        "attach_form",
        "get_issue_forms_index",
        "change_form_visibility",
        "submit_form_action",
        "reopen_form",
        "copy_forms",
        "get_form_simplified_answers",
        "get_project_form_templates",
        "get_project_form_template",
        "export_form_template",
        "create_project_form_template",
        "update_project_form_template",
        "delete_project_form_template",
    ]
    missing_tools = []

    for tool in forms_tools:
        if f"async def {tool}" not in server_content:
            missing_tools.append(tool)

    if missing_tools:
        print(f"ERROR: Missing forms tools: {missing_tools}")
        return False

    print("SUCCESS: All forms tools are implemented in server")

    # Check if FormsMixin methods exist
    forms_file = Path("src/mcp_atlassian/jira/forms.py")
    if not forms_file.exists():
        print("ERROR: forms.py not found")
        return False

    with open(forms_file) as f:
        forms_content = f.read()

    forms_methods = [
        "get_form",
        "get_issue_forms",
        "submit_form",
        "get_form_answers",
        "attach_form",
        "get_issue_forms_index",
        "change_form_visibility",
        "submit_form_action",
        "reopen_form",
        "copy_forms",
        "get_form_simplified_answers",
        "get_project_form_templates",
        "get_project_form_template",
        "export_form_template",
        "create_project_form_template",
        "update_project_form_template",
        "delete_project_form_template",
    ]
    missing_methods = []

    for method in forms_methods:
        if f"def {method}" not in forms_content:
            missing_methods.append(method)

    if missing_methods:
        print(f"ERROR: Missing forms methods: {missing_methods}")
        return False

    print("SUCCESS: All forms methods are implemented in FormsMixin")

    return True


if __name__ == "__main__":
    print("Verifying Jira Forms integration...")
    if check_forms_integration():
        print("\nAll checks passed! Jira Forms should be available.")
        print("\nAvailable forms tools:")
        print("  - get_form: Retrieve form definition")
        print("  - get_issue_forms: Retrieve forms attached to an issue")
        print("  - submit_form: Submit a form for an issue")
        print("  - get_form_answers: Retrieve form answers")
        print("  - attach_form: Attach a form template to an issue")
        print("  - get_issue_forms_index: Get forms index for an issue")
        print("  - change_form_visibility: Change form visibility (external/internal)")
        print("  - submit_form_action: Submit form action (submit/reject)")
        print("  - reopen_form: Reopen a form for editing")
        print("  - copy_forms: Copy forms between issues")
        print("  - get_form_simplified_answers: Get simplified form answers")
        print("  - get_project_form_templates: Get project form templates")
        print("  - get_project_form_template: Get specific project form template")
        print("  - export_form_template: Export form template")
        print("  - create_project_form_template: Create new form template")
        print("  - update_project_form_template: Update existing form template")
        print("  - delete_project_form_template: Delete form template")
        print("\nIf you're not seeing these tools in your MCP client, try:")
        print("  1. Restarting your MCP client")
        print("  2. Check that you're using the installed development version")
        print("  3. Verify the server is loading from the correct location")
    else:
        print("\nERROR: Integration issues found.")
        sys.exit(1)
