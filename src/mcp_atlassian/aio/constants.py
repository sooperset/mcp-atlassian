"""Constants for AIO Tests API interactions."""

# Default base URL for the AIO Tests Cloud REST API (v1).
AIO_CLOUD_API_BASE = "https://tcms.aiojiraapps.com/aio-tcms/api/v1"

# Path appended to a Jira Server/Data Center base URL to reach the AIO Tests API.
AIO_SERVER_API_PATH = "/rest/aio-tcms-api/1.0"

# Hostname of the AIO Tests Cloud service.
AIO_CLOUD_HOSTNAME = "tcms.aiojiraapps.com"

# Entity types that own an independent folder tree in AIO Tests. The API path
# segment matches the entity name, e.g. /project/{key}/testcase/folder.
FOLDER_ENTITY_TYPES = ("testcase", "testcycle", "testset")

# Default page size for paginated list/search calls. The API caps pages at 100
# and silently resets anything outside 10-100 back to 100.
DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100

# Step types accepted by the Case create/update APIs.
CLASSIC_STEP_TYPES = ("TEXT", "REFERENCE")
BDD_STEP_TYPES = (
    "BDD_GIVEN",
    "BDD_WHEN",
    "BDD_AND",
    "BDD_BUT",
    "BDD_THEN",
    "BDD_STAR",
)
STEP_TYPES = CLASSIC_STEP_TYPES + BDD_STEP_TYPES

# Comparison operators supported by the Case search API, per criteria type.
LIST_COMPARISONS = ("IN",)
TEXT_COMPARISONS = ("CONTAINS", "EXACT_MATCH")
DATE_COMPARISONS = ("EMPTY", "BEFORE", "AFTER", "EQUALS", "BETWEEN")

# Case attributes whose values are stored as rich text (HTML).
RICH_TEXT_CASE_FIELDS = ("description", "precondition")

# Step attributes whose values are stored as rich text (HTML).
RICH_TEXT_STEP_KEYS = ("step", "data", "expectedResult", "bddStep")

# Custom field type whose values are stored as rich text (HTML).
RICH_TEXT_CUSTOM_FIELD_TYPE = "MULTI_LINE_TEXT"

# Read-only Case attributes. These are rejected or ignored by the update API, so
# they are stripped from any payload built from a previously fetched case.
READ_ONLY_CASE_FIELDS = frozenset(
    {
        "attachments",
        "createdDate",
        "descriptionAttachments",
        "hasDataSets",
        "isArchived",
        "jiraProjectID",
        "key",
        "permission",
        "preconditionAttachments",
        "updatedDate",
        "version",
        "versions",
    }
)
