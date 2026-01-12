"""Mock data for ProForma forms testing - New Forms REST API."""

# ============================================================================
# FORMS REST API FIXTURES
# ============================================================================

# Mock UUIDs for forms (new API format)
MOCK_FORM_UUID_1 = "1946b8b7-8f03-4dc0-ac2d-5fac0d960c6a"
MOCK_FORM_UUID_2 = "bad2fb1f-3e2d-4a1c-9f8e-7b6c5d4e3f2a"
MOCK_FORM_UUID_3 = "e4644a12-7c3b-4d9e-a1f0-2b3c4d5e6f7g"

# Mock CloudId
MOCK_CLOUD_ID = "d30daf5c-29ad-4817-bd10-bdd85ae8455f"

# Mock form list response (GET /issue/{key}/form)
MOCK_NEW_API_FORMS_LIST = [
    {
        "id": MOCK_FORM_UUID_1,
        "formTemplate": "template-uuid-123",
        "internal": False,
        "submitted": False,
        "lock": False,
        "name": "1. Reporter - Fields Submitted At Intake",
        "updated": "2025-01-15T10:30:00.000Z",
    },
    {
        "id": MOCK_FORM_UUID_2,
        "formTemplate": "template-uuid-456",
        "internal": False,
        "submitted": True,
        "lock": False,
        "name": "0. Status Update",
        "updated": "2025-01-14T15:20:00.000Z",
    },
    {
        "id": MOCK_FORM_UUID_3,
        "formTemplate": "template-uuid-789",
        "internal": True,
        "submitted": False,
        "lock": False,
        "name": "2. Issue Management/Compliance Triage Form",
        "updated": "2025-01-13T09:15:00.000Z",
    },
]

# Mock ADF design structure (simplified for testing)
MOCK_ADF_DESIGN = {
    "conditions": {"version": 1, "rules": []},
    "layout": [
        {
            "type": "panel",
            "attrs": {"panelType": "info"},
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Please provide detailed information"}
                    ],
                }
            ],
        },
        {
            "type": "question",
            "attrs": {"questionId": "q1", "questionType": "TEXT"},
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Description"}],
                }
            ],
        },
    ],
    "questions": {
        "q1": {"id": "q1", "type": "TEXT", "required": True, "label": "Description"},
        "q2": {
            "id": "q2",
            "type": "SELECT",
            "required": True,
            "label": "Impacted Product/Service",
            "options": ["Product A", "Product B", "Service X", "Service Y"],
        },
    },
    "sections": [],
    "settings": {"version": 1},
}

# Mock form details response (GET /issue/{key}/form/{formId})
MOCK_NEW_API_FORM_DETAILS = {
    "id": MOCK_FORM_UUID_1,
    "updated": "2025-01-15T10:30:00.000Z",
    "design": MOCK_ADF_DESIGN,
}

# Mock form with submission
MOCK_NEW_API_FORM_SUBMITTED = {
    "id": MOCK_FORM_UUID_2,
    "formTemplate": "template-uuid-456",
    "internal": False,
    "submitted": True,
    "lock": False,
    "name": "0. Status Update",
    "updated": "2025-01-14T15:20:00.000Z",
}

# Mock update answers request/response (PUT /issue/{key}/form/{formId})
MOCK_UPDATE_ANSWERS_REQUEST = {
    "answers": [
        {"questionId": "q1", "type": "TEXT", "value": "Updated description text"},
        {"questionId": "q2", "type": "SELECT", "value": "Product A"},
    ]
}

MOCK_UPDATE_ANSWERS_RESPONSE = {
    "success": True,
    "message": "Form answers updated successfully",
}

# Mock add template request/response (POST /issue/{key}/form)
MOCK_ADD_TEMPLATE_REQUEST = {"formTemplateId": "template-uuid-999"}

MOCK_ADD_TEMPLATE_RESPONSE = {
    "id": "new-form-uuid-abc",
    "formTemplate": "template-uuid-999",
    "internal": False,
    "submitted": False,
    "lock": False,
    "name": "New Form from Template",
    "updated": "2025-01-16T11:00:00.000Z",
}

# Mock attachments response (GET /issue/{key}/form/{formId}/attachment)
MOCK_FORM_ATTACHMENTS = [
    {
        "id": "attachment-uuid-1",
        "filename": "document.pdf",
        "size": 102400,
        "mimeType": "application/pdf",
        "created": "2025-01-15T10:35:00.000Z",
    },
    {
        "id": "attachment-uuid-2",
        "filename": "screenshot.png",
        "size": 524288,
        "mimeType": "image/png",
        "created": "2025-01-15T10:40:00.000Z",
    },
]

# API endpoint patterns for new Forms REST API
FORMS_REST_API_PATTERNS = {
    "base": "https://api.atlassian.com/jira/forms/cloud/{cloud_id}",
    "get_issue_forms": "/issue/{issue_key}/form",
    "get_form_details": "/issue/{issue_key}/form/{form_id}",
    "update_form_answers": "/issue/{issue_key}/form/{form_id}",  # PUT
    "add_form_template": "/issue/{issue_key}/form",  # POST
    "delete_form": "/issue/{issue_key}/form/{form_id}",  # DELETE
    "get_attachments": "/issue/{issue_key}/form/{form_id}/attachment",
    "export_pdf": "/issue/{issue_key}/form/{form_id}/format/pdf",
    "export_xlsx": "/issue/{issue_key}/form/{form_id}/format/xlsx",
}

# Mock error responses
MOCK_FORM_NOT_FOUND_ERROR = {
    "status_code": 404,
    "message": "Form not found",
    "errors": [{"message": "The specified form does not exist"}],
}

MOCK_FORM_PERMISSION_ERROR = {
    "status_code": 403,
    "message": "Insufficient permissions",
    "errors": [{"message": "You do not have permission to access this form"}],
}

MOCK_FORM_VALIDATION_ERROR = {
    "status_code": 400,
    "message": "Validation error",
    "errors": [{"message": "Required field is missing or invalid"}],
}
