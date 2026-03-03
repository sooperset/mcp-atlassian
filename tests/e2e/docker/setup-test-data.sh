#!/usr/bin/env bash
# Create test data in Jira and Confluence DC via REST API.
# Idempotent: checks for existing resources before creating.
# Requires: setup wizard completed, admin user created.
# Usage: bash setup-test-data.sh

set -euo pipefail

JIRA_BASE="${JIRA_BASE_URL:-http://localhost:8080}"
CONFLUENCE_BASE="${CONFLUENCE_BASE_URL:-http://localhost:8090}"
AUTH="${DC_ADMIN_CREDENTIALS:-admin:admin123}"
PROJECT_KEY="E2E"
SPACE_KEY="E2E"

# Helper: check HTTP status
check_exists() {
  local url="$1"
  local status
  status=$(curl -s -o /dev/null -w '%{http_code}' -u "$AUTH" "$url" 2>/dev/null)
  [ "$status" = "200" ]
}

# Helper: detect Epic Name custom field ID
detect_epic_name_field() {
  local field_id
  field_id=$(curl -s -u "$AUTH" "${JIRA_BASE}/rest/api/2/field" | \
    python3 -c "
import sys, json
fields = json.load(sys.stdin)
for f in fields:
    if f.get('name') == 'Epic Name':
        print(f['id'])
        sys.exit(0)
print('customfield_10011')  # fallback
" 2>/dev/null)
  echo "$field_id"
}

echo "=== Jira: Create E2E project ==="
if check_exists "${JIRA_BASE}/rest/api/2/project/${PROJECT_KEY}"; then
  echo "Project ${PROJECT_KEY} already exists, skipping."
else
  jira_project=$(curl -s -u "$AUTH" \
    -H "Content-Type: application/json" \
    -X POST "${JIRA_BASE}/rest/api/2/project" \
    -d "{
      \"key\": \"${PROJECT_KEY}\",
      \"name\": \"E2E Test Project\",
      \"projectTypeKey\": \"software\",
      \"lead\": \"admin\"
    }")
  echo "Project: $jira_project"
fi

echo ""
echo "=== Jira: Create Task issue ==="
# Check if any issue exists in E2E project
existing_issues=$(curl -s -u "$AUTH" \
  "${JIRA_BASE}/rest/api/2/search?jql=project%3D${PROJECT_KEY}%20AND%20summary~%22E2E%20Test%20Task%22&maxResults=1" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null || echo "0")

if [ "$existing_issues" != "0" ]; then
  echo "E2E Test Task already exists, skipping."
  jira_issue_key=$(curl -s -u "$AUTH" \
    "${JIRA_BASE}/rest/api/2/search?jql=project%3D${PROJECT_KEY}%20AND%20summary~%22E2E%20Test%20Task%22&maxResults=1" | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['issues'][0]['key'])" 2>/dev/null)
  echo "Existing issue: ${jira_issue_key}"
else
  jira_issue=$(curl -s -u "$AUTH" \
    -H "Content-Type: application/json" \
    -X POST "${JIRA_BASE}/rest/api/2/issue" \
    -d "{
      \"fields\": {
        \"project\": {\"key\": \"${PROJECT_KEY}\"},
        \"summary\": \"E2E Test Task\",
        \"issuetype\": {\"name\": \"Task\"},
        \"description\": \"Created by setup-test-data.sh for E2E testing.\"
      }
    }")
  echo "Issue: $jira_issue"
fi

echo ""
echo "=== Jira: Create Epic ==="
EPIC_NAME_FIELD=$(detect_epic_name_field)
echo "Detected Epic Name field: ${EPIC_NAME_FIELD}"

existing_epics=$(curl -s -u "$AUTH" \
  "${JIRA_BASE}/rest/api/2/search?jql=project%3D${PROJECT_KEY}%20AND%20issuetype%3DEpic%20AND%20summary~%22E2E%20Test%20Epic%22&maxResults=1" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))" 2>/dev/null || echo "0")

if [ "$existing_epics" != "0" ]; then
  echo "E2E Test Epic already exists, skipping."
else
  jira_epic=$(curl -s -u "$AUTH" \
    -H "Content-Type: application/json" \
    -X POST "${JIRA_BASE}/rest/api/2/issue" \
    -d "{
      \"fields\": {
        \"project\": {\"key\": \"${PROJECT_KEY}\"},
        \"summary\": \"E2E Test Epic\",
        \"issuetype\": {\"name\": \"Epic\"},
        \"${EPIC_NAME_FIELD}\": \"E2E Epic Name\"
      }
    }")
  echo "Epic: $jira_epic"
fi

echo ""
echo "=== Confluence: Create E2E space ==="
if check_exists "${CONFLUENCE_BASE}/rest/api/space/${SPACE_KEY}"; then
  echo "Space ${SPACE_KEY} already exists, skipping."
else
  confluence_space=$(curl -s -u "$AUTH" \
    -H "Content-Type: application/json" \
    -X POST "${CONFLUENCE_BASE}/rest/api/space" \
    -d "{
      \"key\": \"${SPACE_KEY}\",
      \"name\": \"E2E Test Space\",
      \"description\": {
        \"plain\": {
          \"value\": \"Space for E2E testing\",
          \"representation\": \"plain\"
        }
      }
    }")
  echo "Space: $confluence_space"
fi

echo ""
echo "=== Confluence: Create test page ==="
existing_pages=$(curl -s -u "$AUTH" \
  "${CONFLUENCE_BASE}/rest/api/content?spaceKey=${SPACE_KEY}&title=E2E+Test+Page&limit=1" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('size',0))" 2>/dev/null || echo "0")

if [ "$existing_pages" != "0" ]; then
  echo "E2E Test Page already exists, skipping."
else
  confluence_page=$(curl -s -u "$AUTH" \
    -H "Content-Type: application/json" \
    -X POST "${CONFLUENCE_BASE}/rest/api/content" \
    -d "{
      \"type\": \"page\",
      \"title\": \"E2E Test Page\",
      \"space\": {\"key\": \"${SPACE_KEY}\"},
      \"body\": {
        \"storage\": {
          \"value\": \"<p>This page was created by setup-test-data.sh for E2E testing.</p>\",
          \"representation\": \"storage\"
        }
      }
    }")
  echo "Page: $confluence_page"
fi

echo ""
echo "=== Summary ==="
echo "Jira Project:     ${PROJECT_KEY}"
echo "Confluence Space:  ${SPACE_KEY}"
echo ""
echo "Run 'bash create-pat.sh' next to create PAT tokens."
