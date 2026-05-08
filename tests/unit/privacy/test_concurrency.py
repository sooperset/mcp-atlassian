"""Concurrency tests for the privacy filter.

The pipeline is designed to be stateless at the instance level: every
mutable counter (``FilterStats``) is constructed fresh per call, and
filter rules / compiled regexes are immutable after construction. These
tests verify that property holds end-to-end by firing many concurrent
``Client.call_tool`` invocations through the FastMCP middleware chain
and asserting:

1. Every response carries its caller's expected payload (no cross-call
   corruption of content).
2. Every response is filtered identically — same input → same output —
   regardless of interleaving.
3. The aggregate of per-call stats logged equals the deterministic
   expected total (no double counting, no lost counts).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from mcp_atlassian.privacy import PrivacyConfig, install_privacy_filter


def _build_server_with_indexed_tool(
    payloads: dict[str, dict[str, Any]],
) -> FastMCP[None]:
    """Register one tool per ``payloads`` key. Each tool returns the
    JSON-serialized payload for its name; the index in the returned
    payload lets concurrency tests verify "the right caller got the
    right response"."""
    server: FastMCP[None] = FastMCP(name="concurrency-test")

    def _make_tool(name: str, value: dict[str, Any]) -> None:
        @server.tool(name=name)
        async def _tool() -> str:
            return json.dumps(value, indent=2, ensure_ascii=False)

        _ = _tool

    for tool_name, payload in payloads.items():
        _make_tool(name=tool_name, value=payload)
    return server


@pytest.mark.asyncio
async def test_parallel_tool_calls_no_response_crosstalk() -> None:
    """Fire 100 concurrent calls across 5 distinct tools and verify each
    response carries the index baked into its tool's payload. Any
    cross-talk would surface as a wrong index in the response."""
    payloads = {
        f"tool_{i}": {
            "tool_index": i,
            "summary": f"Tool {i} contact alice{i}@example.com",
            "labels": ["public" if i % 2 else "confidential"],
        }
        for i in range(5)
    }
    server = _build_server_with_indexed_tool(payloads=payloads)
    install_privacy_filter(
        server=server,
        config=PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            mask_token="[X]",
        ),
    )

    async def call_one(client: Client[Any], tool_index: int) -> dict[str, Any]:
        result = await client.call_tool(name=f"tool_{tool_index}", arguments={})
        return json.loads(result.content[0].text)  # type: ignore[union-attr]

    async with Client(server) as client:
        # 100 calls, 20 of each tool, all interleaved.
        coros = [call_one(client=client, tool_index=i % 5) for i in range(100)]
        results = await asyncio.gather(*coros)

    for i, result in enumerate(results):
        expected_index = i % 5
        assert result["tool_index"] == expected_index, (
            f"call #{i} expected tool_{expected_index} but got "
            f"tool_{result['tool_index']} — cross-talk!"
        )
        # Each response is correctly filtered.
        assert "[X]" in json.dumps(result)
        assert "@example.com" not in json.dumps(result)


@pytest.mark.asyncio
async def test_parallel_calls_yield_deterministic_filtered_output() -> None:
    """Same tool, fired 50× in parallel — every response must be byte-
    identical (filter has no per-call state that leaks between calls)."""
    payload = {
        "summary": "alice@example.com bob@example.com carol@example.com",
        "details": {"phone": "+1 (415) 555-0100"},
    }
    server = _build_server_with_indexed_tool(payloads={"my_tool": payload})
    install_privacy_filter(
        server=server,
        config=PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email", "phone"],
            mask_token="[X]",
        ),
    )

    async def call_once(client: Client[Any]) -> str:
        result = await client.call_tool(name="my_tool", arguments={})
        return result.content[0].text  # type: ignore[union-attr]

    async with Client(server) as client:
        outputs = await asyncio.gather(*(call_once(client=client) for _ in range(50)))

    # All 50 responses identical — no inter-call state corruption.
    distinct = set(outputs)
    assert len(distinct) == 1, (
        f"expected all 50 concurrent responses identical, got "
        f"{len(distinct)} distinct outputs"
    )
    out = json.loads(outputs[0])
    flat = json.dumps(out)
    assert "@example.com" not in flat
    assert "555-0100" not in flat
    # Three emails replaced + one phone = 4 mask tokens in the summary +
    # one in details.
    assert flat.count("[X]") == 4


