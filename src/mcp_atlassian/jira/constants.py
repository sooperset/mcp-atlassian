"""Constants specific to Jira operations."""

# Set of default fields returned by Jira read operations when no specific fields are requested.
DEFAULT_READ_JIRA_FIELDS: set[str] = {
    "summary",
    "description",
    "status",
    "assignee",
    "reporter",
    "labels",
    "priority",
    "created",
    "updated",
    "issuetype",
}
