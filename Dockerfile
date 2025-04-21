# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.10-bookworm-slim AS uv

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Copy only necessary files for dependency installation
COPY pyproject.toml uv.lock ./

# Install the project's dependencies using the lockfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --no-editable

# Copy the rest of the application code
COPY . .

# Install the project itself, skipping already installed dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-deps

FROM python:3.10-slim

# Create a non-root user
RUN groupadd --system --gid 1001 app && \
    useradd --system --uid 1001 --gid 1001 --no-create-home --shell /sbin/nologin app

WORKDIR /app

# Copy virtual environment from the build stage
COPY --from=uv --chown=app:app /app/.venv /app/.venv

# Copy application code
COPY --from=uv --chown=app:app /app /app

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER app

ENTRYPOINT ["mcp-atlassian"]
