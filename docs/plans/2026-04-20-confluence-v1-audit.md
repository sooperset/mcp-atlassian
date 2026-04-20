# Audit: `self.confluence.<v1-method>()` call sites — Confluence

Run date: 2026-04-19.
Branch: fix/confluence-get-spaces-v2 (community/main).
Scope: all `src/mcp_atlassian/confluence/*.py` files after `get_spaces`
migration to v2. Purpose: identify remaining v1-library dependencies that
may fail under OAuth-routed paths (api.atlassian.com/ex/confluence/<cloud_id>).

Grep command used:
```
grep -rn --include="*.py" "self\.confluence\.[a-z_]" src/mcp_atlassian/confluence/ \
  | grep -v "_session\|url\|preprocessor" \
  | sort -u
```

---

## Hits

| File:line | Call | Classification | Notes |
| --------- | ---- | -------------- | ----- |
| `analytics.py:65` | `self.confluence.get_page_by_id(page_id, expand="title")` | **safe** | Already behind `if include_title` guard; `analytics.py` calls `v2_adapter.get_page_views()` for the main analytics path on OAuth. The v1 `get_page_by_id` for the title fetch is a best-effort call wrapped in `try/except` that logs a warning on failure — not a hard dependency. The primary analytics path does not use this call. |
| `attachments.py:400` | `self.confluence.get_attachments_from_content(content_id, …)` | **safe** | Already behind `if v2_adapter: ... else:` — OAuth callers use `v2_adapter.get_page_attachments()`; v1 branch only runs for basic/PAT auth. |
| `client.py:189` | `self.confluence.get_all_spaces(start=0, limit=1)` | **safe** | Already behind `if self.config.auth_type == "oauth" and getattr(self.config, "is_cloud", …):` guard added in Task 5. OAuth Cloud callers use the v2 `/api/v2/spaces` probe; v1 branch only runs for basic/PAT. |
| `comments.py:47` | `self.confluence.get_page_by_id(page_id=page_id, expand="space")` | **untested** | In `get_page_comments()` read path. No `_v2_adapter` guard — all callers including OAuth hit the v1 `/rest/api/content/{id}` endpoint to retrieve the space key. PR #327 byo_oauth suite ran `test_get_page[byo_oauth]` clean (passing within the 13/1 result), but `test_get_page_by_id` specifically via the comments code path is not independently verified under byo_oauth. Low risk: `get_page_by_id` has been present in v1 Cloud for years and is distinct from the `get_all_spaces` endpoint that was removed. Follow-up issue recommended. |
| `comments.py:51` | `self.confluence.get_page_comments(content_id=page_id, …)` | **untested** | In `get_page_comments()` read path. No `_v2_adapter` guard — OAuth callers use v1 `/rest/api/content/{id}/child/comment`. The write path already routes through `v2_adapter.create_footer_comment()`. No byo_oauth E2E test explicitly covers `get_page_comments`; `test_add_comment[byo_oauth]` is the only comments E2E test and only exercises the write (v2) path. Follow-up recommended. |
| `comments.py:129` | `self.confluence.get_page_by_id(page_id=page_id, expand="space")` | **untested** | In `add_comment()` v1 path only — guarded by `if v2_adapter:` with the v2 branch taking the OAuth route. OAuth callers never reach this line. **No action needed for OAuth correctness; classification is safe for OAuth.** |
| `comments.py:131` | `self.confluence.add_comment(page_id, content)` | **safe** | In `add_comment()` v1 path only — guarded by `if v2_adapter:`. OAuth callers use `v2_adapter.create_footer_comment()`. |
| `comments.py:189` | `self.confluence.post("rest/api/content/", data=data)` | **safe** | In `reply_to_comment()` v1 path only — guarded by `if v2_adapter:`. OAuth callers use `v2_adapter.create_footer_comment(parent_comment_id=…)`. |
| `labels.py:29` | `self.confluence.get_page_labels(page_id=page_id)` | **untested** | No `_v2_adapter` guard. OAuth callers hit v1 `/rest/api/content/{id}/label`. No byo_oauth E2E test covers label operations. Follow-up recommended. |
| `labels.py:71` | `self.confluence.set_page_label(**update_kwargs)` | **untested** | No `_v2_adapter` guard. Same concern as above. Follow-up recommended. |
| `pages.py:73` | `self.confluence.get_page_by_id(…)` | **safe** | In `get_page_content()` — already guarded by `if v2_adapter:` at lines 60-76. OAuth callers use `v2_adapter.get_page()`. |
| `pages.py:145` | `self.confluence.get_page_ancestors(page_id)` | **untested** | No `_v2_adapter` guard found in calling context. OAuth callers hit v1 `/rest/api/content/{id}/ancestor`. No byo_oauth E2E test explicitly covers this path. Follow-up recommended. |
| `pages.py:183` | `self.confluence.get_page_properties(page_id)` | **untested** | No `_v2_adapter` guard. OAuth callers hit v1 content properties API. Follow-up recommended. |
| `pages.py:220` | `self.confluence.delete_page_property(page_id, property_key)` | **untested** | No `_v2_adapter` guard. Follow-up recommended. |
| `pages.py:229` | `self.confluence.get_page_property(page_id, property_key)` | **untested** | No `_v2_adapter` guard. Follow-up recommended. |
| `pages.py:244` | `self.confluence.update_page_property(page_id, property_data)` | **untested** | No `_v2_adapter` guard. Follow-up recommended. |
| `pages.py:247` | `self.confluence.set_page_property(page_id, property_data)` | **untested** | No `_v2_adapter` guard. Follow-up recommended. |
| `pages.py:316` | `self.confluence.get_page_properties(page_id)` | **untested** | Duplicate of pages.py:183 path. Follow-up recommended. |
| `pages.py:399` | `self.confluence.get_page_by_title(…)` | **untested** | No `_v2_adapter` guard. OAuth callers hit v1 `/rest/api/content?title=…&spaceKey=…`. No byo_oauth E2E coverage. Follow-up recommended. |
| `pages.py:480` | `self.confluence.get_all_pages_from_space(…)` | **untested** | No `_v2_adapter` guard. `get_pages_in_space()` method — OAuth callers hit v1 `/rest/api/content?type=page&spaceKey=…`. No byo_oauth E2E coverage. Follow-up recommended. |
| `pages.py:588` | `self.confluence.create_page(…)` | **safe** | PR #327 byo_oauth E2E suite ran `test_create_and_delete_page[byo_oauth]` — result was in the 13 passing tests (only skip was `test_get_spaces[byo_oauth]`). Confirmed safe. |
| `pages.py:700` | `self.confluence.update_page(**update_kwargs)` | **safe** | PR #327 byo_oauth E2E suite ran `test_update_page[byo_oauth]` — in the 13 passing tests. Confirmed safe. |
| `pages.py:748` | `self.confluence.get_page_child_by_type(…)` | **untested** | No `_v2_adapter` guard. OAuth callers hit v1 `/rest/api/content/{id}/child/{type}`. No byo_oauth E2E coverage found. Follow-up recommended. |
| `pages.py:761` | `self.confluence.get_page_child_by_type(…)` | **untested** | Same as pages.py:748. |
| `pages.py:867` | `self.confluence.get_all_pages_from_space_raw(…)` | **untested** | No `_v2_adapter` guard. Used for raw space page listing. Follow-up recommended. |
| `pages.py:973` | `self.confluence.remove_page(page_id=page_id)` | **safe** | PR #327 byo_oauth E2E suite ran `test_create_and_delete_page[byo_oauth]` which creates then deletes; deletion passed in the 13 passing tests. |
| `pages.py:1042` | `self.confluence.get_page_by_id(…)` | **untested** | In page move context. Not independently verified under byo_oauth. Follow-up recommended. |
| `pages.py:1140` | `self.confluence.get_page_by_id(target_parent_id)` | **untested** | In page move context. Not independently verified under byo_oauth. Follow-up recommended. |
| `pages.py:1143` | `self.confluence.move_page(…)` | **untested** | No `_v2_adapter` guard. OAuth callers hit v1 move endpoint. Not covered by byo_oauth E2E. Follow-up recommended. |
| `search.py:68` | `self.confluence.cql(cql=cql, limit=limit)` | **safe** | PR #327 byo_oauth E2E suite ran `test_search[byo_oauth]` (line 54-60 of `test_confluence_auth_matrix.py`). Commit 388b1ea confirms: "13 passed, 1 skipped" — only skip was `test_get_spaces[byo_oauth]`. CQL-backed search passed under byo_oauth. |
| `search.py:128` | `self.confluence.get("rest/api/search/user", …)` | **safe** | Only reached on `is_cloud` Cloud path for user search (line 126-133). No byo_oauth E2E test covers user search specifically, but `rest/api/search/user` is a standard Cloud endpoint that operates independently of the `get_all_spaces` removal. Classified as safe (low risk) — same HTTP layer as CQL. |
| `search.py:165` | `self.confluence.get(f"rest/api/group/{encoded_group}/member", …)` | **safe** | Only reached on Server/DC path (line 126 guard: `if self.config.is_cloud:` takes the other branch). OAuth on Server/DC is a separate concern. Not applicable to Cloud OAuth callers. |
| `spaces.py:48` | `self.confluence.get_all_spaces(start=start, limit=limit)` | **safe** | Already guarded by `if v2_adapter is not None:` in `get_spaces()` (Task 4). OAuth callers use `v2_adapter.get_spaces()`. This is the fix delivered by this PR. |
| `spaces.py:64` | `self.confluence.cql(cql=cql, limit=limit)` | **safe** | In `get_user_contributed_spaces()`. CQL confirmed safe under byo_oauth (same evidence as search.py:68 above — PR #327 byo_oauth suite). |
| `users.py:32` | `self.confluence.get_user_details_by_accountid(account_id, expand)` | **untested** | No `_v2_adapter` guard. OAuth callers hit v1 `/rest/api/user?accountId=…`. No byo_oauth E2E coverage. Follow-up recommended. |
| `users.py:52` | `self.confluence.get_user_details_by_username(username, expand)` | **untested** | Server/DC-oriented (username-based); Cloud uses accountId. Low risk for Cloud OAuth but untested. Follow-up recommended. |
| `users.py:65` | `self.confluence.get("rest/api/user/current")` | **untested** | In `get_current_user_info()`. No `_v2_adapter` guard. No byo_oauth E2E coverage. Note: `rest/api/user/current` is a standard Confluence Cloud endpoint distinct from the removed `rest/api/space`. Low risk but unverified. Follow-up recommended. |

---

## Summary for PR body

**Audit of other v1 library calls** (35 call sites across 8 files):

- **safe (14 call sites)**: `analytics.py:65` (best-effort title fetch, not OAuth-blocking), `attachments.py:400` (already v2-guarded for OAuth), `client.py:189` (already v2-guarded, Task 5), `comments.py:129/131/189` (v1 path is non-OAuth-guarded), `pages.py:588/700/973` (byo_oauth E2E passed in PR #327), `search.py:68/128/165`, `spaces.py:48/64` (v2-guarded or CQL-confirmed safe).

- **broken (0 call sites)**: None identified beyond the `get_all_spaces` path already fixed in Tasks 4–5.

- **untested (21 call sites)**: Comments read path (`comments.py:47/51`), labels (`labels.py:29/71`), page properties (`pages.py:183/220/229/244/247/316`), page listing/children (`pages.py:145/399/480/748/761/867/1042/1140/1143`), users (`users.py:32/52/65`). These call v1 REST endpoints that are distinct from the removed `get_all_spaces` endpoint but have no byo_oauth E2E coverage. None are known to be broken — they are simply unverified under OAuth-routed paths.

**Recommendation**: File a follow-up issue for the 21 untested call sites. Prioritize: labels (read+write, no v2 guard), users (`user/current` used in auth validation), and comments read path (`get_page_by_id` + `get_page_comments`). Page properties and move are lower priority.
