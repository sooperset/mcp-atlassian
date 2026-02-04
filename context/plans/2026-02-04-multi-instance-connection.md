# Plan: Multi-Instance Connection Support

**Date:** 2026-02-04
**Status:** Pending Review
**Scope:** Add support for connecting to multiple Atlassian instances simultaneously

---

## 1. Objective

Implement multi-instance connection support for the MCP Atlassian server, allowing users to:
- Connect to multiple Jira instances simultaneously (e.g., production and staging)
- Connect to multiple Confluence instances simultaneously
- Distinguish between instances via prefixed tool names or instance identifiers
- Support per-instance authentication (different credentials for each instance)

## 2. Current State Analysis

### Current Architecture

The server currently supports:
- **Single instance per service**: One Jira URL and one Confluence URL from environment variables
- **Multi-user authentication**: Header-based authentication allows different users to connect with their own credentials
- **Multi-cloud support**: Users can connect to different cloud instances via `X-Atlassian-Cloud-Id` header
- **Header-based instance override**: `X-Atlassian-Jira-Url` and `X-Atlassian-Confluence-Url` headers for per-request instance selection

### Key Files

1. **Configuration (`src/mcp_atlassian/jira/config.py`, `src/mcp_atlassian/confluence/config.py`)**
   - `JiraConfig` and `ConfluenceConfig` classes load from single environment variables
   - `from_env()` classmethod reads `JIRA_URL`, `CONFLUENCE_URL`, etc.

2. **Server Initialization (`src/mcp_atlassian/servers/main.py`)**
   - `main_lifespan()`: Loads single Jira and Confluence configs from env at startup
   - `MainAppContext`: Holds `full_jira_config` and `full_confluence_config` (single instances)
   - `UserTokenMiddleware`: Processes header-based authentication

3. **Dependencies (`src/mcp_atlassian/servers/dependencies.py`)**
   - `get_jira_fetcher()` and `get_confluence_fetcher()`: Create fetcher instances
   - Support for header-based instance selection via `X-Atlassian-Jira-Url` and related headers
   - Fallback to global config if no headers provided

4. **Tool Registration (`src/mcp_atlassian/servers/jira.py`, `src/mcp_atlassian/servers/confluence.py`)**
   - Tools are registered with a single service (Jira or Confluence)
   - Tool names are service-scoped (e.g., `jira_get_issue`)

### Current Capabilities

The server already has partial multi-instance support through headers:
- ✅ Header-based instance selection: `X-Atlassian-Jira-Url` + `X-Atlassian-Jira-Personal-Token`
- ✅ Per-request authentication (multi-user mode)
- ✅ Multi-cloud OAuth support via `X-Atlassian-Cloud-Id`

### Gap Analysis

What's missing for full multi-instance support:
- ❌ **Static instance registration**: Define multiple instances in configuration (not just per-request)
- ❌ **Tool name prefixing**: Distinguish tools by instance (e.g., `jira_prod_get_issue` vs `jira_staging_get_issue`)
- ❌ **Instance selection in IDE config**: Users can't specify which instance to use in their MCP client config
- ❌ **Multiple default configs**: Can't define multiple Jira/Confluence instances at startup

## 3. Approach

### Design Decision: Configuration-Based Multi-Instance

**Chosen Approach:** Define multiple instances via environment variables at startup, register tools with instance-prefixed names.

**Rationale:**
1. **Simplicity**: Leverage existing config loading mechanism
2. **Explicit**: Users define instances upfront, not dynamically per-request
3. **Tool Discovery**: All available instances are visible in tool list
4. **Backward Compatibility**: Single-instance configs still work without changes

**Alternative Considered:** Pure header-based routing (current partial implementation)
- **Pros**: More flexible, no config changes
- **Cons**: Requires headers on every request, not visible in tool list, complex error handling

### Configuration Format

Support multiple instances via numbered environment variables:

```bash
# Primary instance (backward compatible)
JIRA_URL=https://company.atlassian.net
JIRA_USERNAME=user@example.com
JIRA_API_TOKEN=token1

# Secondary instance(s)
JIRA_2_URL=https://staging.atlassian.net
JIRA_2_USERNAME=user@example.com
JIRA_2_API_TOKEN=token2
JIRA_2_INSTANCE_NAME=staging  # Optional: defaults to "jira_2"

# Tertiary instance
JIRA_3_URL=https://prod-internal.company.com
JIRA_3_PERSONAL_TOKEN=pat_token
JIRA_3_INSTANCE_NAME=prod_internal
```

