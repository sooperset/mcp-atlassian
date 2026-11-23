"""Wall-clock budgets that stay meaningful under a coverage tracer."""

from __future__ import annotations

import sys

#: How much wider a budget gets when a tracer runs. Tests that scale a budget
#: by this factor also scale whatever the budget must stay below (a slow
#: server, a blocked lookup), so a wider budget still catches a missed
#: deadline.
TRACED_FACTOR = 4.0


def is_traced() -> bool:
    """Return whether coverage or another tracer is slowing this run."""
    try:
        import coverage

        if coverage.Coverage.current() is not None:
            return True
    except ImportError:
        pass
    return sys.gettrace() is not None


def budget(seconds: float, traced_factor: float = TRACED_FACTOR) -> float:
    """Return ``seconds``, widened by ``traced_factor`` when traced."""
    return seconds * traced_factor if is_traced() else seconds
