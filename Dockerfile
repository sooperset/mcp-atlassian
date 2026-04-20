# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.13-alpine AS uv

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Generate proper TOML lockfile first
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv lock

# Install the project's dependencies using the lockfile
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev --no-editable

# Then, copy the rest of the project source code and install it
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-editable

# Remove unnecessary files from the virtual environment before copying
RUN find /app/.venv -name '__pycache__' -type d -exec rm -rf {} + && \
    find /app/.venv -name '*.pyc' -delete && \
    find /app/.venv -name '*.pyo' -delete && \
    echo "Cleaned up .venv"

# Final stage
FROM python:3.13-alpine

# Create a non-root user 'app'
RUN adduser -D -h /home/app -s /bin/sh app
WORKDIR /app
USER app

COPY --from=uv --chown=app:app /app/.venv /app/.venv

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Disable Python output buffering for proper stdio communication
ENV PYTHONUNBUFFERED=1

# Multi-user mode: server holds no credentials; each client supplies its own
# per request via headers. Example:
#   docker run -p 9000:9000 \
#     -e JIRA_URL=https://your-company.atlassian.net \
#     -e CONFLUENCE_URL=https://your-company.atlassian.net/wiki \
#     -e MCP_ATLASSIAN_MULTI_USER_MODE=true \
#     your-image --transport streamable-http --port 9000
# Clients then send one of:
#   Authorization: Basic <base64(email:api_token)>   (Cloud)
#   Authorization: Bearer <oauth_token>              (Cloud)
#   Authorization: Token <personal_access_token>     (Server/DC)

ENTRYPOINT ["mcp-atlassian"]
