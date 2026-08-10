"""Mock AIO Tests API responses for tests."""

MOCK_AIO_PROJECT_CONFIG = {
    "caseTypes": [
        {"ID": 1, "name": "Functional", "isDefault": True},
        {"ID": 2, "name": "Performance"},
    ],
    "casePriorities": [
        {"ID": 10, "name": "Critical"},
        {"ID": 11, "name": "Medium", "isDefault": True},
    ],
    "caseStatuses": [
        {"ID": 20, "name": "Draft", "description": "Work in progress"},
        {"ID": 21, "name": "Published", "description": "Ready for execution"},
    ],
    "caseAutomationStatuses": [
        {"ID": 30, "name": "Manual", "isDefault": True},
        {"ID": 31, "name": "Automated"},
    ],
    "caseScriptTypes": [
        {"ID": 40, "name": "Classic", "isEnabled": True},
        {"ID": 41, "name": "BDD", "isEnabled": True},
    ],
    "runStatuses": [{"ID": 50, "name": "Passed"}],
    "runStepStatuses": [{"ID": 60, "name": "Passed"}],
    "customFields": [
        {
            "ID": 10113,
            "name": "Environment",
            "description": "Setup used for the case",
            "type": "SINGLE_SELECT_LIST",
            "caseAssociation": {"isAssociated": True, "isRequired": True},
            "allowedListValues": [
                {"ID": 1, "value": "Staging"},
                {"ID": 2, "value": "Production"},
            ],
        },
        {
            "ID": 10114,
            "name": "Reviewer",
            "type": "SINGLE_USER_SELECTOR",
            "caseAssociation": {"isAssociated": True, "isRequired": False},
        },
        {
            "ID": 10116,
            "name": "Notes",
            "type": "MULTI_LINE_TEXT",
            "caseAssociation": {"isAssociated": True, "isRequired": False},
        },
        {
            "ID": 10115,
            "name": "Run Note",
            "type": "SINGLE_LINE_TEXT",
            "caseAssociation": {"isAssociated": False, "isRequired": False},
            "runAssociation": {"isAssociated": True, "isRequired": False},
        },
    ],
    "adhocTestCycle": {"ID": 900, "key": "AT-CY-1", "jiraProjectID": 10010},
}

MOCK_AIO_TAGS = [
    {"ID": 1, "name": "AutomationEligible"},
    {"ID": 2, "name": "Smoke"},
]

MOCK_AIO_FOLDER_TREE = [
    {
        "ID": 100,
        "name": "Regression",
        "description": "Regression suites",
        "children": [
            {"ID": 101, "name": "Checkout", "children": []},
            {"ID": 102, "name": "Login", "children": []},
        ],
    },
    {"ID": 200, "name": "Smoke", "children": []},
]

MOCK_AIO_TEST_CASE = {
    "ID": 16557,
    "jiraProjectID": 10010,
    "key": "AT-TC-17",
    "version": 2,
    "title": "Validate quick Add to Cart functionality",
    "description": "Add an item to the cart from the search page",
    "precondition": "Item is available in inventory",
    "ownedByID": "5df1c9f826a4bb0011684aa",
    "folder": {"ID": 101, "name": "Checkout", "parentID": 100},
    "status": {"ID": 21, "name": "Published"},
    "priority": {"ID": 10, "name": "Critical"},
    "type": {"ID": 1, "name": "Functional"},
    "scriptType": {"ID": 40, "name": "Classic"},
    "automationStatus": {"ID": 30, "name": "Manual"},
    "estimatedEffort": 3600,
    "createdDate": "2026-01-05T10:00:00.000Z",
    "updatedDate": "2026-02-11T09:30:00.000Z",
    "isArchived": False,
    "jiraRequirementIDs": ["10221"],
    "jiraComponentIDs": [10000],
    "jiraReleaseIDs": [10500],
    "tags": [
        {"tag": {"ID": 2, "name": "Smoke"}, "associationID": 12},
    ],
    "steps": [
        {
            "ID": 1,
            "stepType": "TEXT",
            "step": "Search for an item",
            "data": "shoes",
            "expectedResult": "Results are listed",
        },
        {
            "ID": 2,
            "stepType": "TEXT",
            "step": "Click quick add to cart",
            "expectedResult": "Item is added to the cart",
        },
    ],
    "customFields": [{"ID": 10113, "name": "Environment", "value": "Staging"}],
    "versions": [{"version": 2, "ID": 16557}, {"version": 1, "ID": 16556}],
}

MOCK_AIO_SEARCH_RESPONSE = {
    "items": [MOCK_AIO_TEST_CASE],
    "startAt": 0,
    "maxResults": 50,
    "isLast": True,
}

MOCK_AIO_FOLDER_DETAILS = {
    "ID": 101,
    "name": "Checkout",
    "description": "Checkout flows",
    "parentID": 100,
}
