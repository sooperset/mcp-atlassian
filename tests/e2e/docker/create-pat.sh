#!/usr/bin/env bash
# Create Personal Access Tokens (PATs) for Jira and Confluence DC.
# Jira PAT: POST /rest/pat/latest/tokens (Jira 8.14+)
# Confluence PAT: POST /rest/de.resolution.apitokenauth/1.0/user/token
# Usage: bash create-pat.sh

set -euo pipefail

JIRA_BASE="${JIRA_BASE_URL:-http://localhost:8080}"
CONFLUENCE_BASE="${CONFLUENCE_BASE_URL:-http://localhost:8090}"
AUTH="${DC_ADMIN_CREDENTIALS:-admin:admin123}"
TOKEN_NAME="${PAT_TOKEN_NAME:-e2e-test-token}"

echo "=== Jira: Create Personal Access Token ==="
jira_pat_response=$(curl -s -u "$AUTH" \
  -H "Content-Type: application/json" \
  -X POST "${JIRA_BASE}/rest/pat/latest/tokens" \
  -d "{
    \"name\": \"${TOKEN_NAME}\",
    \"expirationDuration\": 90
  }")

JIRA_PAT=$(echo "$jira_pat_response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'rawToken' in data:
    print(data['rawToken'])
elif 'token' in data:
    print(data['token'])
else:
    print('ERROR: ' + json.dumps(data), file=sys.stderr)
    sys.exit(1)
" 2>/dev/null) || true

if [ -n "$JIRA_PAT" ]; then
  echo "Jira PAT created successfully."
  echo "  Token: ${JIRA_PAT}"
else
  echo "WARNING: Failed to create Jira PAT."
  echo "  Response: ${jira_pat_response}"
fi

echo ""
echo "=== Confluence: Create Personal Access Token ==="
confluence_pat_response=$(curl -s -u "$AUTH" \
  -H "Content-Type: application/json" \
  -X POST "${CONFLUENCE_BASE}/rest/de.resolution.apitokenauth/1.0/user/token" \
  -d "{
    \"tokenName\": \"${TOKEN_NAME}\"
  }")

CONFLUENCE_PAT=$(echo "$confluence_pat_response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'rawToken' in data:
    print(data['rawToken'])
elif 'token' in data:
    print(data['token'])
else:
    print('ERROR: ' + json.dumps(data), file=sys.stderr)
    sys.exit(1)
" 2>/dev/null) || true

if [ -n "$CONFLUENCE_PAT" ]; then
  echo "Confluence PAT created successfully."
  echo "  Token: ${CONFLUENCE_PAT}"
else
  echo "WARNING: Failed to create Confluence PAT."
  echo "  Response: ${confluence_pat_response}"
fi

echo ""
echo "=== Export these for the E2E test suite ==="
echo "export JIRA_PERSONAL_TOKEN=\"${JIRA_PAT:-<failed>}\""
echo "export CONFLUENCE_PERSONAL_TOKEN=\"${CONFLUENCE_PAT:-<failed>}\""
