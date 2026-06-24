"""In-memory storage for prepared Jira transition plans."""

import copy
import threading
import time
from dataclasses import dataclass

from ..models.jira.transition_plan import TransitionPlan, TransitionPlanStatus


@dataclass(frozen=True)
class _StoredTransitionPlan:
    plan: TransitionPlan
    user_key: str | None
    tenant_key: str | None
    expires_at: float


class TransitionPlanStore:
    """Local process store for prepared transition plans.

    The store is intentionally scoped to one MCP server process. It does not
    survive restarts and is not shared across workers.
    """

    def __init__(self, ttl_seconds: int = 1800, max_entries: int = 1000) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._plans: dict[str, _StoredTransitionPlan] = {}
        self._lock = threading.RLock()

    def put(
        self,
        plan: TransitionPlan,
        user_key: str | None = None,
        tenant_key: str | None = None,
    ) -> None:
        """Store or replace a transition plan."""
        with self._lock:
            self._prune_locked()
            self._plans[plan.plan_id] = _StoredTransitionPlan(
                plan=copy.deepcopy(plan),
                user_key=user_key,
                tenant_key=tenant_key,
                expires_at=self._now() + self._ttl_seconds,
            )
            self._enforce_max_entries_locked()

    def get(
        self,
        plan_id: str,
        user_key: str | None = None,
        tenant_key: str | None = None,
    ) -> TransitionPlan | None:
        """Return a transition plan when present, fresh, and in scope."""
        with self._lock:
            stored = self._plans.get(plan_id)
            if stored is None:
                return None
            if self._is_expired(stored):
                self._plans.pop(plan_id, None)
                return None
            if not self._scope_matches(stored, user_key, tenant_key):
                return None
            return copy.deepcopy(stored.plan)

    def delete(
        self,
        plan_id: str,
        user_key: str | None = None,
        tenant_key: str | None = None,
    ) -> None:
        """Delete a transition plan when it exists and matches the scope."""
        with self._lock:
            stored = self._plans.get(plan_id)
            if stored is None:
                return
            if self._is_expired(stored) or self._scope_matches(
                stored, user_key, tenant_key
            ):
                self._plans.pop(plan_id, None)

    def claim_for_apply(
        self,
        plan_id: str,
        payload_hash: str,
        user_key: str | None = None,
        tenant_key: str | None = None,
    ) -> tuple[TransitionPlan | None, str]:
        """Atomically consume a previewed plan before a local apply call.

        This is a local process guard. It prevents two concurrent MCP calls in
        this server process from applying the same prepared plan.
        """
        with self._lock:
            stored = self._plans.get(plan_id)
            if stored is None:
                return None, "not_found"
            if self._is_expired(stored):
                self._plans.pop(plan_id, None)
                return None, "not_found"
            if not self._scope_matches(stored, user_key, tenant_key):
                return None, "not_found"

            plan = stored.plan
            if (
                plan.status != TransitionPlanStatus.PREVIEWED
                or not plan.last_payload_hash
            ):
                return None, "preview_required"
            if plan.last_payload_hash != payload_hash:
                return None, "payload_hash_mismatch"

            self._plans.pop(plan_id, None)
            return copy.deepcopy(plan), "claimed"

    def _prune_locked(self) -> None:
        expired = [
            plan_id
            for plan_id, stored in self._plans.items()
            if self._is_expired(stored)
        ]
        for plan_id in expired:
            self._plans.pop(plan_id, None)

    def _enforce_max_entries_locked(self) -> None:
        while len(self._plans) > self._max_entries:
            oldest_id = min(
                self._plans,
                key=lambda plan_id: self._plans[plan_id].expires_at,
            )
            self._plans.pop(oldest_id, None)

    def _is_expired(self, stored: _StoredTransitionPlan) -> bool:
        return stored.expires_at <= self._now()

    @staticmethod
    def _scope_matches(
        stored: _StoredTransitionPlan,
        user_key: str | None,
        tenant_key: str | None,
    ) -> bool:
        if stored.user_key is not None and stored.user_key != user_key:
            return False
        if stored.tenant_key is not None and stored.tenant_key != tenant_key:
            return False
        return True

    @staticmethod
    def _now() -> float:
        return time.monotonic()
