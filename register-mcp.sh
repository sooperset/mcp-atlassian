#!/usr/bin/env sh
# Registers mcp-atlassian as a global Claude Code MCP server using credentials from .env

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE not found. Copy .env.example to .env and fill in credentials." >&2
  exit 1
fi

# Parse .env — skip comments and blank lines, no subshell needed
while IFS='=' read -r key value; do
  case "$key" in
    '#'*|'') continue ;;
  esac
  # Strip inline comments and leading/trailing whitespace from value
  value="${value%%#*}"
  value="${value#"${value%%[! ]*}"}"
  value="${value%"${value##*[! ]}"}"
  export "$key=$value"
done < "$ENV_FILE"

# Validate required vars
missing=""
for var in JIRA_URL CONFLUENCE_URL; do
  eval "val=\$$var"
  [ -z "$val" ] && missing="$missing $var"
done
if [ -n "$missing" ]; then
  echo "Error: Missing required vars in .env:$missing" >&2
  exit 1
fi

# Build -e flags for all set Atlassian vars
env_flags=""
for var in \
  JIRA_URL JIRA_USERNAME JIRA_API_TOKEN JIRA_PERSONAL_TOKEN \
  CONFLUENCE_URL CONFLUENCE_USERNAME CONFLUENCE_API_TOKEN CONFLUENCE_PERSONAL_TOKEN \
  ATLASSIAN_OAUTH_CLIENT_ID ATLASSIAN_OAUTH_CLIENT_SECRET ATLASSIAN_OAUTH_REDIRECT_URI \
  ATLASSIAN_OAUTH_SCOPE ATLASSIAN_OAUTH_CLOUD_ID ATLASSIAN_OAUTH_ACCESS_TOKEN \
  READ_ONLY_MODE TOOLSETS ENABLED_TOOLS \
  CONFLUENCE_SPACES_FILTER JIRA_PROJECTS_FILTER; do
  eval "val=\$$var"
  [ -n "$val" ] && env_flags="$env_flags -e $var=$val"
done

echo "Registering mcp-atlassian (user scope)..."

# shellcheck disable=SC2086
claude mcp add mcp-atlassian \
  --scope user \
  $env_flags \
  -- uv run --directory "$SCRIPT_DIR" mcp-atlassian

echo "Done. Restart Claude Code or run /mcp to reload."
