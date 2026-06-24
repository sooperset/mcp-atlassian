"""Utilities for parsing Jira transition field schemas."""

import hashlib
import json
from typing import Any

from ..models.jira.transition_plan import TransitionFieldPlan

VERSION_LOOKUP_TOOL = "jira_search_transition_field_options"


def parse_transition_field(
    field_key: str,
    field_meta: dict[str, Any],
    current_value: Any = None,
    *,
    effective_required: bool = False,
) -> TransitionFieldPlan:
    """Parse a Jira transition screen field into interaction metadata."""
    schema = field_meta.get("schema")
    if not isinstance(schema, dict):
        schema = {}

    field_type = schema.get("type")
    items = schema.get("items")
    custom_type = str(schema.get("custom", ""))
    allowed_values = field_meta.get("allowedValues")

    interaction_type = "text_input"
    value_format = "raw"
    lookup_tool = None
    needs_user_input = False

    if field_type == "user":
        interaction_type = "user_auto_or_picker"
        value_format = "user_object"
    elif field_type == "array" and items == "version":
        interaction_type = "version_picker"
        value_format = "array_of_id_objects"
        lookup_tool = VERSION_LOOKUP_TOOL
        needs_user_input = True
    elif field_type == "array" and isinstance(allowed_values, list):
        interaction_type = "multi_option_picker"
        value_format = "array_of_id_objects"
        needs_user_input = True
    elif field_type in {"option", "option-with-child"}:
        interaction_type = "single_option_picker"
        value_format = "id_object"
        needs_user_input = True
    elif field_type == "string" and (
        "textarea" in custom_type or "textfield" in custom_type
    ):
        interaction_type = "textarea"
        value_format = "string"
    elif field_type == "string":
        interaction_type = "text_input"
        value_format = "string"
    elif field_type == "number":
        interaction_type = "number_input"
        value_format = "number"

    required = bool(field_meta.get("required"))
    required_level = (
        "hard" if required else "soft" if effective_required else "optional"
    )

    operations = field_meta.get("operations")
    if not isinstance(operations, list):
        operations = []

    return TransitionFieldPlan(
        field_key=field_key,
        name=str(field_meta.get("name", field_key)),
        schema=schema,
        required=required,
        required_level=required_level,
        operations=[str(op) for op in operations],
        interaction_type=interaction_type,
        value_format=value_format,
        lookup_tool=lookup_tool,
        needs_user_input=needs_user_input,
        current_value=current_value,
    )


def schema_hash_for_transition(transition: dict[str, Any]) -> str:
    """Build a stable hash for schema-relevant transition metadata."""
    fields = transition.get("fields")
    if not isinstance(fields, dict):
        fields = {}

    stable_fields: dict[str, Any] = {}
    for field_key in sorted(fields):
        field_meta = fields[field_key]
        if not isinstance(field_meta, dict):
            continue
        schema = field_meta.get("schema")
        operations = field_meta.get("operations")
        stable_fields[field_key] = {
            "required": bool(field_meta.get("required")),
            "schema": schema if isinstance(schema, dict) else {},
            "operations": operations if isinstance(operations, list) else [],
        }

    payload = {
        "id": str(transition.get("id", "")),
        "name": str(transition.get("name", "")),
        "fields": stable_fields,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def format_transition_field_value(field_plan: TransitionFieldPlan, value: Any) -> Any:
    """Format a value for Jira transition `fields` payload submission."""
    if is_empty_transition_value(value):
        return [] if field_plan.value_format == "array_of_id_objects" else None

    if field_plan.value_format == "array_of_id_objects":
        return _to_id_object_array(value)

    if field_plan.value_format == "user_object":
        return _to_user_object(value)

    if field_plan.value_format == "id_object":
        return _to_id_object(value)

    if field_plan.value_format == "string":
        return str(value)

    if field_plan.value_format == "number":
        return _to_number(value)

    return value


def is_empty_transition_value(value: Any) -> bool:
    """Return whether a transition field value should be treated as empty."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict) and "id" in value:
        return not str(value.get("id", "")).strip()
    return False


def _to_id_object_array(value: Any) -> list[dict[str, str]]:
    """Convert scalars or arrays into Jira id-object arrays."""
    values = value if isinstance(value, list) else [value]
    result: list[dict[str, str]] = []
    for item in values:
        if is_empty_transition_value(item):
            continue
        result.append(_to_id_object(item))
    return result


def _to_id_object(value: Any) -> dict[str, str]:
    """Convert a scalar or object into a Jira id object."""
    if isinstance(value, dict):
        raw_id = value.get("id")
        if raw_id is None:
            raw_id = value.get("name")
        return {"id": str(raw_id)} if raw_id is not None else {"id": ""}
    return {"id": str(value)}


def _to_user_object(value: Any) -> dict[str, str]:
    """Convert a scalar or object into a Jira user object."""
    if isinstance(value, dict):
        for key in ("accountId", "name", "key"):
            raw_value = value.get(key)
            if raw_value is not None:
                return {key: str(raw_value)}
        raw_id = value.get("id")
        if raw_id is not None:
            return {"name": str(raw_id)}
        return {}
    return {"name": str(value)}


def _to_number(value: Any) -> int | float | Any:
    """Convert numeric-looking input to int or float when possible."""
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        try:
            if "." in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return value
    return value
