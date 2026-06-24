"""Tests for the Jira transition plan in-memory store."""

from concurrent.futures import ThreadPoolExecutor

from mcp_atlassian.jira.transition_plan_store import TransitionPlanStore
from mcp_atlassian.models.jira.transition_plan import (
    TransitionPlan,
    TransitionPlanStatus,
)


def _plan(plan_id: str = "plan-1") -> TransitionPlan:
    return TransitionPlan(
        plan_id=plan_id,
        issue_key="RY-8714",
        transition_id="761",
        transition_name="更新信息",
        to_status="处理中",
        schema_hash="schema-hash",
        issue_updated="2026-06-16T10:00:00.000+0800",
    )


def test_store_and_retrieve_plan() -> None:
    store = TransitionPlanStore()
    plan = _plan()

    store.put(plan, user_key="jianghaitao", tenant_key="jira-a")

    assert store.get("plan-1", user_key="jianghaitao", tenant_key="jira-a") == plan


def test_missing_plan_returns_none() -> None:
    store = TransitionPlanStore()

    assert store.get("missing") is None


def test_expired_plan_is_removed() -> None:
    store = TransitionPlanStore(ttl_seconds=0)
    store.put(_plan())

    assert store.get("plan-1") is None


def test_user_scope_prevents_cross_user_retrieval() -> None:
    store = TransitionPlanStore()
    store.put(_plan(), user_key="jianghaitao")

    assert store.get("plan-1", user_key="other-user") is None
    assert store.get("plan-1", user_key="jianghaitao") is not None


def test_tenant_scope_prevents_cross_tenant_retrieval() -> None:
    store = TransitionPlanStore()
    store.put(_plan(), tenant_key="tenant-a")

    assert store.get("plan-1", tenant_key="tenant-b") is None
    assert store.get("plan-1", tenant_key="tenant-a") is not None


def test_delete_respects_scope() -> None:
    store = TransitionPlanStore()
    store.put(_plan(), user_key="jianghaitao", tenant_key="tenant-a")

    store.delete("plan-1", user_key="other-user", tenant_key="tenant-a")
    assert store.get("plan-1", user_key="jianghaitao", tenant_key="tenant-a")

    store.delete("plan-1", user_key="jianghaitao", tenant_key="tenant-a")
    assert store.get("plan-1", user_key="jianghaitao", tenant_key="tenant-a") is None


def test_concurrent_put_get_delete_is_consistent() -> None:
    store = TransitionPlanStore()

    def put_get_delete(index: int) -> bool:
        plan_id = f"plan-{index}"
        store.put(_plan(plan_id), user_key="user", tenant_key="tenant")
        stored = store.get(plan_id, user_key="user", tenant_key="tenant")
        store.delete(plan_id, user_key="user", tenant_key="tenant")
        removed = store.get(plan_id, user_key="user", tenant_key="tenant")
        return stored is not None and removed is None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(put_get_delete, range(50)))

    assert all(results)


def test_store_prunes_to_max_entries() -> None:
    store = TransitionPlanStore(max_entries=2)

    store.put(_plan("plan-1"))
    store.put(_plan("plan-2"))
    store.put(_plan("plan-3"))

    assert store.get("plan-1") is None
    assert store.get("plan-2") is not None
    assert store.get("plan-3") is not None


def test_claim_for_apply_consumes_previewed_plan() -> None:
    store = TransitionPlanStore()
    plan = _plan()
    plan.status = TransitionPlanStatus.PREVIEWED
    plan.last_payload_hash = "hash-1"
    store.put(plan, user_key="user", tenant_key="tenant")

    claimed, status = store.claim_for_apply(
        "plan-1",
        "hash-1",
        user_key="user",
        tenant_key="tenant",
    )

    assert status == "claimed"
    assert claimed == plan
    assert store.get("plan-1", user_key="user", tenant_key="tenant") is None


def test_claim_for_apply_rejects_unpreviewed_or_mismatched_plan() -> None:
    store = TransitionPlanStore()
    store.put(_plan(), user_key="user")

    claimed, status = store.claim_for_apply("plan-1", "hash-1", user_key="user")
    assert claimed is None
    assert status == "preview_required"

    plan = _plan()
    plan.status = TransitionPlanStatus.PREVIEWED
    plan.last_payload_hash = "hash-1"
    store.put(plan, user_key="user")

    claimed, status = store.claim_for_apply("plan-1", "wrong", user_key="user")
    assert claimed is None
    assert status == "payload_hash_mismatch"
    assert store.get("plan-1", user_key="user") is not None
