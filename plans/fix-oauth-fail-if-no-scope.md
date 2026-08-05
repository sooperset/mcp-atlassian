# OAuth proxy fails closed without scope: plan

## Finding

When `ATLASSIAN_OAUTH_PROXY_ENABLE=true`, `_build_auth_provider()` accepts an
empty or unset `ATLASSIAN_OAUTH_SCOPE`. That results in `valid_scopes=None`,
`forced_scopes=None`, and an opaque-token verifier with no required scopes.
The local DCR scope boundary is therefore absent and behavior falls back to
framework and upstream defaults.

## Security invariant

An enabled OAuth proxy must have an explicit, non-empty scope allowlist before
it exposes DCR, authorization, and token routes. A configured scope continues
to define the proxy's valid and forced scope set.

## Plan

1. Add a narrow startup guard immediately after scope parsing. It will log a
   clear configuration warning and return no auth provider if the scope list is
   empty.
2. Update the provider-construction test helper to model a valid configured
   proxy, and add regression tests for both an unset and whitespace-only scope.
3. Run the focused OAuth proxy build and DCR tests, then the broader OAuth and
   server unit-test selection. Re-read the changed branch to ensure no route is
   exposed in the rejected configuration.
4. Add the remediation report at the existing scan artifact path. It will
   document the source-to-sink path, invariant, implementation, tests, and
   residual deployment assumption.

## Compatibility

This intentionally changes a proxy configuration with no scope from permissive
startup to disabled OAuth-proxy routes. Normal deployments already document an
OAuth scope. The non-proxy server path is unchanged.

## Commit plan

- `fix(oauth): require scope for oauth proxy`
- `test(server): cover oauth proxy scope requirement`
- `docs(auth): document oauth proxy scope hardening`

## Remediation report

### Outcome

Fixed. An enabled proxy with no usable OAuth scope now returns no auth provider,
so it cannot expose proxy, DCR, authorization, token, or discovery routes.

### Path and invariant

The prior path was `ATLASSIAN_OAUTH_PROXY_ENABLE=true` plus an unset scope,
through `_build_auth_provider()`, into `valid_scopes=None`, `forced_scopes=None`,
and an opaque verifier with an empty required-scope list. The enforced invariant
is that proxy construction requires a non-empty local scope boundary before
creating `HardenedOAuthProxy`.

### Fix and preserved behavior

The guard runs immediately after parsing `ATLASSIAN_OAUTH_SCOPE`; it logs a
configuration warning and returns `None` before any OAuth route configuration is
constructed. Configured scopes retain their existing DCR allowlist and forced
scope behavior. The proxy-disabled path and non-proxy authentication modes are
unchanged.

### Proof

- Regression tests cover both unset and whitespace/comma-only scope values.
- Existing provider-construction helpers now model a valid explicit scope.
- `uv run pytest tests/unit/servers/test_oauth_proxy_build.py tests/unit/servers/test_oauth_proxy_dcr_e2e.py tests/unit/servers/test_main_server.py tests/unit/utils/test_oauth.py -q` passed: 173 tests.
- `uv run pre-commit run --files src/mcp_atlassian/servers/main.py tests/unit/servers/test_oauth_proxy_build.py` passed, including Ruff and mypy.

### Residual risk

This closes the local fail-open configuration path. Upstream OAuth app scope
policy remains an operator responsibility, and the selected explicit scope must
still follow least privilege.
