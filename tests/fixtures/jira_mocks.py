MOCK_JIRA_ISSUE_RESPONSE = {
    'expand': 'renderedFields,names,schema,operations,editmeta,changelog,versionedRepresentations',
    'id': '12345',
    'self': 'https://example.atlassian.net/rest/api/2/issue/12345',
    'key': 'PROJ-123',
    'fields': {
        'summary': 'Test Issue Summary',
        'description': 'This is a test issue description',
        'created': '2024-01-01T10:00:00.000+0000',
        'updated': '2024-01-02T15:30:00.000+0000',
        'duedate': '2024-12-31',
        'priority': {
            'self': 'https://example.atlassian.net/rest/api/2/priority/3',
            'iconUrl': 'https://example.atlassian.net/images/icons/priorities/medium.svg',
            'name': 'Medium',
            'id': '3'
        },
        'status': {
            'self': 'https://example.atlassian.net/rest/api/2/status/10000',
            'description': '',
            'iconUrl': 'https://example.atlassian.net/',
            'name': 'In Progress',
            'id': '10000',
            'statusCategory': {
                'self': 'https://example.atlassian.net/rest/api/2/statuscategory/4',
                'id': 4,
                'key': 'indeterminate',
                'colorName': 'yellow',
                'name': 'In Progress'
            }
        },
        'issuetype': {
            'self': 'https://example.atlassian.net/rest/api/2/issuetype/10000',
            'id': '10000',
            'description': 'A task that needs to be done.',
            'iconUrl': 'https://example.atlassian.net/images/icons/issuetypes/task.svg',
            'name': 'Task',
            'subtask': False,
            'avatarId': 10318,
            'hierarchyLevel': 0
        },
        'project': {
            'self': 'https://example.atlassian.net/rest/api/2/project/10000',
            'id': '10000',
            'key': 'PROJ',
            'name': 'Test Project',
            'projectTypeKey': 'software',
            'simplified': True,
            'avatarUrls': {
                '48x48': 'https://example.atlassian.net/secure/projectavatar?size=large&pid=10000',
                '24x24': 'https://example.atlassian.net/secure/projectavatar?size=small&pid=10000',
                '16x16': 'https://example.atlassian.net/secure/projectavatar?size=xsmall&pid=10000',
                '32x32': 'https://example.atlassian.net/secure/projectavatar?size=medium&pid=10000'
            }
        },
        'assignee': {
            'self': 'https://example.atlassian.net/rest/api/2/user?accountId=123456789',
            'accountId': '123456789',
            'emailAddress': 'user@example.com',
            'avatarUrls': {
                '48x48': 'https://secure.gravatar.com/avatar/123?d=https%3A%2F%2Favatar.example.com%2Fdefault.png',
                '24x24': 'https://secure.gravatar.com/avatar/123?d=https%3A%2F%2Favatar.example.com%2Fdefault.png',
                '16x16': 'https://secure.gravatar.com/avatar/123?d=https%3A%2F%2Favatar.example.com%2Fdefault.png',
                '32x32': 'https://secure.gravatar.com/avatar/123?d=https%3A%2F%2Favatar.example.com%2Fdefault.png'
            },
            'displayName': 'Test User',
            'active': True,
            'timeZone': 'UTC',
            'accountType': 'atlassian'
        },
        'reporter': {
            'self': 'https://example.atlassian.net/rest/api/2/user?accountId=987654321',
            'accountId': '987654321',
            'avatarUrls': {
                '48x48': 'https://secure.gravatar.com/avatar/456?d=https%3A%2F%2Favatar.example.com%2Fdefault.png',
                '24x24': 'https://secure.gravatar.com/avatar/456?d=https%3A%2F%2Favatar.example.com%2Fdefault.png',
                '16x16': 'https://secure.gravatar.com/avatar/456?d=https%3A%2F%2Favatar.example.com%2Fdefault.png',
                '32x32': 'https://secure.gravatar.com/avatar/456?d=https%3A%2F%2Favatar.example.com%2Fdefault.png'
            },
            'displayName': 'Reporter User',
            'active': True,
            'timeZone': 'UTC',
            'accountType': 'atlassian'
        },
        'comment': {
            'comments': [
                {
                    'self': 'https://example.atlassian.net/rest/api/2/issue/12345/comment/10000',
                    'id': '10000',
                    'author': {
                        'displayName': 'Comment User',
                        'active': True
                    },
                    'body': 'This is a test comment',
                    'created': '2024-01-01T12:00:00.000+0000',
                    'updated': '2024-01-01T12:00:00.000+0000'
                }
            ],
            'maxResults': 1,
            'total': 1,
            'startAt': 0
        },
        'labels': ['test-label'],
        'timetracking': {},
        'security': None,
        'attachment': [],
        'worklog': {
            'startAt': 0,
            'maxResults': 20,
            'total': 0,
            'worklogs': []
        }
    }
}