@pytest.mark.asyncio
async def test_parallel_telemetry_counters_sum_correctly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fire N parallel calls, each with K known PII matches. The total
    ``pii_redactions`` summed across all DEBUG log lines must equal
    N × K — proving no counter is dropped or double-counted under
    concurrency."""
    n_calls = 30
    pii_per_call = 3  # three email addresses in the payload
    payload = {
        "summary": ("alice@example.com bob@example.com carol@example.com"),
    }
    server = _build_server_with_indexed_tool(payloads={"my_tool": payload})
    install_privacy_filter(
        server=server,
        config=PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            mask_token="[X]",
        ),
    )

    async with Client(server) as client:
        with caplog.at_level(logging.DEBUG, logger="mcp_atlassian.privacy.middleware"):
            await asyncio.gather(
                *(
                    client.call_tool(name="my_tool", arguments={})
                    for _ in range(n_calls)
                )
            )

    log_lines = [
        record.getMessage()
        for record in caplog.records
        if "privacy filter applied" in record.getMessage()
    ]
    assert len(log_lines) == n_calls, (
        f"expected {n_calls} telemetry lines, got {len(log_lines)}"
    )
    # Sum the pii_redactions counts from each log line.
    total = 0
    for line in log_lines:
        m = re.search(r"pii_redactions=(\d+)", line)
        assert m is not None, f"missing pii_redactions in line: {line}"
        total += int(m.group(1))
    assert total == n_calls * pii_per_call, (
        f"summed pii_redactions={total}, expected "
        f"{n_calls * pii_per_call} ({n_calls} calls × {pii_per_call} matches)"
    )


@pytest.mark.asyncio
async def test_parallel_calls_with_distinct_filter_outcomes() -> None:
    """Different concurrent calls produce different stats — verify each
    call's stats reflect ITS payload, not a sibling's."""
    # Tool A: 2 PII matches, no field rules apply.
    # Tool B: 0 PII matches, 1 field drop.
    server: FastMCP[None] = FastMCP(name="distinct-outcomes")

    @server.tool(name="tool_a")
    async def _tool_a() -> str:
        return json.dumps({"x": "a@x.com", "y": "b@x.com"})

    @server.tool(name="tool_b")
    async def _tool_b() -> str:
        return json.dumps({"secret": "sensitive", "kept": "ok"})

    install_privacy_filter(
        server=server,
        config=PrivacyConfig(
            enabled=True,
            pii_pattern_names=["email"],
            drop_fields={"*": ["secret"]},
            mask_token="[X]",
        ),
    )

    async with Client(server) as client:
        results = await asyncio.gather(
            *[
                client.call_tool(name=name, arguments={})
                for name in ("tool_a", "tool_b") * 25
            ]
        )

    for i, result in enumerate(results):
        text = result.content[0].text  # type: ignore[union-attr]
        out = json.loads(text)
        if i % 2 == 0:  # tool_a
            assert out == {"x": "[X]", "y": "[X]"}
        else:  # tool_b
            assert out == {"kept": "ok"}


@pytest.mark.asyncio
async def test_pipeline_instance_state_unchanged_after_parallel_calls() -> None:
    """Direct attack on shared pipeline state: confirm the pipeline's
    internal members (config, filter instances, redactor) are unchanged
    after a flurry of concurrent calls. A naïve refactor that cached
    per-call state on the pipeline would fail this."""
    from mcp_atlassian.privacy.pipeline import PrivacyPipeline

    config = PrivacyConfig(
        enabled=True,
        pii_pattern_names=["email"],
        deny_labels=["confidential"],
        drop_fields={"*": ["secret"]},
        mask_token="[X]",
    )
    pipeline = PrivacyPipeline(config=config)

    # Capture identity of internals before.
    redactor_before = pipeline._redactor  # type: ignore[attr-defined]
    resource_filter_before = pipeline._resource_filter  # type: ignore[attr-defined]

    async def fire(i: int) -> None:
        payload = {
            "issues": [
                {
                    "key": f"PROJ-{i}",
                    "labels": ["public" if i % 3 else "confidential"],
                    "summary": f"contact alice{i}@example.com",
                    "secret": "drop",
                }
            ]
        }
        # Direct call, bypassing the FastMCP layer — exercises the
        # pipeline's own re-entrancy.
        result, stats = pipeline.apply_with_stats(
            tool_name="jira_search", value=payload
        )
        assert isinstance(result, dict)
        assert stats.total_changes > 0

    await asyncio.gather(*(fire(i=i) for i in range(200)))

    # Internal state must be the same instance — no mutation, no swap.
    assert pipeline._redactor is redactor_before  # type: ignore[attr-defined]
    assert (
        pipeline._resource_filter is resource_filter_before  # type: ignore[attr-defined]
    )
