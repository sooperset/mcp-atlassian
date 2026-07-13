"""Module for Jira comment operations.

Internal-only guard (JIRA_INTERNAL_ONLY_PROJECTS) coverage map:

- Guarded routes: add_comment (here), edit_comment (here),
  transition_issue's comment argument (transitions.py), and
  create_issue_link's comment payload (links.py).
- Known non-covered route: add_worklog's comment (worklog.py) is left
  unguarded by design — worklog entries are not portal-visible to JSM
  customers by default, so a worklog comment does not carry the
  customer-visible-leak risk this guard exists for.
- Audited non-routes: FormattingMixin.add_comment_to_transition_data has
  no production caller (the transition path uses
  TransitionsMixin._add_comment_to_transition_data, whose caller is
  guarded), and update_issue never emits an update.comment block.
"""

import logging
from typing import Any

from ..models.jira.adf import adf_to_text
from ..utils import parse_date
from .client import JiraClient

logger = logging.getLogger("mcp-jira")


class CommentsMixin(JiraClient):
    """Mixin for Jira comment operations."""

    def get_issue_comments(
        self, issue_key: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Get comments for a specific issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            limit: Maximum number of comments to return

        Returns:
            List of comments with author, creation date, and content

        Raises:
            Exception: If there is an error getting comments
        """
        try:
            comments = self.jira.issue_get_comments(issue_key)

            if not isinstance(comments, dict):
                msg = f"Unexpected return value type from `jira.issue_get_comments`: {type(comments)}"
                logger.error(msg)
                raise TypeError(msg)

            processed_comments = []
            for comment in comments.get("comments", [])[:limit]:
                # On Jira Cloud (REST API v3) comment bodies are returned as ADF
                # (Atlassian Document Format) dicts. convert to plain text before
                # passing to _clean_text -> clean_jira_text -> _process_mentions,
                # which calls re.sub() and would otherwise raise TypeError on the
                # dict. Mirrors the pattern used in add_comment / edit_comment
                # above. Fixes #1488.
                body_raw = comment.get("body", "")
                body_text = (
                    adf_to_text(body_raw) if isinstance(body_raw, dict) else body_raw
                )
                processed_comment = {
                    "id": comment.get("id"),
                    "body": self._clean_text(body_text or ""),
                    "created": str(parse_date(comment.get("created"))),
                    "updated": str(parse_date(comment.get("updated"))),
                    "author": comment.get("author", {}).get("displayName", "Unknown"),
                }
                processed_comments.append(processed_comment)

            return processed_comments
        except Exception as e:
            logger.error(f"Error getting comments for issue {issue_key}: {str(e)}")
            raise Exception(f"Error getting comments: {str(e)}") from e

    def _enforce_internal_only_add(self, issue_key: str, public: bool | None) -> None:
        """Reject add_comment calls that would post client-visible content
        on a project listed in JIRA_INTERNAL_ONLY_PROJECTS.

        This is the server-side backstop for the client-side PreToolUse
        hook: it protects every MCP client (not only sessions that have the
        hook installed). ``public`` defaults to customer-visible on the
        underlying API when omitted, so an absent value is treated the same
        as ``public=True`` here.

        Args:
            issue_key: The issue key (e.g. 'CC-123')
            public: The 'public' value the caller passed to add_comment

        Raises:
            ValueError: If the project is internal-only and public is not
                exactly False
        """
        if not self._is_internal_only_project(issue_key):
            return
        if public is False:
            return
        raise ValueError(
            f"Issue {issue_key} belongs to a project configured as "
            "internal-only (JIRA_INTERNAL_ONLY_PROJECTS). Automation may "
            "only post internal notes here: call add_comment with "
            "public=False (omitting 'public', or passing public=True, "
            "defaults to a customer-visible comment and is blocked). If "
            "the content is genuinely client-facing, post it as an "
            "internal note prefixed '[DRAFT — client-facing]' and have a "
            "human review and publish it as a public comment."
        )

    def _fetch_servicedesk_comment_is_public(
        self, issue_key: str, comment_id: str
    ) -> bool:
        """Fetch whether a JSM comment is customer-visible via the ServiceDesk API.

        Used by the internal-only-projects guard to check an existing
        comment's visibility before allowing edit_comment to modify it.
        Only called for issues whose project is listed in
        JIRA_INTERNAL_ONLY_PROJECTS, so the extra API round-trip is never
        paid by unaffected projects.

        Args:
            issue_key: The issue key (e.g. 'CC-123')
            comment_id: The ID of the comment to check

        Returns:
            True if the comment is public (customer-visible), False if it
            is internal. Defaults to True (public) if the API response
            omits the field, so ambiguous responses fail closed rather
            than allowing an unverified edit.

        Raises:
            Exception: If the comment's visibility cannot be resolved via
                the ServiceDesk API (e.g. not a JSM issue, or the comment
                does not exist). The guard fails closed: an edit that
                cannot be verified is refused rather than allowed through.
        """
        try:
            url = f"rest/servicedeskapi/request/{issue_key}/comment/{comment_id}"
            headers = {
                **self.jira.default_headers,
                "X-ExperimentalApi": "opt-in",
            }
            response = self.jira.get(url, headers=headers)
            if not isinstance(response, dict):
                msg = (
                    "Unexpected return value type from ServiceDesk API: "
                    f"{type(response)}"
                )
                logger.error(msg)
                raise TypeError(msg)
            public = response.get("public")
            # Only an actual boolean False proves that the comment is
            # internal. Treat missing, null, string, and numeric values as
            # public so malformed responses fail closed.
            return public is not False
        except Exception as e:
            raise Exception(
                f"Could not verify the visibility of comment {comment_id} "
                f"on {issue_key} via the ServiceDesk API (required because "
                f"{issue_key} is in an internal-only project): {e}"
            ) from e

    def _enforce_internal_only_edit(self, issue_key: str, comment_id: str) -> None:
        """Reject edit_comment calls that would modify a public comment on a
        project listed in JIRA_INTERNAL_ONLY_PROJECTS.

        This closes the gap the client-side PreToolUse hook cannot cover:
        the hook can inspect the arguments of an edit_comment call, but not
        the *current* visibility of the comment being edited. The server
        fetches that visibility itself before allowing the edit through.

        Args:
            issue_key: The issue key (e.g. 'CC-123')
            comment_id: The ID of the comment being edited

        Raises:
            ValueError: If the project is internal-only and the target
                comment is currently public
        """
        if not self._is_internal_only_project(issue_key):
            return
        if self._fetch_servicedesk_comment_is_public(issue_key, comment_id):
            raise ValueError(
                f"Comment {comment_id} on issue {issue_key} is PUBLIC "
                f"(customer-visible). {issue_key}'s project is configured "
                "as internal-only (JIRA_INTERNAL_ONLY_PROJECTS), so "
                "automation may not edit public comments there — a human "
                "must edit client-facing content directly in Jira. Post a "
                "new internal note (public=False) instead if you need to "
                "add information."
            )

    def add_comment(
        self,
        issue_key: str,
        comment: str,
        visibility: dict[str, str] | None = None,
        public: bool | None = None,
    ) -> dict[str, Any]:
        """Add a comment to an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment: Comment text to add (in Markdown format)
            visibility: (optional) Restrict comment visibility
                (e.g. {"type":"group","value":"jira-users"})
            public: (optional) For JSM issues only. True for
                customer-visible, False for internal/agent-only. Posted
                via the ServiceDesk API as a raw string; Jira Cloud
                renders it server-side and stores ADF (markdown observed
                to render on Cloud, but without the client-side
                markdown→ADF guarantees of the regular comment path).
                Cannot be combined with visibility. If issue_key's
                project is listed in JIRA_INTERNAL_ONLY_PROJECTS, only
                public=False is accepted.

        Returns:
            The created comment details

        Raises:
            ValueError: If both public and visibility are set, or if
                issue_key's project is internal-only and public is not
                exactly False
            Exception: If there is an error adding the comment
        """
        self._enforce_internal_only_add(issue_key, public)

        # ServiceDesk API path for internal/public comments
        if public is not None:
            if visibility is not None:
                raise ValueError(
                    "Cannot use both 'public' and 'visibility'. "
                    "'public' uses the ServiceDesk API which "
                    "does not support Jira visibility "
                    "restrictions."
                )
            # Deliberately no fallback: downgrading a failed internal-comment
            # request to an ordinary Jira comment could publish it to the
            # customer portal. An internal comment either posts as internal or
            # it fails.
            return self._add_servicedesk_comment(issue_key, comment, public)

        try:
            # Convert Markdown to Jira's markup format
            jira_formatted_comment = self._markdown_to_jira(comment)

            # Use v3 API on Cloud for ADF comments
            if isinstance(jira_formatted_comment, dict) and self.config.is_cloud:
                data: dict[str, Any] = {"body": jira_formatted_comment}
                if visibility:
                    data["visibility"] = visibility
                result = self._post_api3(f"issue/{issue_key}/comment", data)
            else:
                result = self.jira.issue_add_comment(
                    issue_key, jira_formatted_comment, visibility
                )
            if not isinstance(result, dict):
                msg = f"Unexpected return value type from `jira.issue_add_comment`: {type(result)}"
                logger.error(msg)
                raise TypeError(msg)

            body_raw = result.get("body", "")
            body_text = (
                adf_to_text(body_raw) if isinstance(body_raw, dict) else body_raw
            )
            return {
                "id": result.get("id"),
                "body": self._clean_text(body_text or ""),
                "created": str(parse_date(result.get("created"))),
                "author": result.get("author", {}).get("displayName", "Unknown"),
            }
        except Exception as e:
            logger.error(f"Error adding comment to issue {issue_key}: {str(e)}")
            raise Exception(f"Error adding comment: {str(e)}") from e

    def _add_servicedesk_comment(
        self,
        issue_key: str,
        comment: str,
        public: bool,
    ) -> dict[str, Any]:
        """Add a comment via the ServiceDesk API.

        Supports internal (agent-only) and public (customer-visible)
        comments on JSM issues. The body is posted as a raw string —
        unlike the regular comment path, NO client-side markdown→ADF
        conversion happens here (the ServiceDesk ``body`` field is a
        string and would not accept an ADF dict). Jira Cloud renders the
        string server-side and stores ADF; markdown constructs (bold,
        lists, tables) have been observed to render correctly on Cloud,
        but that server-side rendering fidelity is undocumented and the
        deterministic markdown→ADF guarantees of the regular comment
        path do NOT apply here.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment: Comment text (Markdown; rendered server-side by
                Jira, see above)
            public: True for customer-visible, False for internal

        Returns:
            The created comment details

        Raises:
            Exception: If the issue is not a JSM issue or API fails
        """
        try:
            url = f"rest/servicedeskapi/request/{issue_key}/comment"
            data = {"body": comment, "public": public}
            headers = {
                **self.jira.default_headers,
                "X-ExperimentalApi": "opt-in",
            }
            response = self.jira.post(
                url,
                data=data,
                headers=headers,
            )
            if not isinstance(response, dict):
                msg = (
                    "Unexpected return value type from "
                    f"ServiceDesk API: {type(response)}"
                )
                logger.error(msg)
                raise TypeError(msg)

            body_text = response.get("body", "")
            # ServiceDesk API returns DateDTO format
            created_dto = response.get("created", {})
            created_str = (
                created_dto.get("iso8601", "")
                if isinstance(created_dto, dict)
                else str(created_dto)
            )
            author_data = response.get("author", {})
            author_name = author_data.get("displayName", "Unknown")

            return {
                "id": str(response.get("id", "")),
                "body": self._clean_text(body_text),
                "created": (str(parse_date(created_str)) if created_str else ""),
                "author": author_name,
                "public": response.get("public", public),
            }
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "forbidden" in error_msg.lower():
                raise Exception(
                    f"Issue {issue_key} is not a JSM service "
                    f"desk issue or you lack permission: "
                    f"{error_msg}"
                ) from e
            if "404" in error_msg or "not found" in error_msg.lower():
                raise Exception(
                    f"Issue {issue_key} is not a JSM service "
                    f"desk issue or does not exist: {error_msg}"
                ) from e
            raise Exception(
                f"Error adding ServiceDesk comment to {issue_key}: {error_msg}"
            ) from e

    def edit_comment(
        self,
        issue_key: str,
        comment_id: str,
        comment: str,
        visibility: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Edit an existing comment on an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment_id: The ID of the comment to edit
            comment: Updated comment text (in Markdown format)
            visibility: (optional) Restrict comment visibility (e.g. {"type":"group","value":"jira-users"})

        Returns:
            The updated comment details

        Raises:
            ValueError: If issue_key's project is listed in
                JIRA_INTERNAL_ONLY_PROJECTS and the target comment is
                currently public (customer-visible)
            Exception: If there is an error editing the comment, or if
                the target comment's visibility cannot be verified for
                an internal-only project
        """
        self._enforce_internal_only_edit(issue_key, comment_id)

        try:
            # Convert Markdown to Jira's markup format
            jira_formatted_comment = self._markdown_to_jira(comment)

            # Use v3 API on Cloud for ADF comments
            if isinstance(jira_formatted_comment, dict) and self.config.is_cloud:
                data: dict[str, Any] = {"body": jira_formatted_comment}
                if visibility:
                    data["visibility"] = visibility
                result = self._put_api3(f"issue/{issue_key}/comment/{comment_id}", data)
            else:
                result = self.jira.issue_edit_comment(
                    issue_key, comment_id, jira_formatted_comment, visibility
                )
            if not isinstance(result, dict):
                msg = f"Unexpected return value type from `jira.issue_edit_comment`: {type(result)}"
                logger.error(msg)
                raise TypeError(msg)

            body_raw = result.get("body", "")
            body_text = (
                adf_to_text(body_raw) if isinstance(body_raw, dict) else body_raw
            )
            return {
                "id": result.get("id"),
                "body": self._clean_text(body_text or ""),
                "updated": str(parse_date(result.get("updated"))),
                "author": result.get("author", {}).get("displayName", "Unknown"),
            }
        except Exception as e:
            logger.error(
                f"Error editing comment {comment_id} on issue {issue_key}: {str(e)}"
            )
            raise Exception(f"Error editing comment: {str(e)}") from e
