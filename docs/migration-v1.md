# Migrating to v1 outcome-oriented tools

See [#1104](https://github.com/sooperset/mcp-atlassian/issues/1104) for the
direction of the v1 tool restructuring.

| Old tool | New outcome tool |
| --- | --- |

Every PR that deprecates a tool must add its mapping to this table.

## Enable legacy tools during migration

Deprecated tools are grouped in the opt-in `legacy` toolset. Enable only the
deprecated tools while checking a replacement with:

```bash
TOOLSETS=legacy
```

To keep the core tools available as well, combine the groups:

```bash
TOOLSETS=default,legacy
```

`TOOLSETS=legacy` does not enable the core or optional toolsets. Use
`TOOLSETS=all` when the full current and legacy tool inventory is required.
When `ENABLED_TOOLS` is also set, a deprecated tool must pass both filters.
