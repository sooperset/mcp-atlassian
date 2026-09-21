"""Module for Jira worklog operations."""

import logging
import re
from datetime import datetime
from typing import Any

import dateutil.parser
import dateutil.tz

from ..models import JiraWorklog
from ..models.jira import JiraWorkAttribute
from ..models.jira.adf import adf_to_text
from ..utils import parse_date
from .client import JiraClient
from .protocols import WorkAttributeOperationsProto

logger = logging.getLogger("mcp-jira")


class WorklogMixin(JiraClient):
    """Mixin for Jira worklog operations."""

    def _parse_time_spent(self, time_spent: str) -> int:
        """
        Parse time spent string into seconds.

        Args:
            time_spent: Time spent string (e.g. 1h 30m, 1d, etc.)

        Returns:
            Time spent in seconds
        """
        # Base case for direct specification in seconds
        if time_spent.endswith("s"):
            try:
                return int(time_spent[:-1])
            except ValueError:
                pass

        total_seconds = 0
        time_units = {
            "w": 7 * 24 * 60 * 60,  # weeks to seconds
            "d": 24 * 60 * 60,  # days to seconds
            "h": 60 * 60,  # hours to seconds
            "m": 60,  # minutes to seconds
        }

        # Regular expression to find time components like 1w, 2d, 3h, 4m
        pattern = r"(\d+)([wdhm])"
        matches = re.findall(pattern, time_spent)

        for value, unit in matches:
            # Convert value to int and multiply by the unit in seconds
            seconds = int(value) * time_units[unit]
            total_seconds += seconds

        if total_seconds == 0:
            # If we couldn't parse anything, try using the raw value
            try:
                return int(float(time_spent))  # Convert to float first, then to int
            except ValueError:
                # If all else fails, default to 60 seconds (1 minute)
                logger.warning(
                    f"Could not parse time: {time_spent}, defaulting to 60 seconds"
                )
                return 60

        return total_seconds

    def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        comment: str | None = None,
        started: str | None = None,
        original_estimate: str | None = None,
        remaining_estimate: str | None = None,
        worklog_attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Add a worklog entry to a Jira issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            time_spent: Time spent (e.g. '1h 30m', '3h', '1d')
            comment: Optional comment for the worklog
            started: Optional ISO8601 date time string for when work began.
                Tempo Timesheets requires ``yyyy-MM-ddTHH:mm:ss.SSS`` without
                a timezone offset; tz-aware values are converted to local time
                and the offset is dropped. Tempo also requires the field to be
                present, so omitting it logs the work at the current time.
            original_estimate: Optional new value for the original estimate
            remaining_estimate: Optional new value for the remaining estimate.
                Passed to Jira as a duration string (e.g. '3h'), which validates
                it; the Tempo path applies it right after the worklog is created.
                ``remaining_estimate_updated`` therefore reports whether Jira
                accepted the value, not merely that it was requested.
            worklog_attributes: Optional Tempo Core work attribute payload,
                keyed by the attribute ``key`` rather than by attribute ID,
                e.g. ``{"_WorkMode_": {"value": "office"}}``. Discover the
                available keys and the values each attribute accepts via
                ``get_work_attribute_catalog()``. Only supported on Jira
                Server/Data Center with Tempo Timesheets installed. When set,
                Tempo requires a non-empty ``comment``.

        Returns:
            Response data if successful

        Raises:
            ValueError: If the Tempo payload cannot be built, e.g. an empty
                comment, an unparsable ``started`` value, or an unknown work
                attribute key.
            Exception: If there's an error adding the worklog
        """
        try:
            if worklog_attributes and self.config.is_cloud:
                raise NotImplementedError(
                    "Tempo worklog attributes are only available on "
                    "Jira Server/Data Center."
                )

            # Convert time_spent string to seconds
            time_spent_seconds = self._parse_time_spent(time_spent)

            # Convert Markdown comment to Jira format if provided
            if comment:
                comment = self._markdown_to_jira(comment)

            # Step 1: Update original estimate if provided (separate API call)
            # The worklog is still created when that call fails.
            original_estimate_updated = False
            if original_estimate:
                original_estimate_updated = self._update_timetracking_estimate(
                    issue_key, "originalEstimate", original_estimate
                )

            # Step 2: Prepare worklog data
            worklog_data: dict[str, Any] = {"timeSpentSeconds": time_spent_seconds}
            if comment:
                worklog_data["comment"] = comment
            if started:
                worklog_data["started"] = started

            # Step 3: Add the worklog, adjusting the remaining estimate if asked
            remaining_estimate_updated = False
            if worklog_attributes:
                result = self._post_tempo_worklog(
                    issue_key=issue_key,
                    time_spent_seconds=time_spent_seconds,
                    comment=comment,
                    started=started,
                    worklog_attributes=worklog_attributes,
                )
                # Tempo's endpoint ignores Jira's `adjustEstimate` query params,
                # and its own `remainingEstimate` field is not part of the
                # contract verified against a live instance, so hand the raw
                # duration to Jira instead of re-encoding it into seconds. Doing
                # this after the POST mirrors the native semantics, where
                # `adjustEstimate=new` leaves the issue at exactly `newEstimate`.
                if remaining_estimate:
                    remaining_estimate_updated = self._update_timetracking_estimate(
                        issue_key, "remainingEstimate", remaining_estimate
                    )
            else:
                # Jira's native endpoints apply the estimate along with the
                # worklog itself, as query parameters.
                params: dict[str, str] = {}
                if remaining_estimate:
                    params["adjustEstimate"] = "new"
                    params["newEstimate"] = remaining_estimate
                    remaining_estimate_updated = True

                if (
                    isinstance(worklog_data.get("comment"), dict)
                    and self.config.is_cloud
                ):
                    result = self._post_api3(
                        f"issue/{issue_key}/worklog",
                        data=worklog_data,
                        params=params or None,
                    )
                else:
                    base_url = self.jira.resource_url("issue")
                    url = f"{base_url}/{issue_key}/worklog"
                    result = self.jira.post(url, data=worklog_data, params=params)
            if not isinstance(result, dict):
                msg = f"Unexpected return value type from `jira.post`: {type(result)}"
                logger.error(msg)
                raise TypeError(msg)

            # Format and return the result
            comment_raw = result.get("comment", "")
            comment_text = (
                adf_to_text(comment_raw)
                if isinstance(comment_raw, dict)
                else comment_raw
            )
            author_data = result.get("author")
            if isinstance(author_data, dict):
                author = author_data.get("displayName", "Unknown")
            else:
                author = result.get("workerKey", "Unknown")

            created = result.get("created", result.get("dateCreated", ""))
            updated = result.get("updated", result.get("dateUpdated", ""))
            started_value = result.get("started", result.get("startDate", ""))
            return {
                "id": result.get(
                    "id",
                    result.get("jiraWorklogId", result.get("tempoWorklogId")),
                ),
                "comment": self._clean_text(comment_text or ""),
                "created": str(parse_date(created)),
                "updated": str(parse_date(updated)),
                "started": str(parse_date(started_value)),
                "time_spent": result.get("timeSpent", ""),
                "time_spent_seconds": result.get("timeSpentSeconds", 0),
                "author": author,
                "original_estimate_updated": original_estimate_updated,
                "remaining_estimate_updated": remaining_estimate_updated,
                **(
                    {"attributes": result["attributes"]}
                    if "attributes" in result
                    else {}
                ),
            }
        except ValueError:
            # Payload validation errors are actionable as-is; keep the type so
            # callers can distinguish them from transport failures.
            raise
        except Exception as e:
            logger.error(f"Error adding worklog to issue {issue_key}: {str(e)}")
            raise Exception(f"Error adding worklog: {str(e)}") from e

    def _update_timetracking_estimate(
        self, issue_key: str, field: str, value: str
    ) -> bool:
        """Set one of the issue's time tracking estimates (best effort).

        The duration string is forwarded to Jira unchanged so that Jira decides
        whether it is a valid duration; converting it locally would turn
        malformed input into an arbitrary amount of logged time.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').
            field: Timetracking sub-field to set, e.g. 'originalEstimate'.
            value: Duration in Jira format (e.g. '3h', '2d').

        Returns:
            True if Jira accepted the new value, False if the call failed.
        """
        try:
            self.jira.edit_issue(
                issue_id_or_key=issue_key, fields={"timetracking": {field: value}}
            )
        except Exception as e:  # noqa: BLE001 - Intentional fallback with logging
            logger.error(f"Failed to update {field} for issue {issue_key}: {str(e)}")
            # Keep the failure visible to callers without discarding an already
            # created worklog.
            return False
        logger.info(f"Updated {field} for issue {issue_key}")
        return True

    def _post_tempo_worklog(
        self,
        issue_key: str,
        time_spent_seconds: int,
        comment: str | None,
        started: str | None,
        worklog_attributes: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a Data Center worklog through Tempo Timesheets v4.

        The endpoint takes a single JSON object (its response is a list) and is
        stricter than Jira's native worklog API. The contract below was
        verified against a live Jira Data Center + Tempo instance:

        - ``originTaskId`` is the numeric internal issue id, as a string;
        - ``worker`` is the internal Jira user key (``JIRAUSER12345``), not
          the username;
        - ``comment`` must not be empty;
        - ``started`` must carry no timezone offset;
        - every attribute value object needs ``name`` and ``workAttributeId``
          in addition to ``value``.

        Fields outside that contract are left at the live-verified values, in
        particular ``remainingEstimate``, which was never exercised: callers get
        their remaining estimate through Jira's timetracking instead.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').
            time_spent_seconds: Logged time in seconds.
            comment: Worklog comment (already converted to Jira markup).
            started: Optional ISO 8601 start timestamp, optionally tz-aware.
            worklog_attributes: Attributes keyed by Tempo attribute key.

        Returns:
            The created worklog as echoed by Tempo.

        Raises:
            ValueError: If the comment is empty, ``started`` cannot be parsed,
                or a work attribute cannot be resolved.
            TypeError: If Tempo returns an unexpected response shape.
        """
        if not comment or not comment.strip():
            raise ValueError(
                "Tempo worklogs with attributes require a non-empty comment; "
                "pass `comment` describing the logged work."
            )

        worklog_data: dict[str, Any] = {
            "attributes": self._build_tempo_worklog_attributes(worklog_attributes),
            "billableSeconds": "",
            "worker": self._get_current_user_key(),
            "comment": comment,
            "timeSpentSeconds": time_spent_seconds,
            "originTaskId": self._get_issue_internal_id(issue_key),
            # Never part of the verified contract, and Jira's own estimate is
            # updated separately by the caller.
            "remainingEstimate": None,
            "endDate": None,
            "includeNonWorkingDays": False,
            # Required in practice: omitting it fails with
            # 'Date can not be empty', despite being optional in the docs.
            "started": self._format_tempo_started(started),
        }

        result = self.jira.post(  # type: ignore[attr-defined]
            "rest/tempo-timesheets/4/worklogs",
            data=worklog_data,
        )
        if isinstance(result, list):
            if not result or not isinstance(result[0], dict):
                raise TypeError("Unexpected return value from Tempo worklog endpoint")
            result = result[0]

        if not isinstance(result, dict):
            raise TypeError("Unexpected return value from Tempo worklog endpoint")
        return result

    def _get_current_user_key(self) -> str:
        """Resolve the internal Jira user key that Tempo expects as `worker`.

        `UsersMixin.get_current_user_account_id()` is deliberately not reused:
        it prefers the Cloud ``accountId`` and falls back to ``name``, neither
        of which Tempo accepts as a worker.

        Returns:
            The internal user key (e.g. 'JIRAUSER12345').

        Raises:
            TypeError: If Jira returns a non-object response.
            ValueError: If the response carries no internal user key.
        """
        myself = self.jira.myself()  # type: ignore[attr-defined]
        if not isinstance(myself, dict):
            raise TypeError(
                f"Unexpected return value type from `jira.myself`: "
                f"{type(myself).__name__}"
            )

        user_key = myself.get("key")
        if not isinstance(user_key, str) or not user_key:
            raise ValueError(
                "Could not resolve the internal Jira user key required by "
                "Tempo worklogs; `myself` returned no 'key'."
            )
        return user_key

    def _get_issue_internal_id(self, issue_key: str) -> str:
        """Fetch the numeric internal id of an issue.

        Tempo's worklog API keys worklogs by internal issue id rather than by
        issue key, so callers cannot pass what they normally type.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123').

        Returns:
            The internal issue id as a string (e.g. '100500').

        Raises:
            TypeError: If Jira returns a non-object response.
            ValueError: If Jira returns no issue id.
        """
        result = self.jira.get(  # type: ignore[attr-defined]
            f"rest/api/2/issue/{issue_key}?fields=id"
        )
        if not isinstance(result, dict):
            raise TypeError(
                "Unexpected return value type from the issue API: "
                f"{type(result).__name__}"
            )

        issue_id = result.get("id")
        if issue_id is None or str(issue_id) == "":
            raise ValueError(f"Jira returned no internal id for issue {issue_key}.")
        return str(issue_id)

    @staticmethod
    def _format_tempo_started(started: str | None) -> str:
        """Normalize an ISO 8601 timestamp for Tempo's `started` field.

        Tempo rejects timezone offsets ('Date is invalid'), so tz-aware values
        are converted to local time and the offset is dropped. The field is
        required even though the API documentation marks it optional; sending
        no value fails with 'Date can not be empty'.

        Args:
            started: ISO 8601 timestamp, optionally tz-aware. `None` logs the
                work at the current local time.

        Returns:
            Timestamp as 'yyyy-MM-ddTHH:mm:ss.SSS' without an offset.

        Raises:
            ValueError: If the value cannot be parsed as a timestamp.
        """
        if started is None:
            started = datetime.now(tz=dateutil.tz.tzlocal()).isoformat()
        try:
            parsed = dateutil.parser.parse(started)
        except (ValueError, OverflowError, TypeError) as e:
            raise ValueError(
                f"Unable to parse started={started!r}; expected an ISO 8601 "
                "timestamp in the form 'yyyy-MM-ddTHH:mm:ss.SSS' "
                "(e.g. '2026-09-11T08:00:00.000')."
            ) from e

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

    def _build_tempo_worklog_attributes(
        self, worklog_attributes: dict[str, Any]
    ) -> dict[str, Any]:
        """Complete caller-supplied attributes for the Tempo v4 payload.

        Callers only provide the value, e.g.
        ``{"_WorkMode_": {"value": "office"}}``, while Tempo also requires
        ``name`` and ``workAttributeId``. Both are resolved through the work
        attribute catalog unless the caller already supplied them.

        Args:
            worklog_attributes: Attributes keyed by Tempo attribute key.

        Returns:
            The attribute payload to send to Tempo.

        Raises:
            ValueError: If an entry is malformed, the catalog cannot be
                fetched, or an attribute key is unknown.
        """
        entries: dict[str, Any] = {}
        unresolved: list[str] = []

        for key, raw in worklog_attributes.items():
            if not isinstance(raw, dict):
                raise ValueError(
                    f"Work attribute {key} must be an object containing a "
                    f"'value' field, got {type(raw).__name__}."
                )
            if "value" not in raw:
                raise ValueError(
                    f"Work attribute {key} is missing the required 'value' field."
                )

            entry = dict(raw)
            entries[key] = entry
            if entry.get("name") is None or entry.get("workAttributeId") is None:
                unresolved.append(key)

        if unresolved:
            catalog = self._get_work_attribute_catalog_index(unresolved)
            for key in unresolved:
                attribute = catalog.get(key)
                if attribute is None:
                    raise ValueError(
                        f"Unknown Tempo work attribute key {key}. Discover the "
                        "available keys with jira_get_issue "
                        "include='worklog_attributes'."
                    )
                entry = entries[key]
                if entry.get("name") is None:
                    entry["name"] = attribute.name
                if entry.get("workAttributeId") is None:
                    entry["workAttributeId"] = attribute.id

        return entries

    def _get_work_attribute_catalog_index(
        self, missing_keys: list[str]
    ) -> dict[str, JiraWorkAttribute]:
        """Load the Tempo work attribute catalog keyed by attribute key.

        `WorklogMixin` is composed with `WorkAttributeMixin` in `JiraFetcher`
        but does not inherit from it, so the collaborator is looked up
        explicitly instead of assumed.

        Args:
            missing_keys: Attribute keys being resolved, used to make the
                error message actionable.

        Returns:
            Catalog entries keyed by Tempo attribute key.

        Raises:
            ValueError: If the catalog is unavailable or cannot be fetched.
        """
        keys = ", ".join(sorted(missing_keys))
        if not isinstance(self, WorkAttributeOperationsProto):
            raise ValueError(
                "The Tempo work attribute catalog is unavailable in this "
                f"client, so the attribute key(s) {keys} cannot be resolved."
            )

        try:
            catalog = self.get_work_attribute_catalog()
        except (NotImplementedError, TypeError, OSError) as e:
            raise ValueError(
                "Could not fetch the Tempo work attribute catalog needed to "
                f"resolve the attribute key(s) {keys}: {e}"
            ) from e

        return {attribute.key: attribute for attribute in catalog}

    def get_worklog(self, issue_key: str) -> dict[str, Any]:
        """
        Get the worklog data for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            Raw worklog data from the API
        """
        try:
            return self.jira.worklog(issue_key)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning(f"Error getting worklog for {issue_key}: {e}")
            return {"worklogs": []}

    def get_worklog_models(self, issue_key: str) -> list[JiraWorklog]:
        """
        Get all worklog entries for an issue as JiraWorklog models.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of JiraWorklog models
        """
        worklog_data = self.get_worklog(issue_key)
        result: list[JiraWorklog] = []

        if "worklogs" in worklog_data and worklog_data["worklogs"]:
            for log_data in worklog_data["worklogs"]:
                worklog = JiraWorklog.from_api_response(log_data)
                result.append(worklog)

        return result

    def get_worklogs(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all worklog entries for an issue.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')

        Returns:
            List of worklog entries

        Raises:
            Exception: If there's an error getting the worklogs
        """
        try:
            # `jira.issue_get_worklog()` calls GET /issue/{key}/worklog without
            # pagination parameters, so Jira returns at most 20 entries by default.
            # We paginate explicitly to retrieve all worklogs regardless of count.
            base_url = self.jira.resource_url("issue")
            url = f"{base_url}/{issue_key}/worklog"
            page_size = 100
            start_at = 0
            worklogs = []

            while True:
                result = self.jira.get(
                    url, params={"maxResults": page_size, "startAt": start_at}
                )
                if not isinstance(result, dict):
                    msg = (
                        f"Unexpected return value type from worklog API: {type(result)}"
                    )
                    logger.error(msg)
                    raise TypeError(msg)

                page = result.get("worklogs", [])
                for worklog in page:
                    worklogs.append(
                        {
                            "id": worklog.get("id"),
                            "comment": self._clean_text(worklog.get("comment", "")),
                            "created": str(parse_date(worklog.get("created", ""))),
                            "updated": str(parse_date(worklog.get("updated", ""))),
                            "started": str(parse_date(worklog.get("started", ""))),
                            "time_spent": worklog.get("timeSpent", ""),
                            "time_spent_seconds": worklog.get("timeSpentSeconds", 0),
                            "author": worklog.get("author", {}).get(
                                "displayName", "Unknown"
                            ),
                        }
                    )

                start_at += len(page)
                if start_at >= result.get("total", 0) or not page:
                    break

            return worklogs
        except Exception as e:
            logger.error(f"Error getting worklogs for issue {issue_key}: {str(e)}")
            raise Exception(f"Error getting worklogs: {str(e)}") from e

    def search_worklogs(
        self,
        from_date: str,
        to_date: str,
        worker_keys: list[str] | None = None,
        task_keys: list[str] | None = None,
        project_keys: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Find existing worklogs through Tempo Timesheets v4.

        This is the only read path that exposes the Tempo work attributes of
        worklogs that already exist: Jira's native `/issue/{key}/worklog`
        endpoint used by `get_worklogs()` never returns them. The contract below
        was verified against a live Jira Data Center + Tempo instance:

        - the endpoint is POST-only, and a GET answers 404 rather than 405;
        - `from` and `to` are both required and filter on the worklog's
          `started` date, not on the moment the work was logged, so a
          back-dated entry is absent from the day it was recorded;
        - the response is an unpaged array, so a query that narrows nothing
          returns every worklog in the range across all projects. That is both
          a payload hazard and a disclosure hazard, hence the requirement for
          a worker, task, or project filter.

        Args:
            from_date: First started date to include, 'yyyy-MM-dd'.
            to_date: Last started date to include, 'yyyy-MM-dd'.
            worker_keys: Internal Jira user keys (e.g. 'JIRAUSER12345') to
                search for. `None` restricts the search to the authenticated
                user; an empty list means 'any worker' and then `task_keys` or
                `project_keys` becomes mandatory.
            task_keys: Issue keys to filter by (e.g. ['PROJ-123']).
            project_keys: Project keys to filter by (e.g. ['PROJ']).
            limit: Maximum number of worklogs to return. The endpoint itself
                does not paginate, so this caps the already-fetched result set.

        Returns:
            Dict with the applied filters, `count`/`total_matched`/`truncated`,
            and `worklogs` sorted by started date. Each worklog carries Tempo
            `attributes` verbatim when the instance has them.

        Raises:
            NotImplementedError: If connected to Jira Cloud.
            ValueError: If a date is malformed, the range is reversed, or an
                all-worker search carries no narrowing filter.
            TypeError: If Tempo returns a response with an unexpected shape.
            Exception: If the search request itself fails.
        """
        if self.config.is_cloud:
            raise NotImplementedError(
                "Worklog search is only available on Jira Server/Data Center "
                "with Tempo Timesheets installed."
            )

        start = self._validate_tempo_search_date(from_date, "from_date")
        end = self._validate_tempo_search_date(to_date, "to_date")
        if start > end:
            raise ValueError(
                f"from_date={start} is after to_date={end}; expected an "
                "ascending, inclusive range."
            )

        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}.")

        workers = (
            [self._get_current_user_key()]
            if worker_keys is None
            else [worker.strip() for worker in worker_keys if worker.strip()]
        )
        tasks = [
            key.strip()
            for key in task_keys or ()
            if isinstance(key, str) and key.strip()
        ]
        projects = [
            key.strip()
            for key in project_keys or ()
            if isinstance(key, str) and key.strip()
        ]
        if not workers and not tasks and not projects:
            raise ValueError(
                "Searching worklogs for every worker needs at least one of "
                "`task_keys` or `project_keys`; an unfiltered search returns "
                f"every worklog between {start} and {end}."
            )

        payload: dict[str, Any] = {"from": start, "to": end}
        if workers:
            payload["worker"] = workers
        if tasks:
            payload["taskKey"] = tasks
        if projects:
            payload["projectKey"] = projects

        try:
            result = self.jira.post(  # type: ignore[attr-defined]
                "rest/tempo-timesheets/4/worklogs/search",
                data=payload,
            )
        except Exception as e:
            logger.error(f"Error searching worklogs from {start} to {end}: {str(e)}")
            raise Exception(f"Error searching worklogs: {str(e)}") from e

        if not isinstance(result, list):
            raise TypeError(
                "Unexpected return value type from Tempo worklog search API: "
                f"{type(result).__name__}"
            )
        if not all(isinstance(row, dict) for row in result):
            raise TypeError("Unexpected worklog entry in Tempo worklog search response")

        worklogs = sorted(
            (self._simplify_tempo_worklog(row) for row in result),
            key=lambda worklog: (worklog["started"], worklog["issue_key"]),
        )
        page = worklogs[:limit]
        return {
            "from_date": start,
            "to_date": end,
            "workers": workers or ["*"],
            "count": len(page),
            "total_matched": len(worklogs),
            "truncated": len(worklogs) > len(page),
            "worklogs": page,
        }

    @staticmethod
    def _validate_tempo_search_date(value: str, field: str) -> str:
        """Validate one Tempo search date and normalize it to 'yyyy-MM-dd'.

        Tempo answers these failures with an opaque validation error, so the
        value is checked before it leaves the client.

        Args:
            value: Caller-supplied date string.
            field: Parameter name, used in the error message.

        Returns:
            The date as 'yyyy-MM-dd'.

        Raises:
            ValueError: If the value is not a 'yyyy-MM-dd' date.
        """
        try:
            # A calendar date only: no timezone semantics exist here, so the
            # naive datetime DTZ007 warns about is intentional.
            parsed = datetime.strptime(value.strip(), "%Y-%m-%d")  # noqa: DTZ007
        except (AttributeError, ValueError) as e:
            raise ValueError(
                f"{field}={value!r} is not a valid date; expected 'yyyy-MM-dd' "
                "(e.g. '2026-09-10')."
            ) from e
        return parsed.strftime("%Y-%m-%d")

    def _simplify_tempo_worklog(self, row: dict[str, Any]) -> dict[str, Any]:
        """Map one Tempo v4 worklog bean onto the repo's worklog dict shape.

        The live response does not use the names Tempo's own OpenAPI spec
        documents: `started` replaces `startDate`, `worker` replaces
        `workerKey`, and `jiraWorklogId` is absent altogether. Both spellings
        are read so either response shape maps correctly.

        Args:
            row: One entry from the Tempo worklog search response.

        Returns:
            Simplified worklog dict, carrying `attributes` when present.
        """
        issue = row.get("issue") if isinstance(row.get("issue"), dict) else {}
        started = row.get("started") or row.get("startDate") or ""
        created = row.get("dateCreated") or row.get("created") or ""
        updated = row.get("dateUpdated") or row.get("updated") or ""
        worklog_id = row.get("tempoWorklogId", row.get("jiraWorklogId"))
        seconds = row.get("timeSpentSeconds", 0)

        try:
            time_spent_seconds = int(seconds) if seconds is not None else 0
        except (TypeError, ValueError):
            time_spent_seconds = 0

        result: dict[str, Any] = {
            "id": str(worklog_id) if worklog_id is not None else "",
            "issue_key": issue.get("key", ""),
            "issue_summary": issue.get("summary", ""),
            "project_key": issue.get("projectKey", ""),
            "epic_key": issue.get("epicKey", ""),
            "started": str(parse_date(started)) if started else "",
            "created": str(parse_date(created)) if created else "",
            "updated": str(parse_date(updated)) if updated else "",
            "time_spent": row.get("timeSpent", ""),
            "time_spent_seconds": time_spent_seconds,
            "author": row.get("worker") or row.get("workerKey") or "Unknown",
            "comment": self._clean_text(row.get("comment") or ""),
        }
        attributes = row.get("attributes")
        if attributes:
            result["attributes"] = attributes
        return result
