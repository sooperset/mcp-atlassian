MOCK_JIRA_ISSUE_RESPONSE = {
    "expand": "renderedFields,names,schema,operations,editmeta,changelog,versionedRepresentations",
    "id": "12345",
    "self": "https://example.atlassian.net/rest/api/2/issue/12345",
    "key": "PROJ-123",
    "fields": {
        "summary": "Test Issue Summary",
        "description": "This is a test issue description",
        "created": "2024-01-01T10:00:00.000+0000",
        "updated": "2024-01-02T15:30:00.000+0000",
        "status": {
            "self": "https://example.atlassian.net/rest/api/2/status/3",
            "description": "This issue is currently being worked on.",
            "iconUrl": "https://example.atlassian.net/images/icons/statuses/inprogress.png",
            "name": "In Progress",
            "id": "3",
            "statusCategory": {
                "self": "https://example.atlassian.net/rest/api/2/statuscategory/4",
                "id": 4,
                "key": "indeterminate",
                "colorName": "yellow",
                "name": "In Progress",
            },
        },
        "issuetype": {
            "self": "https://example.atlassian.net/rest/api/2/issuetype/10001",
            "id": "10001",
            "description": "A task that needs to be done.",
            "iconUrl": "https://example.atlassian.net/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
            "name": "Task",
            "subtask": False,
        },
        "priority": {
            "self": "https://example.atlassian.net/rest/api/2/priority/3",
            "iconUrl": "https://example.atlassian.net/images/icons/priorities/medium.svg",
            "name": "Medium",
            "id": "3",
        },
        "assignee": {
            "self": "https://example.atlassian.net/rest/api/2/user?accountId=123",
            "accountId": "123",
            "emailAddress": "test@example.com",
            "avatarUrls": {
                "48x48": "https://secure.gravatar.com/avatar/123?d=https%3A%2F%2Favatar.example.com%2Fdefault.png",
            },
            "displayName": "Test User",
            "active": True,
            "timeZone": "UTC",
        },
        "reporter": {
            "self": "https://example.atlassian.net/rest/api/2/user?accountId=456",
            "accountId": "456",
            "displayName": "Reporter User",
            "active": True,
        },
        "labels": ["test-label"],
        "components": [{"name": "Backend"}],
        "fixVersions": [{"name": "v1.0"}],
        "attachment": [
            {
                "id": "10000",
                "filename": "test_attachment.txt",
                "size": 1024,
                "mimeType": "text/plain",
                "content": "https://example.atlassian.net/secure/attachment/10000/test_attachment.txt",
            }
        ],
        "comment": {
            "comments": [
                {
                    "id": "10001",
                    "author": {"displayName": "Commenter User"},
                    "body": "This is a test comment",
                    "created": "2024-01-01T12:00:00.000+0000",
                    "updated": "2024-01-01T12:00:00.000+0000",
                }
            ],
            "maxResults": 1,
            "total": 1,
            "startAt": 0,
        },
        "timetracking": {
            "originalEstimate": "1d",
            "remainingEstimate": "4h",
            "timeSpent": "4h",
            "originalEstimateSeconds": 28800,
            "remainingEstimateSeconds": 14400,
            "timeSpentSeconds": 14400,
        },
        "project": {
            "id": "10000",
            "key": "PROJ",
            "name": "Test Project",
            "self": "https://example.atlassian.net/rest/api/2/project/10000",
            "avatarUrls": {
                "48x48": "https://example.atlassian.net/secure/projectavatar?size=large&pid=10000"
            },
        },
        "resolution": {
            "self": "https://example.atlassian.net/rest/api/2/resolution/10000",
            "id": "10000",
            "description": "Work has been completed on this issue.",
            "name": "Fixed",
        },
        "duedate": "2024-12-31",
        "resolutiondate": "2024-01-15T11:00:00.000+0000",
        "parent": {
            "id": "12344",
            "key": "PROJ-122",
            "fields": {"summary": "Parent Issue Summary"},
        },
        "subtasks": [
            {
                "id": "12346",
                "key": "PROJ-124",
                "fields": {"summary": "Subtask 1 Summary"},
            }
        ],
        "security": {"name": "Internal", "id": "10001"},
        "worklog": {"startAt": 0, "maxResults": 20, "total": 0, "worklogs": []},
        # Custom fields for testing
        "customfield_10011": "Epic Name Example",  # Epic Name
        "customfield_10014": "EPIC-KEY-1",  # Epic Link
        "customfield_10001": "Custom Text Field Value",
        "customfield_10002": {"value": "Custom Select Value"},
        "customfield_10003": [
            {"value": "Custom MultiSelect 1"},
            {"value": "Custom MultiSelect 2"},
        ],
    },
    "names": {
        "customfield_10011": "Epic Name",
        "customfield_10014": "Epic Link",
        "customfield_10001": "My Custom Text Field",
        "customfield_10002": "My Custom Select",
        "customfield_10003": "My Custom MultiSelect",
    },
}

