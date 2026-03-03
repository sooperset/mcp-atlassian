# MCP Atlassian Docker Usage Guide

This guide shows how to use the MCP Atlassian integration Docker image for your company.

## Quick Start

### Pull the Image

```bash
# Once the GitHub Actions workflow completes, the image will be available at:
docker pull ghcr.io/mliq/mcp-atlassian:latest

# Alternative: build locally from source
git clone https://github.com/mliq/mcp-atlassian.git
cd mcp-atlassian
docker build -t mcp-atlassian .
```

### Basic Usage

#### For Atlassian Cloud (OAuth)
```bash
docker run -e ATLASSIAN_OAUTH_ENABLE=true -p 8000:8000 ghcr.io/mliq/mcp-atlassian:latest
```

Then provide authentication via headers:
- `Authorization: Bearer <your_oauth_token>`
- `X-Atlassian-Cloud-Id: <your_cloud_id>`

#### For Jira Cloud (API Token)
```bash
docker run \
  -e JIRA_URL=https://your-company.atlassian.net \
  -e JIRA_USERNAME=your-email@company.com \
  -e JIRA_TOKEN=your_api_token \
  -p 8000:8000 \
  ghcr.io/mliq/mcp-atlassian:latest
```

#### For Confluence Cloud (API Token)
```bash
docker run \
  -e CONFLUENCE_URL=https://your-company.atlassian.net/wiki \
  -e CONFLUENCE_USERNAME=your-email@company.com \
  -e CONFLUENCE_TOKEN=your_api_token \
  -p 8000:8000 \
  ghcr.io/mliq/mcp-atlassian:latest
```

#### For On-Premise Jira Server
```bash
docker run \
  -e JIRA_URL=https://jira.your-company.com \
  -e JIRA_PERSONAL_TOKEN=your_personal_access_token \
  -p 8000:8000 \
  ghcr.io/mliq/mcp-atlassian:latest
```

## Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `JIRA_URL` | Jira instance URL | Yes (for Jira) | `https://company.atlassian.net` |
| `JIRA_USERNAME` | Jira username/email (Cloud only) | Yes (Cloud) | `user@company.com` |
| `JIRA_TOKEN` | Jira API token (Cloud only) | Yes (Cloud) | `ATATT3x...` |
| `JIRA_PERSONAL_TOKEN` | Personal Access Token (Server/DC) | Yes (Server) | `your_pat_token` |
| `CONFLUENCE_URL` | Confluence instance URL | Yes (for Confluence) | `https://company.atlassian.net/wiki` |
| `CONFLUENCE_USERNAME` | Confluence username/email | Yes (Cloud) | `user@company.com` |
| `CONFLUENCE_TOKEN` | Confluence API token | Yes (Cloud) | `ATATT3x...` |
| `ATLASSIAN_OAUTH_ENABLE` | Enable OAuth mode | No | `true` |
| `ENABLED_TOOLS` | Comma-separated list of enabled tools | No | `jira_search,create_issue` |
| `READ_ONLY` | Enable read-only mode | No | `true` |

## Transport Modes

### SSE (Server-Sent Events) - Default
```bash
docker run -p 8000:8000 ghcr.io/mliq/mcp-atlassian:latest --transport sse
```
Access at: `http://localhost:8000/sse`

### Streamable HTTP
```bash
docker run -p 8000:8000 ghcr.io/mliq/mcp-atlassian:latest --transport streamable-http --path /mcp
```
Access at: `http://localhost:8000/mcp`

### STDIO (for direct integration)
```bash
docker run ghcr.io/mliq/mcp-atlassian:latest --transport stdio
```

## Docker Compose Example

Create a `docker-compose.yml` file:

```yaml
version: '3.8'
services:
  mcp-atlassian:
    image: ghcr.io/mliq/mcp-atlassian:latest
    ports:
      - "8000:8000"
    environment:
      - JIRA_URL=https://your-company.atlassian.net
      - JIRA_USERNAME=your-email@company.com
      - JIRA_TOKEN=your_api_token
      - CONFLUENCE_URL=https://your-company.atlassian.net/wiki
      - CONFLUENCE_USERNAME=your-email@company.com
      - CONFLUENCE_TOKEN=your_api_token
    restart: unless-stopped
```

Run with:
```bash
docker-compose up -d
```

## Available Tools

The MCP server provides these tools:
- **Jira**: Search issues, create issues, update issues, add comments, manage transitions
- **Confluence**: Search pages, create pages, update pages, manage attachments

## Security Notes

- Store API tokens securely (use Docker secrets in production)
- The container runs as non-root user for security
- For production, consider using environment files instead of command-line arguments

## Troubleshooting

### Check container logs:
```bash
docker logs <container_id>
```

### Test connection:
```bash
docker run --rm ghcr.io/mliq/mcp-atlassian:latest --help
```

### Enable verbose logging:
```bash
docker run -e LOG_LEVEL=DEBUG ghcr.io/mliq/mcp-atlassian:latest -v
```

## Available Tags

- `latest` - Latest stable release
- `v0.9.1` - Specific version
- `main` - Latest development build

## Development & Manual Building

### Building the Image Locally

#### Simple Single-Platform Build
```bash
# Build for your current platform (fastest option)
docker build -t ghcr.io/mliq/mcp-atlassian:latest .
```

#### Multi-Platform Build (like CI/CD)
```bash
# Set up buildx for multi-platform builds
docker buildx create --use

# Build for both Intel and ARM architectures
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/mliq/mcp-atlassian:latest \
  --load .
```

### Manual Publishing to Registry

#### Prerequisites
1. GitHub token with `write:packages` scope
2. Login to GitHub Container Registry:
```bash
gh auth token | docker login ghcr.io -u mliq --password-stdin
```

#### Push to Registry
```bash
# Push single platform build
docker push ghcr.io/mliq/mcp-atlassian:latest

# Or push multi-platform build directly
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/mliq/mcp-atlassian:latest \
  --push .
```

### Automated Builds vs Manual

**Automated (Recommended)**: Push version tags to trigger GitHub Actions
```bash
git tag v0.11.11
git push origin v0.11.11
```

**Manual**: Use commands above when you need custom builds or testing

## Source Code

This image is built from: https://github.com/mliq/mcp-atlassian

## Support

For issues or questions, please open an issue in the repository.
