"""Tool name → resource type mapping for field-rule lookup.

Each tool returns a particular resource type; field rules in
``PRIVACY_DROP_FIELDS`` / ``PRIVACY_MASK_FIELDS`` are keyed off this type
plus the special wildcard ``"*"``. New upstream tools without a mapping
default to ``None``: PII redaction and resource filtering still run, but
field rules are skipped (safe-by-default).

The mapping intentionally lives in one place so upstream churn affects
exactly one file in this module.
"""

from __future__ import annotations

# Resource type identifiers. Plain strings rather than an enum so user
# config (env var keys) can reference them directly.

# --- Jira ---
JIRA_ISSUE = "jira_issue"
JIRA_ISSUE_LIST = "jira_issue_list"
JIRA_COMMENT = "jira_comment"
JIRA_WORKLOG = "jira_worklog"
JIRA_WORKLOG_LIST = "jira_worklog_list"
JIRA_USER = "jira_user"
JIRA_USER_LIST = "jira_user_list"
JIRA_PROJECT = "jira_project"
JIRA_PROJECT_LIST = "jira_project_list"
JIRA_VERSION = "jira_version"
JIRA_VERSION_LIST = "jira_version_list"
JIRA_COMPONENT_LIST = "jira_component_list"
JIRA_BOARD_LIST = "jira_board_list"
JIRA_SPRINT = "jira_sprint"
JIRA_SPRINT_LIST = "jira_sprint_list"
JIRA_TRANSITION_LIST = "jira_transition_list"
JIRA_LINK_TYPE_LIST = "jira_link_type_list"
JIRA_FIELD_LIST = "jira_field_list"
JIRA_FIELD_OPTION_LIST = "jira_field_option_list"
JIRA_CHANGELOG_LIST = "jira_changelog_list"
JIRA_DEVELOPMENT_INFO = "jira_development_info"
JIRA_ATTACHMENT_LIST = "jira_attachment_list"
JIRA_IMAGE_LIST = "jira_image_list"
JIRA_SLA = "jira_sla"
JIRA_PROFORMA_FORM = "jira_proforma_form"
JIRA_SERVICEDESK_QUEUE_LIST = "jira_servicedesk_queue_list"

# --- Confluence ---
CONFLUENCE_PAGE = "confluence_page"
CONFLUENCE_PAGE_LIST = "confluence_page_list"
CONFLUENCE_PAGE_DIFF = "confluence_page_diff"
CONFLUENCE_PAGE_HISTORY = "confluence_page_history"
CONFLUENCE_PAGE_VIEWS = "confluence_page_views"
CONFLUENCE_COMMENT = "confluence_comment"
CONFLUENCE_COMMENT_LIST = "confluence_comment_list"
CONFLUENCE_USER = "confluence_user"
CONFLUENCE_USER_LIST = "confluence_user_list"
CONFLUENCE_SPACE = "confluence_space"
CONFLUENCE_LABEL_LIST = "confluence_label_list"
CONFLUENCE_ATTACHMENT = "confluence_attachment"
CONFLUENCE_ATTACHMENT_LIST = "confluence_attachment_list"
CONFLUENCE_IMAGE_LIST = "confluence_image_list"

