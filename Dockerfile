# Generated by https://smithery.ai. See: https://smithery.ai/docs/config#dockerfile
# Use a Python image with version >= 3.10
FROM python:3.10-slim AS base

# Set the working directory
WORKDIR /app

# Copy the project files
COPY . .

# Install the dependencies from pyproject.toml
RUN pip install hatchling && \
    pip install .

# Set environment variables
ENV CONFLUENCE_URL=https://your-domain.atlassian.net/wiki
ENV CONFLUENCE_USERNAME=your.email@domain.com
ENV CONFLUENCE_API_TOKEN=your_api_token
ENV JIRA_URL=https://your-domain.atlassian.net
ENV JIRA_USERNAME=your.email@domain.com
ENV JIRA_API_TOKEN=your_api_token

# Run the application
ENTRYPOINT ["python", "-m", "mcp_atlassian"]
