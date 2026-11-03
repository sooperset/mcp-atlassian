# mcp-atlassian Constitution

> **Version:** 1.2.0
> **Ratified:** 2026-09-20
> **Amended:** 2026-10-02
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.29.0
> **Profile:** Forked MCP Server

This file holds what is specific to the crunchtools fork of mcp-atlassian. The
fleet rules and the Forked MCP Server profile (Quay.io-only registry, minimal
gate set, Gourmand scoped to the crunchtools delta) apply at the inherited
version and are checked against this repo's files by `constitution.yml`. They
are not restated here.

## Upstream

- **Source:** https://github.com/sooperset/mcp-atlassian
- **License:** MIT
- **Forked at:** v0.22.1 (last sync 2026-07-12)

## Deployment

- **Port:** 8021
- **Image:** `quay.io/crunchtools/mcp-atlassian`
- **Env file:** /srv/mcp-jira.crunchtools.com/config/mcp-jira.env
- **Credentials:** JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN, ALLOW_GLOBAL_CRED_FALLBACK, TOOLSETS

## Patches

- Multi-stage Containerfile on distroless Hummingbird Python (upstream ships a single-stage python:slim build)
- Security hardening across the attachment, transport, SSRF, authorization, filter and OAuth layers
- Proxy routing preserved for trusted transports
- Rate-limit tests made deterministic against a shared bucket

## History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-09-20 | Forked MCP Server profile declared |
| 1.1.0 | 2026-09-25 | Gourmand gates the crunchtools delta (RT #1511) |
| 1.2.0 | 2026-10-02 | Manifest under constitution v1.18.0: Registry and Quality Gates restatements removed |