TOOL_RESOURCE_TYPES: dict[str, str] = {
    # --- Jira: issues ---
    "jira_get_issue": JIRA_ISSUE,
    "jira_create_issue": JIRA_ISSUE,
    "jira_update_issue": JIRA_ISSUE,
    "jira_transition_issue": JIRA_ISSUE,
    "jira_link_to_epic": JIRA_ISSUE,
    "jira_batch_create_issues": JIRA_ISSUE_LIST,
    "jira_search": JIRA_ISSUE_LIST,
    "jira_get_project_issues": JIRA_ISSUE_LIST,
    "jira_get_board_issues": JIRA_ISSUE_LIST,
    "jira_get_sprint_issues": JIRA_ISSUE_LIST,
    "jira_get_queue_issues": JIRA_ISSUE_LIST,
    # --- Jira: comments ---
    "jira_add_comment": JIRA_COMMENT,
    "jira_edit_comment": JIRA_COMMENT,
    # --- Jira: worklogs ---
    "jira_add_worklog": JIRA_WORKLOG,
    "jira_get_worklog": JIRA_WORKLOG_LIST,
    # --- Jira: users / watchers ---
    "jira_get_user_profile": JIRA_USER,
    "jira_get_issue_watchers": JIRA_USER_LIST,
    # --- Jira: projects / versions / components ---
    "jira_get_all_projects": JIRA_PROJECT_LIST,
    "jira_get_project_versions": JIRA_VERSION_LIST,
    "jira_get_project_components": JIRA_COMPONENT_LIST,
    "jira_create_version": JIRA_VERSION,
    "jira_batch_create_versions": JIRA_VERSION_LIST,
    # --- Jira: agile ---
    "jira_get_agile_boards": JIRA_BOARD_LIST,
    "jira_get_sprints_from_board": JIRA_SPRINT_LIST,
    "jira_create_sprint": JIRA_SPRINT,
    "jira_update_sprint": JIRA_SPRINT,
    # --- Jira: workflow / fields / metadata ---
    "jira_get_transitions": JIRA_TRANSITION_LIST,
    "jira_get_link_types": JIRA_LINK_TYPE_LIST,
    "jira_search_fields": JIRA_FIELD_LIST,
    "jira_get_field_options": JIRA_FIELD_OPTION_LIST,
    "jira_batch_get_changelogs": JIRA_CHANGELOG_LIST,
    # --- Jira: development / attachments / SLA / forms ---
    "jira_get_issue_development_info": JIRA_DEVELOPMENT_INFO,
    "jira_get_issues_development_info": JIRA_DEVELOPMENT_INFO,
    "jira_download_attachments": JIRA_ATTACHMENT_LIST,
    "jira_get_issue_images": JIRA_IMAGE_LIST,
    "jira_get_issue_sla": JIRA_SLA,
    "jira_get_issue_proforma_forms": JIRA_PROFORMA_FORM,
    "jira_get_proforma_form_details": JIRA_PROFORMA_FORM,
    "jira_update_proforma_form_answers": JIRA_PROFORMA_FORM,
    # --- Jira: service desk ---
    "jira_get_service_desk_queues": JIRA_SERVICEDESK_QUEUE_LIST,
    # --- Confluence: pages ---
    "confluence_get_page": CONFLUENCE_PAGE,
    "confluence_create_page": CONFLUENCE_PAGE,
    "confluence_update_page": CONFLUENCE_PAGE,
    "confluence_move_page": CONFLUENCE_PAGE,
    "confluence_search": CONFLUENCE_PAGE_LIST,
    "confluence_get_page_children": CONFLUENCE_PAGE_LIST,
    "confluence_get_space_page_tree": CONFLUENCE_PAGE_LIST,
    "confluence_get_page_diff": CONFLUENCE_PAGE_DIFF,
    "confluence_get_page_history": CONFLUENCE_PAGE_HISTORY,
    "confluence_get_page_views": CONFLUENCE_PAGE_VIEWS,
    # --- Confluence: comments ---
    "confluence_add_comment": CONFLUENCE_COMMENT,
    "confluence_reply_to_comment": CONFLUENCE_COMMENT,
    "confluence_get_comments": CONFLUENCE_COMMENT_LIST,
    # --- Confluence: users ---
    "confluence_search_user": CONFLUENCE_USER_LIST,
    # --- Confluence: labels / attachments / images ---
    "confluence_get_labels": CONFLUENCE_LABEL_LIST,
    "confluence_add_label": CONFLUENCE_LABEL_LIST,
    "confluence_get_attachments": CONFLUENCE_ATTACHMENT_LIST,
    "confluence_upload_attachment": CONFLUENCE_ATTACHMENT,
    "confluence_upload_attachments": CONFLUENCE_ATTACHMENT_LIST,
    "confluence_get_page_images": CONFLUENCE_IMAGE_LIST,
}


def resource_type_for_tool(tool_name: str) -> str | None:
    """Return the resource-type key for ``tool_name``, or ``None`` if unknown.

    Unknown tool names are not an error: the privacy pipeline simply skips
    field rules for them. PII redaction and resource filtering still run.
    """
    return TOOL_RESOURCE_TYPES.get(tool_name)
