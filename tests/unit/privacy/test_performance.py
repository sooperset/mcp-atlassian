"""Performance tests for the privacy pipeline on big payloads.

Why *relative* thresholds?
--------------------------
Absolute millisecond thresholds drift with the runner: a developer laptop
(Apple M-series) is roughly 5–15× faster than a shared GitHub Actions
runner, which would make any single ms threshold either flaky on CI or
useless on the laptop.

Each test instead times the filter *and* a deepcopy of the same payload
in the same run, then asserts ``filter_ms / deepcopy_ms < multiplier``.
``copy.deepcopy`` walks the same nested structure once with predictable
per-element cost, so it functions as a machine-independent baseline:
when the runner is slow, both numbers grow together and the ratio stays
stable. Real regressions (an O(n²) walk slipping in, an extra pass over
every string, etc.) drive the ratio far past the documented bound and
fail loudly on every machine.

Reference ratios on a developer laptop (Apple M-series, Python 3.10):

    config         n=100   n=1000
    noop           ~0.0    ~0.0
    regex_only     ~3.2    ~3.5
    field_only     ~4.2    ~4.1
    full_pipeline  ~10.5   ~10.8

The bounds below give ~1.5–2× headroom over those baselines for runner
variance, while still catching a meaningful regression.

Marked ``pytest.mark.performance``; run explicitly with::

    uv run pytest -m performance tests/unit/privacy/test_performance.py
"""

from __future__ import annotations

import copy
import json
import time
from typing import Any

import pytest

from mcp_atlassian.privacy.config import PrivacyConfig
from mcp_atlassian.privacy.pipeline import PrivacyPipeline

pytestmark = pytest.mark.performance


# Each entry: filter time ≤ multiplier × deepcopy(payload) time.
# We take the minimum of MEASURE_BATCHES batches (each averaged over
# REPEAT_RUNS) to dampen GC/scheduler noise — variance always increases
# the measured time, never decreases it, so the min reflects the
# uncontaminated lower bound.
WARMUP_RUNS = 1
REPEAT_RUNS = 5
MEASURE_BATCHES = 3

RELATIVE_THRESHOLDS: dict[tuple[str, int], float] = {
    ("noop", 1000): 0.5,
    ("regex_only", 100): 7.0,
    ("regex_only", 1000): 7.0,
    ("field_only", 100): 8.0,
    ("field_only", 1000): 8.0,
    ("full_pipeline", 100): 18.0,
    ("full_pipeline", 1000): 18.0,
}


def _make_issues(n: int) -> dict[str, Any]:
    """Synthetic ``jira_search`` response with ``n`` simplified-dict
    issues. Each issue carries multiple PII fields plus 3 comments to
    exercise nested walking."""
    return {
        "total": n,
        "start_at": 0,
        "max_results": n,
        "issues": [
            {
                "id": f"100{i}",
                "key": f"PROJ-{i}",
                "summary": (
                    f"Issue {i}: contact alice{i}@example.com about IP 10.0.0.{i % 256}"
                ),
                "description": (
                    f"Description with email bob{i}@example.com, "
                    f"card 4242 4242 4242 4242, "
                    f"IBAN DE89370400440532013000."
                ),
                "labels": ["public" if i % 7 else "confidential"],
                "reporter": {
                    "display_name": f"Reporter {i}",
                    "name": f"reporter_{i}",
                    "email": f"reporter{i}@example.com",
                    "avatar_url": f"https://x/avatar/{i}",
                },
                "assignee": {
                    "display_name": f"Assignee {i}",
                    "name": f"assignee_{i}",
                    "email": f"assignee{i}@example.com",
                    "avatar_url": f"https://x/avatar/{i + 1000}",
                },
                "comments": [
                    {
                        "id": f"c{i}-{j}",
                        "body": f"Comment {j}: see carol{i}@example.com",
                        "author": {
                            "display_name": f"Commenter {j}",
                            "email": f"commenter{i}{j}@example.com",
                        },
                    }
                    for j in range(3)
                ],
            }
            for i in range(n)
        ],
    }


def _config_for(label: str) -> PrivacyConfig:
    if label == "noop":
        return PrivacyConfig(enabled=False)
    if label == "regex_only":
        return PrivacyConfig(
            enabled=True,
            pii_pattern_names=[
                "email",
                "phone",
                "ipv4",
                "iban",
                "credit_card",
            ],
        )
    if label == "field_only":
        return PrivacyConfig(
            enabled=True,
            drop_fields={
                "jira_issue_list": [
                    "issues.*.assignee.email",
                    "issues.*.reporter.email",
                ]
            },
        )
    if label == "full_pipeline":
        return PrivacyConfig(
            enabled=True,
            pii_pattern_names=[
                "email",
                "phone",
                "ipv4",
                "iban",
                "credit_card",
            ],
            deny_labels=["confidential"],
            drop_fields={"*": ["**.email", "**.avatar_url"]},
            mask_fields={"*": ["**.display_name"]},
        )
    raise ValueError(f"unknown config label {label!r}")