**Instance Naming Rules:**
- Primary instance (no number): Tool prefix is `jira_` or `confluence_`
- Numbered instances: Tool prefix is `jira_{instance_name}_` or `confluence_{instance_name}_`
- Default instance name if not specified: `jira_2`, `jira_3`, etc.

### Tool Registration Strategy

Each instance gets its own set of tools with prefixed names:

```
# Primary instance
jira_get_issue
jira_search
jira_create_issue
...

# Staging instance (JIRA_2_INSTANCE_NAME=staging)
jira_staging_get_issue
jira_staging_search
jira_staging_create_issue
...

# Internal instance (JIRA_3_INSTANCE_NAME=prod_internal)
jira_prod_internal_get_issue
jira_prod_internal_search
...
```

## 4. Implementation Steps

### Phase 1: Configuration Loading (Core)

1. **Extend config loading** (`jira/config.py`, `confluence/config.py`)
   - Add `JiraConfig.from_env_multi()` classmethod
   - Parse `JIRA_{N}_*` environment variables
   - Return `dict[str, JiraConfig]` mapping instance names to configs
   - Validate instance names (alphanumeric + underscore only)
   - Include primary instance with default name `""` (empty string for primary)

2. **Update `MainAppContext`** (`servers/context.py`)
   - Change `full_jira_config: JiraConfig | None` to `jira_configs: dict[str, JiraConfig]`
   - Change `full_confluence_config: ConfluenceConfig | None` to `confluence_configs: dict[str, ConfluenceConfig]`
   - Primary instance has key `""` (empty string)
   - Secondary+ instances have keys like `"staging"`, `"prod_internal"`

3. **Update server initialization** (`servers/main.py`)
   - In `main_lifespan()`: Load all instances via `JiraConfig.from_env_multi()`
   - Store in `MainAppContext.jira_configs` and `.confluence_configs`
   - Log loaded instances with their URLs

### Phase 2: Dependency Resolution

1. **Extend dependency providers** (`servers/dependencies.py`)
   - Add `instance_name` parameter to `get_jira_fetcher()` and `get_confluence_fetcher()`
   - Look up config from `MainAppContext.jira_configs[instance_name]`
   - Maintain backward compatibility: default to primary instance (`""`) if not specified

2. **Update `_create_user_config_for_fetcher()`**
   - No changes needed—already supports user-specific overrides

### Phase 3: Tool Registration

1. **Update tool registration** (`servers/jira.py`, `servers/confluence.py`)
   - For each loaded instance, register a full set of tools
   - Apply instance-specific name prefix (e.g., `jira_staging_`)
   - Primary instance keeps original names (`jira_`) for backward compatibility
   - Pass `instance_name` to dependency providers

2. **Tool filtering** (`servers/main.py`)
   - Update `_list_tools_mcp()` to handle instance-specific tools
   - Filter by instance availability and authentication
   - Check if instance config exists before including its tools

### Phase 4: Documentation and Examples

1. **Update `.env.example`**
   - Add multi-instance configuration examples
   - Document instance naming conventions

2. **Update `docs/configuration.mdx`**
   - Add "Multi-Instance Setup" section
   - Provide examples for common scenarios (prod + staging, multiple tenants)

3. **Update `docs/http-transport.mdx`**
   - Document interaction between static instances and header-based routing
   - Clarify precedence: header-based routing overrides static instances

## 5. Affected Files

### Core Implementation
- `src/mcp_atlassian/jira/config.py` - Add `from_env_multi()` classmethod
- `src/mcp_atlassian/confluence/config.py` - Add `from_env_multi()` classmethod
- `src/mcp_atlassian/servers/context.py` - Update `MainAppContext` structure
- `src/mcp_atlassian/servers/main.py` - Update `main_lifespan()` for multi-instance loading
- `src/mcp_atlassian/servers/dependencies.py` - Add `instance_name` parameter to fetcher functions
- `src/mcp_atlassian/servers/jira.py` - Update tool registration for multiple instances
- `src/mcp_atlassian/servers/confluence.py` - Update tool registration for multiple instances