MOCK_JIRA_JQL_RESPONSE = {
    'expand': 'schema,names',
    'startAt': 0,
    'maxResults': 5,
    'total': 34,
    'issues': [
        {
            'expand': 'operations,versionedRepresentations,editmeta,changelog,renderedFields',
            'id': '12345',
            'self': 'https://example.atlassian.net/rest/api/2/issue/12345',
            'key': 'PROJ-123',
            'fields': {
                'parent': {
                    'id': '12340',
                    'key': 'PROJ-120',
                    'self': 'https://example.atlassian.net/rest/api/2/issue/12340',
                    'fields': {
                        'summary': 'Parent Epic Summary',
                        'status': {
                            'self': 'https://example.atlassian.net/rest/api/2/status/10000',
                            'description': '',
                            'iconUrl': 'https://example.atlassian.net/',
                            'name': 'In Progress',
                            'id': '10000',
                            'statusCategory': {
                                'self': 'https://example.atlassian.net/rest/api/2/statuscategory/4',
                                'id': 4,
                                'key': 'indeterminate',
                                'colorName': 'yellow',
                                'name': 'In Progress'
                            }
                        },
                        'priority': {
                            'self': 'https://example.atlassian.net/rest/api/2/priority/3',
                            'iconUrl': 'https://example.atlassian.net/images/icons/priorities/medium.svg',
                            'name': 'Medium',
                            'id': '3'
                        },
                        'issuetype': {
                            'self': 'https://example.atlassian.net/rest/api/2/issuetype/10001',
                            'id': '10001',
                            'description': 'Epics track large pieces of work.',
                            'iconUrl': 'https://example.atlassian.net/images/icons/issuetypes/epic.svg',
                            'name': 'Epic',
                            'subtask': False,
                            'hierarchyLevel': 1
                        }
                    }
                },
                'summary': 'Test Issue Summary',
                'description': 'This is a test issue description',
                'created': '2024-01-01T10:00:00.000+0000',
                'updated': '2024-01-02T15:30:00.000+0000',
                'duedate': '2024-12-31',
                'priority': {
                    'self': 'https://example.atlassian.net/rest/api/2/priority/3',
                    'iconUrl': 'https://example.atlassian.net/images/icons/priorities/medium.svg',
                    'name': 'Medium',
                    'id': '3'
                },
                'status': {
                    'self': 'https://example.atlassian.net/rest/api/2/status/10000',
                    'description': '',
                    'iconUrl': 'https://example.atlassian.net/',
                    'name': 'In Progress',
                    'id': '10000',
                    'statusCategory': {
                        'self': 'https://example.atlassian.net/rest/api/2/statuscategory/4',
                        'id': 4,
                        'key': 'indeterminate',
                        'colorName': 'yellow',
                        'name': 'In Progress'
                    }
                },
                'issuetype': {
                    'self': 'https://example.atlassian.net/rest/api/2/issuetype/10000',
                    'id': '10000',
                    'description': 'A task that needs to be done.',
                    'iconUrl': 'https://example.atlassian.net/images/icons/issuetypes/task.svg',
                    'name': 'Task',
                    'subtask': False,
                    'hierarchyLevel': 0
                },
                'project': {
                    'self': 'https://example.atlassian.net/rest/api/2/project/10000',
                    'id': '10000',
                    'key': 'PROJ',
                    'name': 'Test Project',
                    'projectTypeKey': 'software',
                    'simplified': True
                },
                'comment': {
                    'comments': [
                        {
                            'self': 'https://example.atlassian.net/rest/api/2/issue/12345/comment/10000',
                            'id': '10000',
                            'author': {
                                'displayName': 'Comment User',
                                'active': True
                            },
                            'body': 'This is a test comment',
                            'created': '2024-01-01T12:00:00.000+0000',
                            'updated': '2024-01-01T12:00:00.000+0000'
                        }
                    ],
                    'maxResults': 1,
                    'total': 1,
                    'startAt': 0
                }
            }
        }
    ]
}