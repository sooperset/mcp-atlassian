"""Fuzzy matching and suggestion utilities for error recovery."""

from __future__ import annotations

import logging
from difflib import get_close_matches
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_atlassian.confluence import ConfluenceFetcher

logger = logging.getLogger(__name__)


def fuzzy_match(
    user_input: str,
    candidates: list[str],
    max_results: int = 3,
    cutoff: float = 0.5,
) -> list[str]:
    """Find candidates that fuzzy-match the user input.

    Uses case-insensitive difflib matching plus substring matching.

    Args:
        user_input: The string the user provided.
        candidates: Available valid strings to match against.
        max_results: Maximum number of suggestions to return.
        cutoff: Minimum similarity ratio (0.0-1.0) for difflib. Default 0.5.

    Returns:
        List of matching candidates (original case), best matches first.
    """
    if not user_input or not candidates:
        return []

    input_lower = user_input.lower()

    # 1. Exact case-insensitive match (highest priority)
    exact = [c for c in candidates if c.lower() == input_lower]
    if exact:
        return exact[:max_results]

    # 2. difflib fuzzy matching (case-insensitive comparison)
    lower_to_original: dict[str, str] = {}
    for c in candidates:
        lower_to_original.setdefault(c.lower(), c)

    difflib_matches = get_close_matches(
        input_lower,
        list(lower_to_original.keys()),
        n=max_results,
        cutoff=cutoff,
    )
    results = [lower_to_original[m] for m in difflib_matches]

    # 3. Substring matching (append any not already found)
    if len(results) < max_results:
        for c in candidates:
            if input_lower in c.lower() and c not in results:
                results.append(c)
                if len(results) >= max_results:
                    break

    return results[:max_results]


def format_suggestions(
    error_msg: str,
    suggestions: list[str],
    hint: str | None = None,
) -> dict[str, object]:
    """Build a structured error response with suggestions.

    Args:
        error_msg: The primary error message.
        suggestions: List of suggested corrections.
        hint: Optional hint for the user.

    Returns:
        Dict with 'error', 'suggestions', and optionally 'hint'.
    """
    result: dict[str, object] = {
        "error": error_msg,
        "suggestions": suggestions,
    }
    if hint:
        result["hint"] = hint
    return result


def suggest_spaces(
    space_key_input: str,
    fetcher: ConfluenceFetcher,
) -> list[str]:
    """Suggest similar space keys when the given key is invalid.

    Fetches available spaces from Confluence and fuzzy-matches against them.
    Designed to be lightweight -- single API call, no caching.

    Args:
        space_key_input: The invalid space key the user provided.
        fetcher: A ConfluenceFetcher instance.

    Returns:
        List of similar space keys, best matches first.
    """
    try:
        spaces_response = fetcher.get_spaces(limit=100)
        results = spaces_response.get("results", [])
        space_keys = [s["key"] for s in results if "key" in s]
    except Exception:
        logger.debug("Failed to fetch spaces for suggestions", exc_info=True)
        return []

    return fuzzy_match(space_key_input, space_keys)
