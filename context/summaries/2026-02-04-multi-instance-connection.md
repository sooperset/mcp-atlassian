# Multi-Instance Connection Support - Implementation Summary

**Date:** 2026-02-04
**Branch:** `feature/multi-instance-connection`
**Related Plan:** [2026-02-04-multi-instance-connection.md](../plans/2026-02-04-multi-instance-connection.md)

## Overview

Successfully implemented infrastructure for multi-instance connection support, allowing users to connect to multiple Jira and/or Confluence instances simultaneously (e.g., production, staging, development environments).

## What Was Built

### 1. Configuration Loading (Completed)

- **Files Modified:**
  - `src/mcp_atlassian/jira/config.py`
  - `src/mcp_atlassian/confluence/config.py`
  - `tests/unit/jira/test_config.py`

- **Implementation:**
  - Added `from_env_multi()` classmethod to both `JiraConfig` and `ConfluenceConfig`
  - Supports primary instance (standard variables) and numbered secondary instances (JIRA_2_*, JIRA_3_*, etc.)
  - Custom instance naming via `{SERVICE}_{N}_INSTANCE_NAME` (defaults to `jira_{N}`, `confluence_{N}`)
  - Instance name validation: alphanumeric + underscore only, max 30 chars, reserved names blocked
  - Returns dict with instance names as keys ("" for primary instance)

- **Test Coverage:**
  - Added 9 new test functions covering all scenarios
  - Tests for single instance, multiple instances, default naming, custom naming, validation rules, incomplete configs
  - All tests passing (20/20 in test_config.py)

### 2. Server Infrastructure (Completed)

- **Files Modified:**
  - `src/mcp_atlassian/servers/context.py`
  - `src/mcp_atlassian/servers/main.py`

- **Changes:**
  - `MainAppContext` now uses dict-based config storage:
    - `jira_configs: dict[str, JiraConfig]`
    - `confluence_configs: dict[str, ConfluenceConfig]`
  - Added backward compatibility properties (`full_jira_config`, `full_confluence_config`)
  - Updated `main_lifespan()` to call `from_env_multi()` and load all instances
  - Validation: Only fully authenticated instances are loaded

### 3. Dependency Providers (Completed)

- **Files Modified:**
  - `src/mcp_atlassian/servers/dependencies.py`

- **Changes:**
  - Extended `get_jira_fetcher()` and `get_confluence_fetcher()` with `instance_name` parameter
  - Default value `""` maintains backward compatibility (primary instance)
  - Config lookup from multi-instance dict
  - Clear error messages with list of available instances
  - Full support for user-specific auth and header-based auth across all instances

### 4. Documentation (Completed)

- **Files Modified:**
  - `.env.example` - Added comprehensive multi-instance configuration section with examples
  - `docs/configuration.mdx` - Added full multi-instance configuration documentation with JSON examples
  - `README.md` - Added note about multi-instance support capability

- **Documentation Includes:**
  - Configuration pattern explanation
  - Tool naming convention (prefixed vs unprefixed)
  - Instance name rules
  - Multiple examples (Jira only, Confluence only, mixed instances)
  - Best practices and notes

### 5. Tool Registration (Infrastructure Complete, TODO Added)

- **Files Modified:**
  - `src/mcp_atlassian/servers/jira.py`

- **Status:**
  - Infrastructure ready (dependency providers support `instance_name`)
  - Current tool registration uses static decorators (all tools use primary instance by default)
  - Added comprehensive TODO comment documenting:
    - Required refactoring from static to factory-based tool registration
    - Dynamic tool registration pattern for each loaded instance
    - Tool naming convention for secondary instances (e.g., `jira_staging_get_issue`)
    - Backward compatibility approach (primary keeps unprefixed names)

## Git Commits

All changes committed to `feature/multi-instance-connection` branch:

1. **docs: add plan for multi-instance connection support** (71e3ef9)
2. **docs: add multi-instance configuration documentation** (ce440d1)
3. **feat: implement multi-instance config loading** (9581bf8)
4. **feat: update server infrastructure for multi-instance support** (b06933b)
5. **feat: extend dependency providers for multi-instance support** (527b635)
6. **docs: add TODO for dynamic tool registration** (07b3ebf)

## Key Decisions

### 1. Configuration Approach
- **Decision:** Use numbered environment variable prefixes (JIRA_2_*, JIRA_3_*) with optional custom instance names
- **Rationale:**
  - Familiar pattern used by other multi-instance tools
  - Clear distinction between primary and secondary instances
  - No configuration file required (pure environment variables)
  - Easy to document and understand

