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
- Scope: the setting names whole *projects*, but the customer-visibility
  risk it exists for is per *issue* — only a JSM customer request has a
  portal view. add_comment therefore exempts issues in a guarded project
  that are not requests (see _is_servicedesk_request), because the
  ServiceDesk comment API they would need does not exist for them.
"""

import logging
import re
from typing import Any, cast

from requests.exceptions import HTTPError

from ..models.jira.adf import adf_to_text, build_media_comment_adf
from ..utils import parse_date
from ..utils.io import validate_safe_path
from ..utils.media import ATTACHMENT_MAX_BYTES, get_image_dimensions
from .client import JiraClient
from .config import normalize_project_key
from .protocols import AttachmentMediaOperationsProto

logger = logging.getLogger("mcp-jira")

_CANONICAL_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")

# Markdown image syntax used to position an inline attachment inside a comment
# body: ``![alt](media:0)`` (index into the media list) or ``![alt](shot.png)``
# (matching a media entry's filename).
_MEDIA_PLACEHOLDER_RE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)\s*\)")


def _http_status(exc: BaseException) -> int | None:
    """Extract the HTTP status code from an exception, if it carries one.

    Preferred over matching on ``str(exc)``: an HTTPError raised for a
    response with an empty body stringifies to ``""``, so a substring test
    silently misses the status it is looking for.

    Args:
        exc: The exception to inspect.

    Returns:
        The HTTP status code, or None if the exception does not carry one.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


