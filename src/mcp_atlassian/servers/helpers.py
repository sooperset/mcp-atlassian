"""Shared helpers for outcome-oriented server tools."""

import logging
from collections.abc import Iterable, Mapping
from typing import Any

logger = logging.getLogger(__name__)


def parse_include(include: str | None, valid_sections: set[str]) -> set[str]:
    """Parse a comma-separated include value into valid section names.

    Args:
        include: Comma-separated section names, or ``"all"``.
        valid_sections: The section names accepted by the caller.

    Returns:
        The requested valid sections. Unknown and empty sections are ignored.
    """
    if include is None:
        return set()

    normalized_sections = {section.casefold(): section for section in valid_sections}
    sections: set[str] = set()
    for raw_section in include.split(","):
        section = raw_section.strip()
        if not section:
            continue

        normalized_section = section.casefold()
        if normalized_section == "all":
            sections.update(valid_sections)
        elif normalized_section in normalized_sections:
            sections.add(normalized_sections[normalized_section])
        else:
            logger.warning("Ignoring unknown include section: %s", section)

    return sections


def resolve_transition(
    transitions: Iterable[Mapping[str, Any]], name_or_id: str
) -> str:
    """Resolve a transition name or ID to its transition ID.

    Args:
        transitions: Available transitions containing ``id`` and ``name`` keys.
        name_or_id: Transition ID or name to resolve.

    Returns:
        The matching transition ID as a string.

    Raises:
        ValueError: If no transition matches, including the available options.
    """
    transition_list = list(transitions)

    for transition in transition_list:
        transition_id = transition.get("id")
        if transition_id is not None and str(transition_id) == name_or_id:
            return str(transition_id)

    requested_name = name_or_id.casefold()
    for transition in transition_list:
        transition_name = transition.get("name")
        transition_id = transition.get("id")
        if (
            transition_id is not None
            and isinstance(transition_name, str)
            and transition_name.casefold() == requested_name
        ):
            return str(transition_id)

    available_options = [
        f"{transition.get('name', '')} ({transition.get('id', '')})"
        for transition in transition_list
    ]
    options = ", ".join(available_options) or "none"
    error_message = f"Transition '{name_or_id}' not found. Available options: {options}"
    raise ValueError(error_message)
