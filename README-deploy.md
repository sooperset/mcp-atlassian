# Running this fork as a shared, multi-tenant MCP server

`docker-compose.yml` here runs one container for every tenant. The credentials do not live
in it: coworker sends each tenant's site URL and API token as headers on every request, and
`--stateless` is what stops one call's fetcher reaching the next one.

    docker build -f Dockerfile.plain -t mcp-atlassian:local .
    COWORKER_STATE_DIR=/home/dev/workforce-state docker compose up -d

`Dockerfile.plain`, not `Dockerfile`: upstream's uses BuildKit-only mounts and this host has
classic docker with no buildx.

## The placeholders are load-bearing

`<state dir>/mcp-atlassian.env` sets `JIRA_URL`, `JIRA_USERNAME` and `JIRA_API_TOKEN` to
values under `.invalid`. They are not credentials and are never used by a real call — but
without *something* there the server registers **zero tools**: `servers/main.py` only mounts
the Jira and Confluence tools when `from_env()` reports auth configured at startup, however
many headers a later request carries. Measured: 0 tools with the variables unset, 98 with
them set.

`.invalid` rather than a plausible `something.atlassian.net`, because RFC 2606 guarantees
that TLD never resolves. A request that arrives without its headers then fails at DNS with
the hostname in the message, instead of authenticating against a real site that happened to
be named in a config file.

## What was verified

  * `tools/list` → 98 tools.
  * `jira_get_user_profile` with `X-Atlassian-Jira-Url` + `Authorization: Basic` → the real
    profile from that site.
  * the same call with the URL header REMOVED → fails against `never-used.invalid`. It does
    not reuse the previous request's site, which is the property the whole design rests on.
