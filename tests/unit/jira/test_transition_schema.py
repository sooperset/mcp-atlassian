"""Tests for Jira transition schema parsing."""

from mcp_atlassian.jira.transition_schema import (
    format_transition_field_value,
    is_empty_transition_value,
    parse_transition_field,
    schema_hash_for_transition,
)


def test_parse_user_field() -> None:
    """User fields should use user-specific collection metadata."""
    field = parse_transition_field(
        "assignee",
        {
            "name": "经办人",
            "schema": {"type": "user"},
            "operations": ["set"],
        },
    )

    assert field.interaction_type == "user_auto_or_picker"
    assert field.value_format == "user_object"


def test_parse_version_array_field_truncates_allowed_values() -> None:
    """Version fields use lookup metadata instead of embedding huge options."""
    allowed_values = [{"id": str(i), "name": f"V{i}"} for i in range(100)]

    field = parse_transition_field(
        "customfield_11405",
        {
            "required": False,
            "name": "引入版本",
            "schema": {"type": "array", "items": "version"},
            "operations": ["set", "add", "remove"],
            "allowedValues": allowed_values,
        },
    )

    assert field.interaction_type == "version_picker"
    assert field.value_format == "array_of_id_objects"
    assert field.lookup_tool == "jira_search_transition_field_options"
    assert field.needs_user_input is True
    assert field.field_schema == {"type": "array", "items": "version"}


def test_parse_multi_option_field() -> None:
    """Array fields with allowed values should become multi-option pickers."""
    field = parse_transition_field(
        "customfield_10718",
        {
            "name": "缺陷产生原因",
            "schema": {"type": "array", "items": "option"},
            "operations": ["set", "add", "remove"],
            "allowedValues": [{"id": "1", "value": "代码缺陷"}],
        },
    )

    assert field.interaction_type == "multi_option_picker"
    assert field.value_format == "array_of_id_objects"


def test_parse_single_option_field() -> None:
    """Option fields should become single-option pickers."""
    field = parse_transition_field(
        "customfield_11407",
        {
            "name": "历史数据处理",
            "schema": {"type": "option"},
            "operations": ["set"],
            "allowedValues": [{"id": "1", "value": "不涉及"}],
        },
    )

    assert field.interaction_type == "single_option_picker"
    assert field.value_format == "id_object"


def test_parse_textarea_and_number_fields() -> None:
    """Textarea-like strings and numbers should get specific interactions."""
    textarea = parse_transition_field(
        "customfield_10705",
        {
            "name": "根因描述",
            "schema": {
                "type": "string",
                "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
            },
        },
    )
    number = parse_transition_field(
        "customfield_10010",
        {"name": "Score", "schema": {"type": "number"}},
    )

    assert textarea.interaction_type == "textarea"
    assert textarea.value_format == "string"
    assert number.interaction_type == "number_input"
    assert number.value_format == "number"


def test_parse_unknown_field_falls_back_to_text() -> None:
    """Unknown schemas should be represented as text input fallback."""
    field = parse_transition_field(
        "customfield_unknown",
        {"name": "Unknown", "schema": {"type": "mystery"}},
    )

    assert field.interaction_type == "text_input"
    assert field.value_format == "raw"


def test_effective_required_sets_soft_required_level() -> None:
    """Profile-driven screen validation marks fields as soft required."""
    field = parse_transition_field(
        "customfield_10706",
        {"name": "解决方案", "schema": {"type": "string"}, "required": False},
        effective_required=True,
    )

    assert field.required is False
    assert field.required_level == "soft"


def test_schema_hash_is_stable_for_irrelevant_allowed_value_order() -> None:
    """Schema hash ignores large option payload details."""
    transition_a = {
        "id": "771",
        "name": "完成分析",
        "fields": {
            "customfield_11405": {
                "required": False,
                "schema": {"type": "array", "items": "version"},
                "operations": ["set", "add", "remove"],
                "allowedValues": [{"id": "1"}, {"id": "2"}],
            }
        },
    }
    transition_b = {
        "id": "771",
        "name": "完成分析",
        "fields": {
            "customfield_11405": {
                "required": False,
                "schema": {"type": "array", "items": "version"},
                "operations": ["set", "add", "remove"],
                "allowedValues": [{"id": "2"}, {"id": "1"}],
            }
        },
    }

    assert schema_hash_for_transition(transition_a) == schema_hash_for_transition(
        transition_b
    )


def test_format_version_value_from_scalar_and_objects() -> None:
    """Version values should become Jira id-object arrays."""
    field = parse_transition_field(
        "customfield_11405",
        {"name": "引入版本", "schema": {"type": "array", "items": "version"}},
    )

    assert format_transition_field_value(field, "123") == [{"id": "123"}]
    assert format_transition_field_value(field, [{"id": 456}, "789"]) == [
        {"id": "456"},
        {"id": "789"},
    ]


def test_format_multi_option_and_single_option_values() -> None:
    """Option values should be converted to Jira id objects."""
    multi = parse_transition_field(
        "customfield_10718",
        {
            "name": "缺陷产生原因",
            "schema": {"type": "array", "items": "option"},
            "allowedValues": [{"id": "1", "value": "代码缺陷"}],
        },
    )
    single = parse_transition_field(
        "customfield_11407",
        {"name": "历史数据处理", "schema": {"type": "option"}},
    )

    assert format_transition_field_value(multi, ["1", {"id": 2}]) == [
        {"id": "1"},
        {"id": "2"},
    ]
    assert format_transition_field_value(single, "3") == {"id": "3"}
    assert format_transition_field_value(single, {"id": 4}) == {"id": "4"}


def test_format_user_values() -> None:
    """User values should not be formatted as Jira option id objects."""
    user = parse_transition_field(
        "assignee",
        {"name": "经办人", "schema": {"type": "user"}},
    )

    assert format_transition_field_value(user, "jianghaitao") == {
        "name": "jianghaitao"
    }
    assert format_transition_field_value(user, {"accountId": "abc"}) == {
        "accountId": "abc"
    }
    assert format_transition_field_value(user, {"key": "jh"}) == {"key": "jh"}


def test_format_text_and_number_values() -> None:
    """String and number values should keep API-compatible scalar types."""
    text = parse_transition_field(
        "customfield_10705",
        {"name": "根因描述", "schema": {"type": "string"}},
    )
    number = parse_transition_field(
        "customfield_10010",
        {"name": "Score", "schema": {"type": "number"}},
    )

    assert format_transition_field_value(text, 123) == "123"
    assert format_transition_field_value(number, "12") == 12
    assert format_transition_field_value(number, "12.5") == 12.5


def test_is_empty_transition_value() -> None:
    """Empty detection should match transition form validation semantics."""
    assert is_empty_transition_value(None) is True
    assert is_empty_transition_value("") is True
    assert is_empty_transition_value("  ") is True
    assert is_empty_transition_value([]) is True
    assert is_empty_transition_value({"id": ""}) is True
    assert is_empty_transition_value({"id": "1"}) is False
    assert is_empty_transition_value([{"id": "1"}]) is False
