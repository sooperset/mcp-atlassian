# MCP Atlassian Helm Chart

This Helm chart deploys the [MCP Atlassian](https://github.com/sooperset/mcp-atlassian) server to Kubernetes, providing a Model Context Protocol (MCP) server for Jira and Confluence integration.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- Atlassian Cloud or Server/Data Center instance
- API tokens or OAuth credentials

## Installation

### Quick Start (Cloud with API Tokens)

```bash
# Create values file
cat > my-values.yaml <<YAML
confluence:
  url: "https://your-company.atlassian.net/wiki"
  username: "your.email@company.com"
  apiToken: "your_confluence_api_token"

jira:
  url: "https://your-company.atlassian.net"
  username: "your.email@company.com"
  apiToken: "your_jira_api_token"
YAML

# Install the chart
helm install mcp-atlassian ./mcp-atlassian -f my-values.yaml
```

### Validate the chart

```bash
helm lint mcp-atlassian/
```

### Test installation

```bash
helm install mcp-atlassian ./mcp-atlassian \
  --set confluence.url="https://your-company.atlassian.net/wiki" \
  --set confluence.username="user@example.com" \
  --set confluence.apiToken="token" \
  --set jira.url="https://your-company.atlassian.net" \
  --set jira.username="user@example.com" \
  --set jira.apiToken="token" \
  --dry-run --debug
```

## Configuration

See the `values.yaml` file for all configuration options.

### Key Configuration Options

- **authMode**: `api-token`, `personal-token`, `oauth`, or `byot`
- **transport**: `stdio`, `sse`, or `streamable-http`
- **confluence/jira.enabled**: Enable/disable Confluence or Jira integration
- **config.readOnlyMode**: Disable all write operations
- **persistence.enabled**: Enable OAuth token persistence

### Health Checks and Readiness Probe

The MCP server exposes a `/healthz` endpoint that returns `{"status": "ok"}` for Kubernetes health checks. This endpoint is automatically used for the readiness probe when using HTTP transport modes (`sse` or `streamable-http`).

> **Note:** The readiness probe is only enabled for HTTP transports. When using `stdio` transport, no HTTP server is exposed, so the probe is disabled.

Default readiness probe configuration in `values.yaml`:

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: http
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

You can customize these values in your `values.yaml` file:

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: http
  initialDelaySeconds: 15
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 5
```

## Upgrading

```bash
helm upgrade mcp-atlassian ./mcp-atlassian -f my-values.yaml
```

## Uninstalling

```bash
helm uninstall mcp-atlassian
```

## Support

For issues with the MCP Atlassian server, see https://github.com/sooperset/mcp-atlassian

## License

MIT License