MOCK_JIRA_JQL_RESPONSE = {
    "expand": "schema,names",
    "startAt": 0,
    "maxResults": 5,
    "total": 34,
    "issues": [
        {
            "expand": "operations,versionedRepresentations,editmeta,changelog,renderedFields",
            "id": "12345",
            "self": "https://example.atlassian.net/rest/api/2/issue/12345",
            "key": "PROJ-123",
            "fields": {
                "parent": {
                    "id": "12340",
                    "key": "PROJ-120",
                    "self": "https://example.atlassian.net/rest/api/2/issue/12340",
                    "fields": {
                        "summary": "Parent Epic Summary",
                        "status": {
                            "self": "https://example.atlassian.net/rest/api/2/status/10000",
                            "description": "",
                            "iconUrl": "https://example.atlassian.net/",
                            "name": "In Progress",
                            "id": "10000",
                            "statusCategory": {
                                "self": "https://example.atlassian.net/rest/api/2/statuscategory/4",
                                "id": 4,
                                "key": "indeterminate",
                                "colorName": "yellow",
                                "name": "In Progress",
                            },
                        },
                        "priority": {
                            "self": "https://example.atlassian.net/rest/api/2/priority/3",
                            "iconUrl": "https://example.atlassian.net/images/icons/priorities/medium.svg",
                            "name": "Medium",
                            "id": "3",
                        },
                        "issuetype": {
                            "self": "https://example.atlassian.net/rest/api/2/issuetype/10001",
                            "id": "10001",
                            "description": "Epics track large pieces of work.",
                            "iconUrl": "https://example.atlassian.net/images/icons/issuetypes/epic.svg",
                            "name": "Epic",
                            "subtask": False,
                            "hierarchyLevel": 1,
                        },
                    },
                },
                "summary": "Test Issue Summary",
                "description": "This is a test issue description",
                "created": "2024-01-01T10:00:00.000+0000",
                "updated": "2024-01-02T15:30:00.000+0000",
                "duedate": "2024-12-31",
                "priority": {
                    "self": "https://example.atlassian.net/rest/api/2/priority/3",
                    "iconUrl": "https://example.atlassian.net/images/icons/priorities/medium.svg",
                    "name": "Medium",
                    "id": "3",
                },
                "status": {
                    "self": "https://example.atlassian.net/rest/api/2/status/10000",
                    "description": "",
                    "iconUrl": "https://example.atlassian.net/",
                    "name": "In Progress",
                    "id": "10000",
                    "statusCategory": {
                        "self": "https://example.atlassian.net/rest/api/2/statuscategory/4",
                        "id": 4,
                        "key": "indeterminate",
                        "colorName": "yellow",
                        "name": "In Progress",
                    },
                },
                "issuetype": {
                    "self": "https://example.atlassian.net/rest/api/2/issuetype/10000",
                    "id": "10000",
                    "description": "A task that needs to be done.",
                    "iconUrl": "https://example.atlassian.net/images/icons/issuetypes/task.svg",
                    "name": "Task",
                    "subtask": False,
                    "hierarchyLevel": 0,
                },
                "project": {
                    "self": "https://example.atlassian.net/rest/api/2/project/10000",
                    "id": "10000",
                    "key": "PROJ",
                    "name": "Test Project",
                    "projectTypeKey": "software",
                    "simplified": True,
                },
                "comment": {
                    "comments": [
                        {
                            "self": "https://example.atlassian.net/rest/api/2/issue/12345/comment/10000",
                            "id": "10000",
                            "author": {"displayName": "Comment User", "active": True},
                            "body": "This is a test comment",
                            "created": "2024-01-01T12:00:00.000+0000",
                            "updated": "2024-01-01T12:00:00.000+0000",
                        }
                    ],
                    "maxResults": 1,
                    "total": 1,
                    "startAt": 0,
                },
            },
        }
    ],
    "names": {
        "customfield_10011": "Epic Name",
        "customfield_10014": "Epic Link",
    },
}

