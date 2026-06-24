"""Planning layer for guided Jira issue transitions."""

import hashlib
import json
import secrets
from typing import Any

from ..models.jira.transition_plan import (
    TransitionFieldPlan,
    TransitionFieldSource,
    TransitionFieldValue,
    TransitionPlan,
    TransitionPlanStatus,
    TransitionStaleChecks,
)
from .client import JiraClient
from .transition_comments import extract_comment_evidence
from .transition_profiles import get_transition_profile
from .transition_schema import (
    format_transition_field_value,
    is_empty_transition_value,
    parse_transition_field,
    schema_hash_for_transition,
)


class TransitionPlanningMixin(JiraClient):
    """Prepare context-aware Jira transition plans."""

    def prepare_transition_plan(
        self,
        issue_key: str,
        target_transition_id: str | None = None,
        target_transition_name: str | None = None,
        target_status: str | None = None,
        profile: str | None = None,
        work_context: dict[str, Any] | None = None,
    ) -> TransitionPlan:
        """Prepare a transition plan without mutating Jira."""
        issue = self._get_transition_issue(issue_key)
        transitions = self._get_available_transition_dicts(issue_key)
        transition = self._resolve_transition(
            transitions,
            target_transition_id=target_transition_id,
            target_transition_name=target_transition_name,
            target_status=target_status,
        )

        transition_profile = get_transition_profile(profile)
        fields = transition.get("fields")
        if not isinstance(fields, dict):
            fields = {}

        parsed_fields = [
            parse_transition_field(
                field_key,
                field_meta,
                self._get_current_issue_field_value(issue, field_key),
                effective_required=self._is_profile_soft_required(
                    transition,
                    field_meta,
                    transition_profile,
                ),
            )
            for field_key, field_meta in sorted(fields.items())
            if isinstance(field_meta, dict)
        ]

        comments_response = self._get_raw_issue_comments(issue_key)
        assignee_name, assignee_key = self._get_issue_assignee_identity(issue)
        comment_context = extract_comment_evidence(
            comments_response,
            assignee_name=assignee_name,
            assignee_key=assignee_key,
        )
        if work_context:
            comment_context["work_context"] = work_context

        schema_hash = schema_hash_for_transition(transition)
        transition_id = str(transition.get("id", ""))
        issue_updated = str(getattr(issue, "updated", "") or "")
        stale_checks = TransitionStaleChecks(
            issue_updated=issue_updated,
            status_id=self._get_issue_status_id(issue),
            transition_id=transition_id,
            schema_hash=schema_hash,
            latest_comment_id=self._latest_comment_value(comments_response, "id"),
            latest_comment_updated=self._latest_comment_value(
                comments_response, "updated"
            ),
            comment_fingerprints=self._comment_fingerprints(comments_response),
        )

        return TransitionPlan(
            plan_id=self._new_transition_plan_id(),
            issue_key=issue_key,
            transition_id=transition_id,
            transition_name=str(transition.get("name", "")),
            to_status=self._get_transition_target_status(transition),
            schema_hash=schema_hash,
            issue_updated=issue_updated,
            profile=profile,
            fields=parsed_fields,
            comment_context=comment_context,
            stale_checks=stale_checks,
        )

    def update_transition_plan(
        self,
        plan: TransitionPlan,
        field_values: dict[str, Any],
        cleared_fields: list[str] | None = None,
    ) -> TransitionPlan:
        """Update user-selected field values on a transition plan."""
        fields_by_key = {field.field_key: field for field in plan.fields}

        for field_key, value in field_values.items():
            field = fields_by_key.get(field_key)
            if field is None:
                plan.warnings.append(f"Ignored unknown transition field: {field_key}")
                continue
            field.user_value = TransitionFieldValue(
                value=value,
                source=TransitionFieldSource.USER_SELECTION,
                changed=True,
            )

        for field_key in cleared_fields or []:
            field = fields_by_key.get(field_key)
            if field is None:
                plan.warnings.append(f"Ignored unknown cleared field: {field_key}")
                continue
            field.user_value = TransitionFieldValue(
                value=[] if field.value_format == "array_of_id_objects" else None,
                source=TransitionFieldSource.USER_SELECTION,
                changed=True,
                destructive=True,
            )

        return plan

    def preview_transition_plan(self, plan: TransitionPlan) -> dict[str, Any]:
        """Compose the Jira transition payload without applying it."""
        freshness = self.validate_transition_plan_freshness(plan)
        if freshness["hard_stale"]:
            plan.status = TransitionPlanStatus.STALE
            return {
                "status": "stale",
                "freshness": freshness,
            }

        preview = self._compose_transition_preview(plan)
        preview["freshness"] = freshness
        return preview

    def _compose_transition_preview(self, plan: TransitionPlan) -> dict[str, Any]:
        """Compose the Jira transition payload after freshness checks."""
        payload: dict[str, Any] = {"transition": {"id": plan.transition_id}}
        payload_fields: dict[str, Any] = {}
        field_sources: dict[str, str] = {}
        changed_fields: list[str] = []
        unchanged_reused_fields: list[str] = []
        destructive_changes: list[str] = []
        missing_fields: list[dict[str, str]] = []
        soft_missing_fields: list[dict[str, str]] = []

        for field in plan.fields:
            selected = self._select_field_value(field)
            field.final_value = selected

            if selected.destructive:
                payload_fields[field.field_key] = format_transition_field_value(
                    field, selected.value
                )
                field_sources[field.field_key] = selected.source.value
                changed_fields.append(field.field_key)
                destructive_changes.append(field.field_key)
                continue

            if is_empty_transition_value(selected.value):
                if field.required:
                    missing_fields.append(
                        {"field_key": field.field_key, "name": field.name}
                    )
                elif field.required_level == "soft":
                    soft_missing_fields.append(
                        {"field_key": field.field_key, "name": field.name}
                    )
                continue

            payload_fields[field.field_key] = format_transition_field_value(
                field, selected.value
            )
            field_sources[field.field_key] = selected.source.value
            if selected.source == TransitionFieldSource.CURRENT_ISSUE:
                unchanged_reused_fields.append(field.field_key)
            else:
                changed_fields.append(field.field_key)

        if payload_fields:
            payload["fields"] = payload_fields

        payload_hash = self._hash_payload(payload)
        preview_id = f"pv_{payload_hash[:16]}"
        plan.last_preview_id = preview_id
        plan.last_payload_hash = payload_hash
        plan.status = TransitionPlanStatus.PREVIEWED

        return {
            "payload": payload,
            "field_sources": field_sources,
            "changed_fields": changed_fields,
            "unchanged_reused_fields": unchanged_reused_fields,
            "destructive_changes": destructive_changes,
            "missing_fields": missing_fields,
            "soft_missing_fields": soft_missing_fields,
            "preview_id": preview_id,
            "payload_hash": payload_hash,
        }

    def validate_transition_plan_freshness(
        self, plan: TransitionPlan
    ) -> dict[str, Any]:
        """Validate that a prepared transition plan still matches Jira state."""
        reasons: list[str] = []
        hard_stale = False
        requires_reconfirmation = False

        stale_checks = plan.stale_checks
        issue = self._get_transition_issue(plan.issue_key)
        current_status_id = self._get_issue_status_id(issue)
        if (
            stale_checks
            and stale_checks.status_id
            and current_status_id != stale_checks.status_id
        ):
            hard_stale = True
            reasons.append("issue status changed")

        current_issue_updated = str(getattr(issue, "updated", "") or "")
        if (
            stale_checks
            and stale_checks.issue_updated
            and current_issue_updated != stale_checks.issue_updated
        ):
            hard_stale = True
            reasons.append("issue was updated after planning")

        transitions = self._get_available_transition_dicts(plan.issue_key)
        transition = self._find_transition_by_id(transitions, plan.transition_id)
        if transition is None:
            hard_stale = True
            reasons.append("transition is no longer available")
        elif stale_checks and schema_hash_for_transition(transition) != (
            stale_checks.schema_hash
        ):
            hard_stale = True
            reasons.append("transition schema changed")

        comments_response = self._get_raw_issue_comments(plan.issue_key)
        if stale_checks:
            changed_comments = self._changed_comment_fingerprints(
                previous=stale_checks.comment_fingerprints,
                current=self._comment_fingerprints(comments_response),
            )
            if not stale_checks.comment_fingerprints:
                changed_comments = self._legacy_changed_latest_comment(
                    stale_checks,
                    comments_response,
                )
            if changed_comments:
                assignee_name, assignee_key = self._get_issue_assignee_identity(issue)
                evidence = extract_comment_evidence(
                    comments_response,
                    assignee_name=assignee_name,
                    assignee_key=assignee_key,
                )
                if self._has_changed_high_value_comment(evidence, changed_comments):
                    requires_reconfirmation = True
                    reasons.append("new high-value assignee comment")

        fresh = not hard_stale and not requires_reconfirmation
        return {
            "fresh": fresh,
            "hard_stale": hard_stale,
            "requires_reconfirmation": requires_reconfirmation,
            "reasons": reasons,
        }

    def apply_transition_plan(
        self,
        plan: TransitionPlan,
        *,
        confirmed: bool = False,
        payload_hash: str | None = None,
    ) -> dict[str, Any]:
        """Apply a prepared transition plan after confirmation checks."""
        if plan.status == TransitionPlanStatus.APPLIED:
            return {"success": False, "status": "already_applied"}

        freshness = self.validate_transition_plan_freshness(plan)
        if freshness["hard_stale"]:
            plan.status = TransitionPlanStatus.STALE
            return {
                "success": False,
                "status": "stale",
                "freshness": freshness,
            }
        if freshness["requires_reconfirmation"]:
            return {
                "success": False,
                "status": "reconfirmation_required",
                "freshness": freshness,
            }

        if confirmed:
            if (
                plan.status != TransitionPlanStatus.PREVIEWED
                or not plan.last_payload_hash
            ):
                return {
                    "success": False,
                    "status": "preview_required",
                    "freshness": freshness,
                }
            if payload_hash != plan.last_payload_hash:
                return {
                    "success": False,
                    "status": "payload_hash_mismatch",
                    "freshness": freshness,
                }

        preview = self._compose_transition_preview(plan)
        if preview["missing_fields"]:
            plan.status = TransitionPlanStatus.NEEDS_USER_INPUT
            return {
                "success": False,
                "status": "missing_fields",
                "preview": preview,
                "freshness": freshness,
            }

        if not confirmed:
            return {
                "success": False,
                "status": "confirmation_required",
                "preview": preview,
                "freshness": freshness,
            }

        if payload_hash != preview["payload_hash"]:
            return {
                "success": False,
                "status": "payload_hash_mismatch",
                "preview": preview,
                "freshness": freshness,
            }

        payload = preview["payload"]
        fields = payload.get("fields") if isinstance(payload, dict) else None
        result = self.transition_issue(  # type: ignore[attr-defined]
            plan.issue_key,
            plan.transition_id,
            fields=fields,
        )
        plan.status = TransitionPlanStatus.APPLIED

        issue = (
            result.to_simplified_dict()
            if hasattr(result, "to_simplified_dict")
            else result
        )
        return {
            "success": True,
            "status": "applied",
            "issue": issue,
            "preview": preview,
            "freshness": freshness,
        }

    def _get_transition_issue(self, issue_key: str) -> Any:
        return self.get_issue(issue_key, fields="*all", comment_limit=0)  # type: ignore[attr-defined]

    def _get_available_transition_dicts(
        self, issue_key: str
    ) -> list[dict[str, Any]]:
        transitions = self.get_available_transitions(  # type: ignore[attr-defined]
            issue_key, response_mode="full"
        )
        if not isinstance(transitions, list):
            return []
        return [item for item in transitions if isinstance(item, dict)]

    def _resolve_transition(
        self,
        transitions: list[dict[str, Any]],
        *,
        target_transition_id: str | None,
        target_transition_name: str | None,
        target_status: str | None,
    ) -> dict[str, Any]:
        for transition in transitions:
            if target_transition_id and str(transition.get("id")) == str(
                target_transition_id
            ):
                return transition
            if (
                target_transition_name
                and transition.get("name") == target_transition_name
            ):
                return transition
            if target_status and self._get_transition_target_status(
                transition
            ) == target_status:
                return transition

        target = target_transition_id or target_transition_name or target_status
        msg = f"Transition not found for target: {target}"
        raise ValueError(msg)

    @staticmethod
    def _get_transition_target_status(transition: dict[str, Any]) -> str | None:
        to_status = transition.get("to_status")
        if to_status:
            return str(to_status)
        to_data = transition.get("to")
        if isinstance(to_data, dict) and to_data.get("name"):
            return str(to_data["name"])
        return None

    @staticmethod
    def _is_profile_soft_required(
        transition: dict[str, Any],
        field_meta: dict[str, Any],
        transition_profile: dict[str, Any],
    ) -> bool:
        if not transition_profile.get("soft_required"):
            return False
        transitions = transition_profile.get("transitions")
        if isinstance(transitions, list) and transition.get("name") not in transitions:
            return False
        fields = transition_profile.get("fields")
        field_name = field_meta.get("name")
        return isinstance(fields, dict) and field_name in fields

    @staticmethod
    def _get_current_issue_field_value(issue: Any, field_key: str) -> Any:
        custom_fields = getattr(issue, "custom_fields", None)
        if isinstance(custom_fields, dict) and field_key in custom_fields:
            custom_value = custom_fields[field_key]
            if isinstance(custom_value, dict) and "value" in custom_value:
                return custom_value["value"]
            return custom_value

        value = getattr(issue, field_key, None)
        to_simplified_dict = getattr(value, "to_simplified_dict", None)
        if callable(to_simplified_dict):
            return to_simplified_dict()
        return value

    def _get_raw_issue_comments(self, issue_key: str) -> dict[str, Any]:
        comments = self.jira.issue_get_comments(issue_key)
        return comments if isinstance(comments, dict) else {"comments": []}

    @staticmethod
    def _get_issue_assignee_identity(issue: Any) -> tuple[str | None, str | None]:
        assignee = getattr(issue, "assignee", None)
        if assignee is None:
            return None, None
        name = getattr(assignee, "username", None) or getattr(
            assignee, "display_name", None
        )
        key = getattr(assignee, "user_key", None) or getattr(
            assignee, "account_id", None
        )
        return str(name) if name else None, str(key) if key else None

    @staticmethod
    def _get_issue_status_id(issue: Any) -> str | None:
        status = getattr(issue, "status", None)
        status_id = getattr(status, "id", None)
        return str(status_id) if status_id else None

    @staticmethod
    def _latest_comment_value(
        comments_response: dict[str, Any],
        key: str,
    ) -> str | None:
        comments = comments_response.get("comments")
        if not isinstance(comments, list) or not comments:
            return None
        latest = comments[-1]
        if not isinstance(latest, dict):
            return None
        value = latest.get(key)
        return str(value) if value else None

    @staticmethod
    def _comment_fingerprints(comments_response: dict[str, Any]) -> dict[str, str]:
        comments = comments_response.get("comments")
        if not isinstance(comments, list):
            return {}

        fingerprints: dict[str, str] = {}
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            comment_id = comment.get("id")
            if not comment_id:
                continue
            updated = comment.get("updated") or comment.get("created") or ""
            fingerprints[str(comment_id)] = str(updated)
        return fingerprints

    @staticmethod
    def _changed_comment_fingerprints(
        *,
        previous: dict[str, str],
        current: dict[str, str],
    ) -> dict[str, str]:
        return {
            comment_id: updated
            for comment_id, updated in current.items()
            if previous.get(comment_id) != updated
        }

    def _legacy_changed_latest_comment(
        self,
        stale_checks: TransitionStaleChecks,
        comments_response: dict[str, Any],
    ) -> dict[str, str]:
        latest_comment_id = self._latest_comment_value(comments_response, "id")
        latest_comment_updated = self._latest_comment_value(
            comments_response, "updated"
        )
        if (
            latest_comment_id != stale_checks.latest_comment_id
            or latest_comment_updated != stale_checks.latest_comment_updated
        ):
            return {str(latest_comment_id): str(latest_comment_updated)}
        return {}

    @staticmethod
    def _new_transition_plan_id() -> str:
        return f"tp_{secrets.token_urlsafe(18)}"

    @staticmethod
    def _find_transition_by_id(
        transitions: list[dict[str, Any]],
        transition_id: str,
    ) -> dict[str, Any] | None:
        for transition in transitions:
            if str(transition.get("id")) == transition_id:
                return transition
        return None

    @staticmethod
    def _has_changed_high_value_comment(
        evidence: dict[str, Any],
        changed_comments: dict[str, str],
    ) -> bool:
        high_value_comments = evidence.get("high_value_comments")
        if not isinstance(high_value_comments, list):
            return False
        for comment in high_value_comments:
            if not isinstance(comment, dict):
                continue
            comment_id = comment.get("comment_id")
            if comment_id is None:
                continue
            updated = changed_comments.get(str(comment_id))
            if updated is None:
                continue
            if str(comment.get("updated")) == updated and int(
                comment.get("weight", 0)
            ) >= 5:
                return True
        return False

    @staticmethod
    def _select_field_value(field: TransitionFieldPlan) -> TransitionFieldValue:
        if field.user_value is not None:
            return field.user_value
        if field.auto_draft is not None and not is_empty_transition_value(
            field.auto_draft.value
        ):
            return field.auto_draft
        if not is_empty_transition_value(field.current_value):
            return TransitionFieldValue(
                value=field.current_value,
                source=TransitionFieldSource.CURRENT_ISSUE,
            )
        return TransitionFieldValue(
            value=None,
            source=TransitionFieldSource.EMPTY,
        )

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