def _measure_pipeline_ms(pipeline: PrivacyPipeline, payload: dict[str, Any]) -> float:
    for _ in range(WARMUP_RUNS):
        pipeline.apply_with_stats(tool_name="jira_search", value=payload)
    runs: list[float] = []
    for _ in range(MEASURE_BATCHES):
        start = time.perf_counter()
        for _ in range(REPEAT_RUNS):
            pipeline.apply_with_stats(tool_name="jira_search", value=payload)
        runs.append(((time.perf_counter() - start) / REPEAT_RUNS) * 1000.0)
    return min(runs)


def _measure_deepcopy_ms(payload: dict[str, Any]) -> float:
    """Time a deepcopy of the payload as a machine-speed baseline.

    Deepcopy walks the same nested structure once with predictable
    per-element cost, so the ratio of pipeline-time to deepcopy-time
    is stable across runners with very different absolute speed.
    """
    for _ in range(WARMUP_RUNS):
        copy.deepcopy(x=payload)
    runs: list[float] = []
    for _ in range(MEASURE_BATCHES):
        start = time.perf_counter()
        for _ in range(REPEAT_RUNS):
            copy.deepcopy(x=payload)
        runs.append(((time.perf_counter() - start) / REPEAT_RUNS) * 1000.0)
    return min(runs)


@pytest.mark.parametrize(
    ("config_label", "n"),
    sorted(RELATIVE_THRESHOLDS.keys()),
)
def test_pipeline_under_threshold(
    config_label: str, n: int, capsys: pytest.CaptureFixture[str]
) -> None:
    """Filter time ≤ multiplier × deepcopy(payload) time on the same
    machine. Auto-scales to runner speed; fails loudly when the filter
    becomes pathologically slower than just walking the structure once.
    Numbers are printed even on success so trends are visible in CI logs.
    """
    multiplier = RELATIVE_THRESHOLDS[(config_label, n)]
    pipeline = PrivacyPipeline(config=_config_for(label=config_label))
    payload = _make_issues(n=n)
    payload_kb = len(json.dumps(payload)) / 1024
    deepcopy_ms = _measure_deepcopy_ms(payload=payload)
    elapsed_ms = _measure_pipeline_ms(pipeline=pipeline, payload=payload)
    ratio = elapsed_ms / deepcopy_ms if deepcopy_ms > 0 else float("inf")
    with capsys.disabled():
        print(
            f"\n[perf] {config_label:14s} n={n:5d}  "
            f"payload={payload_kb:6.0f}KB  "
            f"filter={elapsed_ms:7.1f}ms  "
            f"deepcopy={deepcopy_ms:6.1f}ms  "
            f"ratio={ratio:5.2f} (max={multiplier:.1f})"
        )
    assert ratio < multiplier, (
        f"{config_label} on n={n}: filter={elapsed_ms:.1f}ms vs "
        f"deepcopy baseline {deepcopy_ms:.1f}ms — ratio={ratio:.2f}, "
        f"exceeding the {multiplier:.1f}× bound. Either a perf "
        f"regression slipped in (filter is now much slower than walking "
        f"the same structure once), or the multiplier needs updating "
        f"after a deliberate change."
    )


def test_filter_correctness_holds_at_scale() -> None:
    """A perf test is only useful if the filter is still correct at the
    big-payload sizes. Cross-check: a 1000-issue full-pipeline run drops
    every confidential issue and redacts every documented PII pattern."""
    pipeline = PrivacyPipeline(config=_config_for(label="full_pipeline"))
    payload = _make_issues(n=1000)
    result, stats = pipeline.apply_with_stats(tool_name="jira_search", value=payload)
    assert isinstance(result, dict)
    issues_kept = result["issues"]
    # 1 in 7 issues is confidential → ~143 dropped, ~857 kept.
    assert 100 < len(issues_kept) < 1000
    assert all("confidential" not in i.get("labels", []) for i in issues_kept)
    flat = json.dumps(result)
    assert "@example.com" not in flat
    assert "10.0.0." not in flat
    assert "4242 4242 4242 4242" not in flat
    assert "DE89370400440532013000" not in flat
    # Telemetry must reflect what happened.
    assert stats.resources_dropped > 0
    assert stats.fields_dropped > 0
    assert stats.fields_masked > 0
    assert stats.pii_redactions > 0