# Generic mock Jira comments data without any company-specific information
MOCK_JIRA_COMMENTS = {
    "startAt": 0,
    "maxResults": 100,
    "total": 5,
    "comments": [
        {
            "self": "https://example.atlassian.net/rest/api/2/issue/10001/comment/10101",
            "id": "10101",
            "author": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-1",
                "accountId": "account-id-1",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user1_48.png",
                    "24x24": "https://avatar.example.com/avatar/user1_24.png",
                    "16x16": "https://avatar.example.com/avatar/user1_16.png",
                    "32x32": "https://avatar.example.com/avatar/user1_32.png",
                },
                "displayName": "John Smith",
                "active": True,
                "timeZone": "UTC",
                "accountType": "atlassian",
            },
            "body": "I've analyzed this issue and found that we need to update the configuration settings.",
            "updateAuthor": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-1",
                "accountId": "account-id-1",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user1_48.png",
                    "24x24": "https://avatar.example.com/avatar/user1_24.png",
                    "16x16": "https://avatar.example.com/avatar/user1_16.png",
                    "32x32": "https://avatar.example.com/avatar/user1_32.png",
                },
                "displayName": "John Smith",
                "active": True,
                "timeZone": "UTC",
                "accountType": "atlassian",
            },
            "created": "2023-01-15T09:14:01.240+0000",
            "updated": "2023-01-15T09:14:15.433+0000",
            "jsdPublic": True,
        },
        {
            "self": "https://example.atlassian.net/rest/api/2/issue/10001/comment/10102",
            "id": "10102",
            "author": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-2",
                "accountId": "account-id-2",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user2_48.png",
                    "24x24": "https://avatar.example.com/avatar/user2_24.png",
                    "16x16": "https://avatar.example.com/avatar/user2_16.png",
                    "32x32": "https://avatar.example.com/avatar/user2_32.png",
                },
                "displayName": "Jane Doe",
                "active": True,
                "timeZone": "America/New_York",
                "accountType": "atlassian",
            },
            "body": "I agree with John. Let's schedule a meeting to discuss the implementation details.",
            "updateAuthor": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-2",
                "accountId": "account-id-2",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user2_48.png",
                    "24x24": "https://avatar.example.com/avatar/user2_24.png",
                    "16x16": "https://avatar.example.com/avatar/user2_16.png",
                    "32x32": "https://avatar.example.com/avatar/user2_32.png",
                },
                "displayName": "Jane Doe",
                "active": True,
                "timeZone": "America/New_York",
                "accountType": "atlassian",
            },
            "created": "2023-01-15T14:35:28.392+0000",
            "updated": "2023-01-15T14:35:28.392+0000",
            "jsdPublic": True,
        },
        {
            "self": "https://example.atlassian.net/rest/api/2/issue/10001/comment/10103",
            "id": "10103",
            "author": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-3",
                "accountId": "account-id-3",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user3_48.png",
                    "24x24": "https://avatar.example.com/avatar/user3_24.png",
                    "16x16": "https://avatar.example.com/avatar/user3_16.png",
                    "32x32": "https://avatar.example.com/avatar/user3_32.png",
                },
                "displayName": "Robert Johnson",
                "active": True,
                "timeZone": "Europe/London",
                "accountType": "atlassian",
            },
            "body": "I've created a draft implementation. Please review the code changes in the linked PR.",
            "updateAuthor": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-3",
                "accountId": "account-id-3",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user3_48.png",
                    "24x24": "https://avatar.example.com/avatar/user3_24.png",
                    "16x16": "https://avatar.example.com/avatar/user3_16.png",
                    "32x32": "https://avatar.example.com/avatar/user3_32.png",
                },
                "displayName": "Robert Johnson",
                "active": True,
                "timeZone": "Europe/London",
                "accountType": "atlassian",
            },
            "created": "2023-01-18T10:47:53.672+0000",
            "updated": "2023-01-18T11:01:55.589+0000",
            "jsdPublic": True,
        },
        {
            "self": "https://example.atlassian.net/rest/api/2/issue/10001/comment/10104",
            "id": "10104",
            "author": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-1",
                "accountId": "account-id-1",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user1_48.png",
                    "24x24": "https://avatar.example.com/avatar/user1_24.png",
                    "16x16": "https://avatar.example.com/avatar/user1_16.png",
                    "32x32": "https://avatar.example.com/avatar/user1_32.png",
                },
                "displayName": "John Smith",
                "active": True,
                "timeZone": "UTC",
                "accountType": "atlassian",
            },
            "body": "The code looks good. I've left some minor suggestions in the PR review.",
            "updateAuthor": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-1",
                "accountId": "account-id-1",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user1_48.png",
                    "24x24": "https://avatar.example.com/avatar/user1_24.png",
                    "16x16": "https://avatar.example.com/avatar/user1_16.png",
                    "32x32": "https://avatar.example.com/avatar/user1_32.png",
                },
                "displayName": "John Smith",
                "active": True,
                "timeZone": "UTC",
                "accountType": "atlassian",
            },
            "created": "2023-01-19T15:20:02.083+0000",
            "updated": "2023-01-19T15:20:02.083+0000",
            "jsdPublic": True,
        },
        {
            "self": "https://example.atlassian.net/rest/api/2/issue/10001/comment/10105",
            "id": "10105",
            "author": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-3",
                "accountId": "account-id-3",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user3_48.png",
                    "24x24": "https://avatar.example.com/avatar/user3_24.png",
                    "16x16": "https://avatar.example.com/avatar/user3_16.png",
                    "32x32": "https://avatar.example.com/avatar/user3_32.png",
                },
                "displayName": "Robert Johnson",
                "active": True,
                "timeZone": "Europe/London",
                "accountType": "atlassian",
            },
            "body": "I've addressed all the feedback and merged the PR. Issue can be closed.",
            "updateAuthor": {
                "self": "https://example.atlassian.net/rest/api/2/user?accountId=account-id-3",
                "accountId": "account-id-3",
                "avatarUrls": {
                    "48x48": "https://avatar.example.com/avatar/user3_48.png",
                    "24x24": "https://avatar.example.com/avatar/user3_24.png",
                    "16x16": "https://avatar.example.com/avatar/user3_16.png",
                    "32x32": "https://avatar.example.com/avatar/user3_32.png",
                },
                "displayName": "Robert Johnson",
                "active": True,
                "timeZone": "Europe/London",
                "accountType": "atlassian",
            },
            "created": "2023-01-20T11:10:38.167+0000",
            "updated": "2023-01-20T11:10:38.167+0000",
            "jsdPublic": True,
        },
    ],
}

