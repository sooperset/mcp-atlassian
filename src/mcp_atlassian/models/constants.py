"""
Constants and default values for model conversions.

This module centralizes all default values and fallbacks used when
converting API responses to models, eliminating "magic strings" in
the codebase and providing a single source of truth for defaults.
"""

#
# Common defaults
#
EMPTY_STRING = ""
UNKNOWN = "Unknown"
UNASSIGNED = "Unassigned"
NONE_VALUE = "None"

#
# Jira defaults
#
JIRA_DEFAULT_ID = "0"
JIRA_DEFAULT_KEY = "UNKNOWN-0"

# Status defaults
JIRA_DEFAULT_STATUS = {
    "name": UNKNOWN,
    "id": JIRA_DEFAULT_ID,
}

# Priority defaults
JIRA_DEFAULT_PRIORITY = {
    "name": NONE_VALUE,
    "id": JIRA_DEFAULT_ID,
}

# Issue type defaults
JIRA_DEFAULT_ISSUE_TYPE = {
    "name": UNKNOWN,
    "id": JIRA_DEFAULT_ID,
}

# Project defaults
JIRA_DEFAULT_PROJECT = JIRA_DEFAULT_ID

#
# Confluence defaults
#
CONFLUENCE_DEFAULT_ID = "0"

# Space defaults
CONFLUENCE_DEFAULT_SPACE = {
    "key": EMPTY_STRING,
    "name": UNKNOWN,
    "id": CONFLUENCE_DEFAULT_ID,
}

# Version defaults
CONFLUENCE_DEFAULT_VERSION = {
    "number": 0,
    "when": EMPTY_STRING,
}

# Date/Time defaults
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00.000+0000"