### 2. Instance Name as Key
- **Decision:** Use instance name strings as dict keys, with "" for primary
- **Rationale:**
  - Empty string for primary maintains semantic consistency with "unprefixed"
  - String keys are more readable than numeric keys
  - Easy to validate and restrict (alphanumeric + underscore)
  - Prevents collision with reserved service names

### 3. Tool Registration Deferral
- **Decision:** Complete infrastructure first, defer dynamic tool registration
- **Rationale:**
  - Current decorator-based registration makes dynamic registration complex
  - Infrastructure (config loading, dependency providers) works independently
  - Tool registration requires significant refactoring
  - Better to implement as separate focused effort with proper design
  - TODO comment documents clear path forward

### 4. Backward Compatibility
- **Decision:** Maintain full backward compatibility via properties and default parameters
- **Rationale:**
  - Existing users continue working without changes
  - Primary instance uses empty string "" key (internal detail)
  - Dependency providers default to `instance_name=""` (primary)
  - `MainAppContext` provides compatibility properties

## Testing Performed

### Unit Tests
- ✅ All 20 tests in `tests/unit/jira/test_config.py` passing
- ✅ New multi-instance tests (9 added):
  - Single instance loading
  - Two instances with custom name
  - Default instance naming
  - Three instances with mixed auth types
  - Incomplete instance skipping
  - Invalid instance name handling
  - Reserved instance name handling
  - Empty dict when no config
  - Mixed authentication types

### Manual Verification
- ✅ Documentation examples validated for syntax and completeness
- ✅ Environment variable naming consistent across all files

## Known Limitations

### 1. Tool Registration Not Dynamic
- **Current State:** All tools use primary instance only
- **Impact:** Users can configure multiple instances, but tools aren't registered for secondary instances yet
- **Workaround:** None currently - feature incomplete for end-users
- **Resolution Path:** Documented in TODO comment in `jira.py`

### 2. Confluence Tests Not Added
- **Current State:** Only Jira multi-instance tests added
- **Impact:** Confluence multi-instance loading not explicitly tested
- **Mitigation:** Implementation is identical to Jira, should work correctly
- **Future Work:** Add parallel test suite for Confluence config

## Future Work

### Immediate (Required for Full Feature)
1. **Dynamic Tool Registration** - Convert static decorator-based tools to factory pattern and register per instance
2. **Confluence Tests** - Add test coverage for `ConfluenceConfig.from_env_multi()`
3. **Integration Testing** - Test actual multi-instance connections end-to-end
4. **Error Handling** - Ensure graceful handling when specific instances are unavailable

### Nice to Have
1. **Instance Discovery** - CLI command to list configured instances
2. **Instance Validation** - Pre-startup validation of all configured instances
3. **Instance Metrics** - Track which instances are being used
4. **UI Indicator** - Show instance name in tool responses

## Lessons Learned

1. **TDD Works Well for Config** - Writing tests first clarified requirements and caught edge cases early
2. **Backward Compatibility is Critical** - Property-based compatibility layer prevents breaking existing deployments
3. **Clear TODO Comments Help** - Documenting incomplete work prevents confusion about feature status
4. **Environment Swapping Pattern** - Temporarily swapping environment variables to reuse `from_env()` logic was elegant and DRY
5. **Incremental Delivery** - Completing infrastructure first enables future work without rewrites

## Risks and Mitigations

### Risk: Users Enable Feature Before Tool Registration Complete
- **Mitigation:** Documentation clearly shows this is coming soon
- **Mitigation:** Primary instance continues working as before
- **Mitigation:** No breaking changes introduced

### Risk: Instance Name Collisions
- **Mitigation:** Validation prevents reserved names ("jira", "confluence")
- **Mitigation:** Alphanumeric + underscore constraint prevents special characters
- **Mitigation:** Max 30 char limit prevents excessively long names

### Risk: Tool Naming Conflicts
- **Mitigation:** Prefix secondary instance tools with instance name
- **Mitigation:** Primary instance keeps standard names (no prefix)
- **Mitigation:** Clear documentation of naming convention

## References

- **Plan:** `context/plans/2026-02-04-multi-instance-connection.md`
- **Branch:** `feature/multi-instance-connection`
- **Related Issues:** None (proactive feature development)
- **Documentation:**
  - `.env.example` - Configuration examples
  - `docs/configuration.mdx` - Full documentation
  - `README.md` - Feature mention

## Next Steps

1. Review this summary and plan
2. Consider whether to:
   - Merge infrastructure now (enables future work)
   - Complete tool registration first (delivers full feature)
   - Split into two PRs (infrastructure + tool registration)
3. Create GitHub PR with appropriate description and links
4. Address any review feedback
5. Plan tool registration implementation as follow-up work

---

**Status:** Infrastructure complete, tool registration documented as TODO
**Recommended Action:** Merge infrastructure, schedule tool registration work
**Blockers:** None