# Create a simplified version for test use
MOCK_JIRA_COMMENTS_SIMPLIFIED = {
    "startAt": 0,
    "maxResults": 100,
    "total": MOCK_JIRA_COMMENTS["total"],
    "comments": [
        {
            "id": comment["id"],
            "author": {"displayName": comment["author"]["displayName"]},
            "body": comment["body"],
            "created": comment["created"],
            "updated": comment["updated"],
        }
        for comment in MOCK_JIRA_COMMENTS["comments"][:3]  # Just use first 3 comments
    ],
}

# Create simplified versions of the mock responses
MOCK_JIRA_ISSUE_RESPONSE_SIMPLIFIED = {
    "id": "12345",
    "self": "https://example.atlassian.net/rest/api/2/issue/12345",
    "key": "PROJ-123",
    "fields": {
        "summary": "Test Issue Summary",
        "description": "This is a test issue description",
        "created": "2024-01-01T10:00:00.000+0000",
        "updated": "2024-01-02T15:30:00.000+0000",
        "duedate": "2024-12-31",
        "priority": {
            "name": "Medium",
            "id": "3",
        },
        "status": {
            "name": "In Progress",
            "id": "10000",
            "statusCategory": {
                "id": 4,
                "key": "indeterminate",
                "name": "In Progress",
            },
        },
        "issuetype": {
            "id": "10000",
            "name": "Task",
            "subtask": False,
        },
        "project": {
            "id": "10000",
            "key": "PROJ",
            "name": "Test Project",
        },
        "comment": {
            "comments": [
                {
                    "id": "10000",
                    "author": {"displayName": "Comment User"},
                    "body": "This is a test comment",
                    "created": "2024-01-01T12:00:00.000+0000",
                    "updated": "2024-01-01T12:00:00.000+0000",
                }
            ],
            "total": 1,
        },
        "labels": ["test-label"],
        "fixVersions": [{"name": "v1.0"}],
        "attachment": [
            {
                "id": "10000",
                "filename": "test_attachment.txt",
                "author": {"displayName": "Test User"},
                "created": "2024-01-01T10:00:00.000+0000",
                "size": 1024,
                "mimeType": "text/plain",
                "content": "https://example.atlassian.net/secure/attachment/10000/test_attachment.txt",
            }
        ],
        "timetracking": {
            "originalEstimate": "1d",
            "remainingEstimate": "4h",
            "timeSpent": "4h",
        },
        "custom_fields": {
            "customfield_10011": "My Awesome Epic Name",
            "customfield_10014": "EPIC-123",
            "customfield_10001": "Simple string value",
            "customfield_10002": {"value": "Option value"},
            "customfield_10003": [{"value": "Item 1"}, {"value": "Item 2"}],
        },
    },
}

MOCK_JIRA_JQL_RESPONSE_SIMPLIFIED = {
    "startAt": 0,
    "maxResults": 5,
    "total": 34,
    "issues": [
        {
            "id": "12345",
            "key": "PROJ-123",
            "fields": {
                "parent": {
                    "id": "12340",
                    "key": "PROJ-120",
                    "fields": {
                        "summary": "Parent Epic Summary",
                        "status": {
                            "name": "In Progress",
                        },
                        "issuetype": {
                            "name": "Epic",
                            "subtask": False,
                        },
                    },
                },
                "summary": "Test Issue Summary",
                "description": "This is a test issue description",
                "created": "2024-01-01T10:00:00.000+0000",
                "updated": "2024-01-02T15:30:00.000+0000",
                "status": {
                    "name": "In Progress",
                },
                "issuetype": {
                    "name": "Task",
                    "subtask": False,
                },
                "project": {
                    "key": "PROJ",
                    "name": "Test Project",
                },
                "comment": {
                    "comments": [
                        {
                            "id": "10000",
                            "author": {"displayName": "Comment User"},
                            "body": "This is a test comment",
                            "created": "2024-01-01T12:00:00.000+0000",
                        }
                    ],
                    "total": 1,
                },
            },
        }
    ],
}