class CommentsMixin(JiraClient):
    """Mixin for Jira comment operations."""

    @staticmethod
    def _require_canonical_guarded_issue_key(issue_key: str) -> str:
        """Reject ambiguous issue keys before relaxing an internal-only guard.

        The guard deliberately normalizes project keys so padded or invisible
        input cannot evade protection. The request probe and the later Jira
        write must not then use that original, different spelling: a 404 for
        the malformed spelling is not evidence that the canonical issue is not
        a customer request.

        This check is only used after the issue has matched an internal-only
        project. Unlisted projects retain their existing behavior.

        Args:
            issue_key: The caller-provided Jira issue key.

        Returns:
            The unchanged, canonical issue key.

        Raises:
            ValueError: If normalization would change the key, or if whitespace
                remains in it.
        """
        normalized = normalize_project_key(issue_key)
        project, separator, suffix = normalized.partition("-")
        canonical = (
            f"{normalize_project_key(project)}-{normalize_project_key(suffix)}"
            if separator
            else normalized
        )
        if (
            issue_key != canonical
            or any(char.isspace() for char in canonical)
            or _CANONICAL_ISSUE_KEY_RE.fullmatch(canonical) is None
        ):
            raise ValueError(
                f"Issue key {issue_key!r} belongs to an internal-only project "
                "but is not canonical. Malformed, padded, lowercase, "
                "whitespace, or invisible-character variants are rejected "
                "before checking whether the issue is a JSM customer request."
            )
        return canonical

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

    def _is_servicedesk_request(self, issue_key: str) -> bool:
        """Check whether an issue is a JSM customer request.

        JIRA_INTERNAL_ONLY_PROJECTS names whole projects, but only a JSM
        customer request has a portal view and customer participants. An
        issue raised internally in the same project — an agent-created Task
        or Sub-task, say — has no portal presence, so an ordinary Jira
        comment on it cannot reach a customer.

        The distinction matters because the guard would otherwise leave no
        way to comment on such an issue at all: ``public=False`` posts via
        ``rest/servicedeskapi/request/<key>/comment``, which does not exist
        for a non-request, while ``public=True`` or an omitted ``public`` is
        refused by :meth:`_enforce_internal_only_add`.

        Fails closed. Only an explicit 404 counts as a negative; every other
        outcome — 403, 5xx, timeout, unexpected body — reports True so the
        guard stays in force. Called only for projects listed in
        JIRA_INTERNAL_ONLY_PROJECTS, so other projects never pay the extra
        round-trip.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            True if the issue is a JSM customer request, or if that could
            not be established. False only on a definite 404.
        """
        try:
            response = self.jira.get(
                f"rest/servicedeskapi/request/{issue_key}",
                headers={
                    **self.jira.default_headers,
                    "X-ExperimentalApi": "opt-in",
                },
            )
        except HTTPError as exc:
            if _http_status(exc) == 404:
                logger.info(
                    f"{issue_key} is not a JSM customer request; an ordinary "
                    "Jira comment there has no portal audience, so the "
                    "internal-only guard does not apply."
                )
                return False
            logger.warning(
                f"Could not establish whether {issue_key} is a JSM customer "
                f"request; treating it as one so the internal-only guard "
                f"stays in force: {exc}"
            )
            return True
        except Exception as exc:
            logger.warning(
                f"Could not establish whether {issue_key} is a JSM customer "
                f"request; treating it as one so the internal-only guard "
                f"stays in force: {exc}"
            )
            return True

        if isinstance(response, dict) and response.get("issueId"):
            return True
        logger.warning(
            f"ServiceDesk API returned no issueId for {issue_key}; treating "
            "it as a customer request so the internal-only guard stays in "
            "force."
        )
        return True

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
                public=False is accepted — unless issue_key is not a JSM
                customer request, in which case it has no portal audience,
                this argument is ignored, and the comment posts through
                the ordinary path.

        Returns:
            The created comment details

        Raises:
            ValueError: If both public and visibility are set, or if
                issue_key's project is internal-only and public is not
                exactly False
            Exception: If there is an error adding the comment
        """
        # The guard names a project, but the leak it prevents is per issue.
        # An issue that is not a JSM customer request has no portal audience,
        # and the ServiceDesk comment API that public=False needs does not
        # exist for it — so enforcing the guard there blocks every route
        # instead of protecting anyone. Fall through to the ordinary comment
        # path for those. _is_servicedesk_request fails closed, so anything
        # short of a definite 404 keeps the guard in force.
        # The shared project matcher accounts for URL normalization before
        # classifying the key. Canonical validation then rejects the original
        # spelling before any request lookup or write.
        if self._is_internal_only_project(issue_key):
            issue_key = self._require_canonical_guarded_issue_key(issue_key)
            if not self._is_servicedesk_request(issue_key):
                public = None
            else:
                self._enforce_internal_only_add(issue_key, public)
        else:
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
            # Prefer the status carried on the exception. Matching on the
            # message alone misses a status whose response body is empty:
            # str(e) is then "", and the caller gets the generic message
            # below with nothing after the colon.
            status = _http_status(e)
            if status == 403 or "403" in error_msg or "forbidden" in error_msg.lower():
                raise Exception(
                    f"Issue {issue_key} is not a JSM service "
                    f"desk issue or you lack permission: "
                    f"{error_msg or 'HTTP 403'}"
                ) from e
            if status == 404 or "404" in error_msg or "not found" in error_msg.lower():
                raise Exception(
                    f"Issue {issue_key} is not a JSM service "
                    f"desk issue or does not exist: "
                    f"{error_msg or 'HTTP 404'}"
                ) from e
            raise Exception(
                f"Error adding ServiceDesk comment to {issue_key}: "
                f"{error_msg or type(e).__name__}"
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

    def delete_comment(self, issue_key: str, comment_id: str) -> bool:
        """
        Delete a comment from an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            comment_id: The ID of the comment to delete

        Returns:
            True if the comment was deleted successfully

        Raises:
            Exception: If there is an error deleting the comment
        """
        try:
            resource = f"issue/{issue_key}/comment/{comment_id}"
            # Use v3 on Cloud for consistency with the other comment writes;
            # the library exposes no comment-deletion helper, so issue a raw
            # DELETE.
            if self.config.is_cloud:
                self._delete_api3(resource)
            else:
                self.jira.delete(self.jira.resource_url(resource))
            return True
        except Exception as e:
            logger.error(
                f"Error deleting comment {comment_id} on issue {issue_key}: {str(e)}"
            )
            raise Exception(f"Error deleting comment: {str(e)}") from e

    def add_comment_adf(
        self,
        issue_key: str,
        adf_body: dict[str, Any],
        visibility: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Add a comment from a pre-built ADF document.

        Used for rich comments that Markdown cannot express, such as inline
        media (screenshots embedded in the body). Cloud only, since the v3 API
        is what accepts ADF.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            adf_body: A complete ADF document (``version``/``type``/``content``)
            visibility: (optional) Restrict comment visibility

        Returns:
            The created comment details

        Raises:
            ValueError: If the Jira instance is not Cloud
            Exception: If there is an error adding the comment
        """
        if not self.config.is_cloud:
            raise ValueError(
                "ADF comments (inline media) are supported on Jira Cloud only."
            )

        try:
            data: dict[str, Any] = {"body": adf_body}
            if visibility:
                data["visibility"] = visibility
            result = self._post_api3(f"issue/{issue_key}/comment", data)

            if not isinstance(result, dict):
                msg = f"Unexpected return value type from `_post_api3`: {type(result)}"
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
            logger.error(f"Error adding ADF comment to issue {issue_key}: {str(e)}")
            raise Exception(f"Error adding ADF comment: {str(e)}") from e

    @staticmethod
    def _resolve_media_sources(media: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Turn caller-supplied media entries into filename/content pairs.

        Each entry supplies exactly one source: ``file_path`` (read from disk)
        or ``content`` (raw bytes the caller already holds, such as decoded
        base64). File reads are confined to the server workspace by
        :func:`validate_safe_path`, so a caller cannot use a comment to
        exfiltrate an arbitrary file from the host.

        Args:
            media: Ordered list of media entries.

        Returns:
            An ordered list of ``{"filename": str, "content": bytes}`` dicts.

        Raises:
            ValueError: If an entry names no source, names both, is missing a
                filename for inline content, escapes the workspace, does not
                exist, or exceeds the attachment size limit.
        """
        resolved: list[dict[str, Any]] = []

        for index, entry in enumerate(media):
            if not isinstance(entry, dict):
                raise ValueError(f"media[{index}] must be a JSON object.")

            file_path = entry.get("file_path")
            content = entry.get("content")
            filename = entry.get("filename")

            if file_path and content is not None:
                raise ValueError(
                    f"media[{index}]: provide 'file_path' OR inline content, not both."
                )

            if file_path:
                # Confine the read to the workspace before it happens: an
                # absolute or traversing path would otherwise let a caller
                # attach any file the server process can read.
                safe_path = validate_safe_path(file_path)
                if not safe_path.is_file():
                    raise ValueError(f"media[{index}]: file not found: {file_path}")
                content = safe_path.read_bytes()
                filename = filename or safe_path.name
            elif content is None:
                raise ValueError(f"media[{index}]: needs 'file_path' or content.")
            elif not filename:
                raise ValueError(
                    f"media[{index}]: 'filename' is required with inline content."
                )

            if not isinstance(content, bytes):
                raise ValueError(f"media[{index}]: content must be bytes.")
            if not content:
                raise ValueError(f"media[{index}]: content is empty.")
            if len(content) > ATTACHMENT_MAX_BYTES:
                raise ValueError(
                    f"media[{index}]: '{filename}' is {len(content)} bytes, which "
                    f"exceeds the {ATTACHMENT_MAX_BYTES} byte limit."
                )

            resolved.append({"filename": str(filename), "content": content})

        return resolved

    @staticmethod
    def _plan_media_comment(body: str, filenames: list[str]) -> list[dict[str, Any]]:
        """Split a Markdown body into ordered text and media placeholders.

        A placeholder is Markdown image syntax whose target is either
        ``media:<index>`` or the filename of a media entry. Image syntax that
        matches neither is left in the text, where ``markdown_to_adf`` handles
        it as ordinary Markdown. Media the body never references is appended
        after the text, in the order supplied.

        Args:
            body: The comment body in Markdown.
            filenames: Filenames of the resolved media entries, in order.

        Returns:
            An ordered list of ``{"type": "text", "text": ...}`` and
            ``{"type": "media", "index": ...}`` segments.

        Raises:
            ValueError: If a ``media:<index>`` placeholder is malformed or out
                of range.
        """
        by_name: dict[str, int] = {}
        for position, name in enumerate(filenames):
            # First occurrence wins, so duplicate filenames stay deterministic.
            by_name.setdefault(name, position)

        segments: list[dict[str, Any]] = []
        referenced: set[int] = set()
        cursor = 0

        for match in _MEDIA_PLACEHOLDER_RE.finditer(body):
            target = match.group(1)
            if target.startswith("media:"):
                raw_index = target[len("media:") :]
                if not raw_index.isdigit():
                    raise ValueError(
                        f"Invalid media placeholder '{target}': "
                        "expected 'media:<index>'."
                    )
                index = int(raw_index)
                if index >= len(filenames):
                    raise ValueError(
                        f"Media placeholder '{target}' refers to media[{index}], "
                        f"but only {len(filenames)} media entries were given."
                    )
            elif target in by_name:
                index = by_name[target]
            else:
                # Not one of ours, so leave it in the surrounding text.
                continue

            segments.append({"type": "text", "text": body[cursor : match.start()]})
            segments.append({"type": "media", "index": index})
            referenced.add(index)
            cursor = match.end()

        segments.append({"type": "text", "text": body[cursor:]})
        segments.extend(
            {"type": "media", "index": position}
            for position in range(len(filenames))
            if position not in referenced
        )
        return segments

    def add_comment_with_media(
        self,
        issue_key: str,
        body: str,
        media: list[dict[str, Any]],
        visibility: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Add a Jira Cloud comment whose body embeds images inline.

        Each media entry is uploaded as an issue attachment, its Media Services
        file UUID is resolved, and the image is embedded in the comment body at
        the position of its placeholder, giving the text -> screenshot -> text
        -> screenshot layout that a plain-text comment cannot express.

        If any step fails, every attachment uploaded during this call is
        deleted again, so a failed comment leaves no orphans behind.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            body: Comment body in Markdown, optionally containing
                ``![alt](media:0)`` or ``![alt](filename)`` placeholders
            media: Ordered media entries, each with ``file_path`` or raw
                ``content`` bytes (plus ``filename`` for inline content)
            visibility: (optional) Restrict comment visibility

        Returns:
            A dict with the created ``comment`` and the ``embedded``
            attachments (filename, attachment id, media id)

        Raises:
            ValueError: If the instance is not Cloud, or the media entries or
                placeholders are invalid
            Exception: If an upload, media-id resolution, or the comment post
                fails
        """
        if not self.config.is_cloud:
            raise ValueError("Inline media comments are supported on Jira Cloud only.")
        if not media:
            raise ValueError("At least one media entry is required.")

        # Validate and read every source before anything is uploaded, so bad
        # input never leaves a partial upload behind.
        resolved = self._resolve_media_sources(media)
        plan = self._plan_media_comment(body, [item["filename"] for item in resolved])

        uploaded_ids: list[str] = []
        embedded: list[dict[str, Any]] = []
        media_nodes: dict[int, dict[str, Any]] = {}

        # The attachment methods live on AttachmentsMixin, which JiraFetcher
        # composes alongside this mixin. Declaring the dependency by cast keeps
        # CommentsMixin instantiable on its own, which inheriting the Protocol
        # (whose members are abstract) would not.
        attachments = cast(AttachmentMediaOperationsProto, self)

        try:
            for index, item in enumerate(resolved):
                filename = item["filename"]
                content = item["content"]
                upload = attachments.upload_attachment_from_content(
                    issue_key, filename, content
                )
                if not upload.get("success"):
                    raise ValueError(
                        f"media[{index}]: attachment upload failed: "
                        f"{upload.get('error')}"
                    )

                attachment_id = upload.get("id")
                if not attachment_id:
                    raise ValueError(
                        f"media[{index}]: could not determine the attachment id "
                        "after upload."
                    )
                # Track immediately, so a later resolve/post failure rolls this
                # upload back too.
                uploaded_ids.append(str(attachment_id))

                media_id = attachments.get_attachment_media_id(str(attachment_id))
                if not media_id:
                    raise ValueError(
                        f"media[{index}]: could not resolve the Media Services "
                        f"id for attachment {attachment_id}. Jira Cloud's "
                        "attachment-content endpoint returned no parseable "
                        "media redirect (this happens behind some OAuth "
                        "gateways and proxies; the server log records the HTTP "
                        "status and redirect target)."
                    )

                node: dict[str, Any] = {"type": "media", "media_id": media_id}
                dimensions = get_image_dimensions(content)
                if dimensions is not None:
                    node["width"], node["height"] = dimensions
                media_nodes[index] = node
                embedded.append(
                    {
                        "filename": filename,
                        "attachment_id": str(attachment_id),
                        "media_id": media_id,
                    }
                )

            segments = [
                media_nodes[segment["index"]] if segment["type"] == "media" else segment
                for segment in plan
            ]
            adf_body = build_media_comment_adf(segments, self.config.url or "")
            comment = self.add_comment_adf(issue_key, adf_body, visibility)
        except Exception:
            self._rollback_attachments(issue_key, uploaded_ids)
            raise

        return {"comment": comment, "embedded": embedded}

    def _rollback_attachments(self, issue_key: str, attachment_ids: list[str]) -> None:
        """Best-effort deletion of attachments uploaded by a failed operation."""
        if not attachment_ids:
            return
        attachments = cast(AttachmentMediaOperationsProto, self)
        for attachment_id in attachment_ids:
            try:
                attachments.delete_attachment(attachment_id)
            except Exception as exc:  # noqa: BLE001 - cleanup must not mask the cause
                logger.warning(
                    "Failed to roll back attachment %s on %s: %s",
                    attachment_id,
                    issue_key,
                    exc,
                )
        logger.info(
            "Rolled back %d attachment(s) on %s after a failed media comment: %s",
            len(attachment_ids),
            issue_key,
            attachment_ids,
        )
