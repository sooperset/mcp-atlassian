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
4. Enter a **license key** — paste the **Jira Software Data Center** timebomb key (10 user, 3 hours) from [Atlassian's testing licenses page](https://developer.atlassian.com/platform/marketplace/timebomb-licenses-for-testing-server-apps/) (under *Data Center host product licenses*). No my.atlassian.com account needed. See [License (timebomb)](#license-timebomb).
5. Create the admin account (default: `admin` / `admin123`)
6. Skip email configuration and language prompts

### Confluence (http://localhost:8090)

1. Select **Production Installation**
2. Enter a **license key** — paste the **Confluence Data Center** timebomb key (10 user, 3 hours) from [Atlassian's testing licenses page](https://developer.atlassian.com/platform/marketplace/timebomb-licenses-for-testing-server-apps/). **Tip:** set `CONFLUENCE_LICENSE_KEY` in `.env` — Confluence 7.9+ reads it from `ATL_LICENSE_KEY` at first-time setup, so this step can be skipped. See [License (timebomb)](#license-timebomb).
3. Choose **My own database** — again, auto-detected from environment
4. Skip the demo space
5. Configure user management (standalone, not connected to Jira)
6. Create the admin account (default: `admin` / `admin123`)

## License (timebomb)

These tests use Atlassian's published **Data Center timebomb licenses** (10 user, valid **3 hours** from when applied) instead of 30-day my.atlassian.com evals — they are free, public, and need no my.atlassian.com account. Get them from [Atlassian's testing licenses page](https://developer.atlassian.com/platform/marketplace/timebomb-licenses-for-testing-server-apps/) → *Data Center host product licenses* → **Jira Software Data Center** / **Confluence Data Center**.

The 3-hour limit is irrelevant for a normal run (the DC suite typically completes in under a minute); it only matters if an instance stays up for hours.

- **Confluence** — set `CONFLUENCE_LICENSE_KEY` in `.env` (see `.env.example`). Confluence 7.9+ reads it from `ATL_LICENSE_KEY` and applies it at **first-time setup** (skipping the wizard license step), writing it to `confluence.cfg.xml` on the persisted volume. It is **not** re-read on later restarts (`ATL_FORCE_CFG_UPDATE` defaults `false`), so a restart does **not** reset the 3-hour timer. To re-apply after expiry: a clean re-setup (`docker compose down -v`), or force a config refresh with `ATL_FORCE_CFG_UPDATE=true docker compose up -d confluence` (wired in `docker-compose.yml`). _(Verified on `confluence:9.2.21`: a fresh blank-DB start with this set skips the wizard license step. The no-restart-refresh detail follows Atlassian's container docs.)_
- **Jira** — has no license env var. Paste the timebomb key in the setup wizard. If it expires on a long-lived instance, re-paste at **Administration > System > License** (`/secure/admin/ViewLicense.jspa`, no restart needed) — still no my.atlassian.com.

> A 30-day my.atlassian.com eval also works for either product if you want a longer-lived local instance.
>
> **Fully unattended setup** (zero browser) is future work: seed a pre-configured database dump, or apply the Jira license post-boot via the private REST endpoint `POST /rest/plugins/applications/1.0/installed/jira-software/license`.

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
| License expired | See [License (timebomb)](#license-timebomb) — Jira: re-paste in admin; Confluence: `down -v` re-setup or `ATL_FORCE_CFG_UPDATE=true docker compose up -d confluence` (a plain restart does **not** refresh it) |

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `JIRA_VERSION` | `10.3-jdk17` | Jira DC Docker image tag |
| `CONFLUENCE_VERSION` | `9.2-jdk17` | Confluence DC Docker image tag |
| `JIRA_DB_PASSWORD` | `jira_e2e_pass` | Jira PostgreSQL password |
| `CONFLUENCE_DB_PASSWORD` | `confluence_e2e_pass` | Confluence PostgreSQL password |
| `CONFLUENCE_LICENSE_KEY` | _(empty)_ | Confluence DC timebomb license, supplied at first-time setup via `ATL_LICENSE_KEY` (Confluence 7.9+; see [License](#license-timebomb)) |
| `JIRA_BASE_URL` | `http://localhost:8080` | Jira base URL (for scripts) |
| `CONFLUENCE_BASE_URL` | `http://localhost:8090` | Confluence base URL (for scripts) |
| `DC_ADMIN_CREDENTIALS` | `admin:admin123` | Admin credentials for REST API calls |
| `HEALTHCHECK_TIMEOUT` | `300` | Max wait time in seconds for healthcheck |
| `PAT_TOKEN_NAME` | `e2e-test-token` | Name for generated PAT tokens |
