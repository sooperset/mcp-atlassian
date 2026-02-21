#!/usr/bin/env bash
# Wait for Jira and Confluence DC to become ready.
# Usage: bash healthcheck.sh
# Override timeout: HEALTHCHECK_TIMEOUT=600 bash healthcheck.sh

set -euo pipefail

JIRA_URL="${JIRA_BASE_URL:-http://localhost:8080}/status"
CONFLUENCE_URL="${CONFLUENCE_BASE_URL:-http://localhost:8090}/status"
INTERVAL=5
MAX_WAIT="${HEALTHCHECK_TIMEOUT:-300}"

wait_for_service() {
  local name="$1"
  local url="$2"
  local elapsed=0

  echo "Waiting for ${name} at ${url} ..."
  while [ "$elapsed" -lt "$MAX_WAIT" ]; do
    status=$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)
    if [ "$status" = "200" ]; then
      echo "${name} is ready! (${elapsed}s)"
      return 0
    fi
    sleep "$INTERVAL"
    elapsed=$((elapsed + INTERVAL))
    printf "  %ds / %ds (HTTP %s)\n" "$elapsed" "$MAX_WAIT" "$status"
  done

  echo "ERROR: ${name} did not become ready within ${MAX_WAIT}s"
  return 1
}

wait_for_service "Jira" "$JIRA_URL"
wait_for_service "Confluence" "$CONFLUENCE_URL"

echo ""
echo "All services are ready!"
echo "  Jira:       ${JIRA_BASE_URL:-http://localhost:8080}"
echo "  Confluence:  ${CONFLUENCE_BASE_URL:-http://localhost:8090}"