### Documentation
- `.env.example` - Add multi-instance examples
- `docs/configuration.mdx` - Add multi-instance section
- `docs/http-transport.mdx` - Document interaction with header-based routing
- `README.md` - Add brief mention in Quick Start section

### Testing
- `tests/test_jira_config.py` - Test `from_env_multi()` loading
- `tests/test_confluence_config.py` - Test `from_env_multi()` loading
- `tests/test_multi_instance.py` - New integration test file

## 6. Edge Cases and Risks

### Edge Cases

1. **Instance name collision**: User defines `JIRA_2_INSTANCE_NAME=jira`
   - **Mitigation**: Validate instance names, reject reserved names (`jira`, `confluence`)

2. **Mixed authentication types**: Instance 1 uses OAuth, Instance 2 uses PAT
   - **Mitigation**: Each instance has independent config, no conflicts

3. **Partial instance config**: User sets `JIRA_2_URL` but not credentials
   - **Mitigation**: Skip instance during loading, log warning

4. **Tool name length**: Long instance names create long tool names
   - **Mitigation**: Validate instance name max length (e.g., 20 chars), reject if too long

5. **Header-based routing with static instances**: Both defined
   - **Mitigation**: Header-based routing overrides static instance, document precedence

### Risks

1. **Breaking change**: Modifying `MainAppContext` structure
   - **Mitigation**: Update all code that accesses these fields, provide backward-compatible accessors

2. **Performance**: Loading many instances at startup
   - **Mitigation**: Lazy-load fetchers (don't create until first use), limit max instances

3. **Credential leakage**: Wrong instance used for a request
   - **Mitigation**: Clear logging of which instance is used, validate instance existence before use

4. **Tool list explosion**: 50 tools × 3 instances = 150 tools
   - **Mitigation**: Consider tool filtering by instance in future enhancement

## 7. Testing Strategy

### Unit Tests
- `test_jira_config.py`: Test `from_env_multi()` with various env configs
- `test_confluence_config.py`: Test `from_env_multi()` with various env configs
- `test_dependencies.py`: Test `get_jira_fetcher()` with `instance_name` parameter

### Integration Tests
- `test_multi_instance.py`: End-to-end test with 2 Jira instances
  - Define two mock Jira configs
  - Call tools with different instance prefixes
  - Verify correct instance is used

### Manual Testing
- Test with real Jira instances (prod + staging)
- Verify tool list includes all instances
- Test authentication with different credentials per instance

## 8. Rollout Plan

### Phase 1: Core Implementation (High Priority)
- Implement config loading for multiple instances
- Update `MainAppContext` structure
- Update server initialization

### Phase 2: Tool Registration (High Priority)
- Implement instance-specific tool registration
- Update dependency providers
- Test with 2 instances

### Phase 3: Documentation (Medium Priority)
- Update all docs with multi-instance examples
- Add troubleshooting section

### Phase 4: Polish (Low Priority)
- Add tool filtering by instance
- Optimize performance (lazy loading)
- Enhanced logging for debugging

## 9. Future Enhancements (Out of Scope)

- **Dynamic instance registration**: Add/remove instances without restart
- **Instance aliasing**: Map short names to instances (e.g., `prod` → `jira_prod`)
- **Cross-instance operations**: Link issues across instances
- **Instance health monitoring**: Check connectivity at startup
- **Instance groups**: Group instances for batch operations

## 10. Success Criteria

- ✅ Users can define multiple Jira/Confluence instances via environment variables
- ✅ Tools are registered with instance-specific names (e.g., `jira_staging_get_issue`)
- ✅ Each instance supports independent authentication
- ✅ Primary instance remains backward compatible (no breaking changes)
- ✅ Documentation clearly explains multi-instance setup
- ✅ All existing tests pass
- ✅ New integration tests cover multi-instance scenarios

---

## Review Checklist

Before proceeding to execution:
- [ ] Approach is clear and feasible
- [ ] Breaking changes are minimized and documented
- [ ] Testing strategy is comprehensive
- [ ] Documentation updates are planned
- [ ] Edge cases are identified and mitigated
- [ ] Backward compatibility is maintained
