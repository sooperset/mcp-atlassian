# Jira DC + Confluence DC — Docker E2E Environment

Local Docker environment for running E2E tests against Jira Data Center and Confluence Data Center.

## Prerequisites

- **Docker Desktop** with at least **10 GB RAM** allocated (Settings > Resources > Memory)
- **curl** and **python3** available on your PATH
- Ports **8080** (Jira) and **8090** (Confluence) must be free

## Quick start

```bash
# 1. Copy env file and adjust if needed
cp .env.example .env

# 2. Start the services
docker compose up -d

# 3. Wait for both services to become healthy
bash healthcheck.sh

# 4. Complete the setup wizards in your browser (see below)

# 5. Create test data (project, space, issues, pages)
bash setup-test-data.sh

# 6. Create Personal Access Tokens for the test suite
bash create-pat.sh
```

## Setup wizard (manual, one-time)

Both Jira and Confluence require completing a setup wizard on first launch.

### Jira (http://localhost:8080)

1. Select **I'll set it up myself**
2. Choose **My Own Database** — the DB is already configured via environment variables, so Jira should auto-detect it
3. Set application title and base URL (defaults are fine)
4. Enter a **license key** — generate a 30-day evaluation license at [my.atlassian.com](https://my.atlassian.com/license/evaluation)
5. Create the admin account (default: `admin` / `admin123`)
6. Skip email configuration and language prompts

### Confluence (http://localhost:8090)

1. Select **Production Installation**
2. Enter a **license key** — generate a 30-day evaluation at [my.atlassian.com](https://my.atlassian.com/license/evaluation)
3. Choose **My own database** — again, auto-detected from environment
4. Skip the demo space
5. Configure user management (standalone, not connected to Jira)
6. Create the admin account (default: `admin` / `admin123`)

## License renewal

Evaluation licenses expire after **30 days**. To renew:

1. Go to [my.atlassian.com](https://my.atlassian.com/license/evaluation) and generate a new evaluation license for the same product
2. In Jira: **Administration > System > License** — paste the new key
3. In Confluence: **Administration > License Details** — paste the new key
4. No restart required

> **Tip**: If the license has already expired, you may need to access the admin page directly at `/secure/admin/ViewLicense.jspa` (Jira) or `/admin/license.action` (Confluence).

## Stopping and cleaning up

```bash
# Stop services (preserves data volumes)
docker compose down

# Stop and remove all data (full reset)
docker compose down -v
```

## Troubleshooting

| Problem | Solution |
| --- | --- |
| Service won't start | Check `docker compose logs jira` or `docker compose logs confluence` |
| Out of memory | Increase Docker Desktop RAM to 10 GB+ |
| Port conflict | Change the host port in `docker-compose.yml` (e.g., `9080:8080`) |
| DB connection error | Ensure the DB container is healthy: `docker compose ps` |
| Setup wizard reappears | Data volumes were removed — run `docker compose down` (without `-v`) to preserve them |
| License expired | See [License renewal](#license-renewal) above |

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `JIRA_VERSION` | `10.3-jdk17` | Jira DC Docker image tag |
| `CONFLUENCE_VERSION` | `9.2-jdk17` | Confluence DC Docker image tag |
| `JIRA_DB_PASSWORD` | `jira_e2e_pass` | Jira PostgreSQL password |
| `CONFLUENCE_DB_PASSWORD` | `confluence_e2e_pass` | Confluence PostgreSQL password |
| `JIRA_BASE_URL` | `http://localhost:8080` | Jira base URL (for scripts) |
| `CONFLUENCE_BASE_URL` | `http://localhost:8090` | Confluence base URL (for scripts) |
| `DC_ADMIN_CREDENTIALS` | `admin:admin123` | Admin credentials for REST API calls |
| `HEALTHCHECK_TIMEOUT` | `300` | Max wait time in seconds for healthcheck |
| `PAT_TOKEN_NAME` | `e2e-test-token` | Name for generated PAT tokens |
