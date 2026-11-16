"""Structural check: async tool handlers never call a fetcher on the event loop.

Fetcher methods are blocking ``requests`` calls. Inside an ``async def`` they
must go through ``run_fetcher_call``, which runs them in a worker thread.
This test reads the handler modules and fails on any other use of a name bound
from ``await get_jira_fetcher(ctx)`` / ``await get_confluence_fetcher(ctx)``.

Allowed uses of the fetcher name ``f``:

* ``run_fetcher_call(f.method, ...)`` and ``run_fetcher_call(helper, f, ...)``
  (also as a keyword argument, for example ``fetch_fn=f.method``);
* reads through ``f.config`` (plain configuration data).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SERVERS_DIR = Path(__file__).resolve().parents[3] / "src" / "mcp_atlassian" / "servers"
HANDLER_MODULES = ("jira.py", "confluence.py")
FETCHER_FACTORIES = frozenset({"get_jira_fetcher", "get_confluence_fetcher"})
OFFLOAD_HELPER = "run_fetcher_call"
DATA_ATTRS = frozenset({"config"})


def _factory_name(node: ast.AST) -> str | None:
    """Name of the called factory in ``get_x(ctx)`` or ``module.get_x(ctx)``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _fetcher_names(fn: ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if (
            isinstance(value, ast.Await)
            and isinstance(value.value, ast.Call)
            and _factory_name(value.value.func) in FETCHER_FACTORIES
        ):
            names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names


def _is_offload_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == OFFLOAD_HELPER
    )


def find_violations(source: str, filename: str) -> list[str]:
    """Return ``file:line handler: expression`` for each on-loop fetcher use."""
    tree = ast.parse(source)
    violations: list[str] = []
    for fn in tree.body:
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        names = _fetcher_names(fn)
        if not names:
            continue
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(fn):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(fn):
            if _is_offload_call(node) and not isinstance(parents[node], ast.Await):
                violations.append(
                    f"{filename}:{node.lineno} {fn.name}: "
                    f"{OFFLOAD_HELPER}(...) is not awaited"
                )
        for node in ast.walk(fn):
            if not (
                isinstance(node, ast.Name)
                and node.id in names
                and isinstance(node.ctx, ast.Load)
            ):
                continue
            expr: ast.AST = node
            parent = parents[expr]
            if isinstance(parent, ast.Attribute) and parent.attr in DATA_ATTRS:
                continue
            if isinstance(parent, ast.Attribute):
                expr, parent = parent, parents[parent]
            if isinstance(parent, ast.keyword):
                expr, parent = parent, parents[parent]
            if _is_offload_call(parent) and expr is not parent.func:  # type: ignore[attr-defined]
                continue
            violations.append(
                f"{filename}:{node.lineno} {fn.name}: {ast.unparse(parent)[:80]}"
            )
    return violations


def _handler_count(source: str) -> int:
    tree = ast.parse(source)
    return sum(
        1
        for fn in tree.body
        if isinstance(fn, ast.AsyncFunctionDef) and _fetcher_names(fn)
    )


@pytest.mark.parametrize("module", HANDLER_MODULES)
def test_handlers_offload_every_fetcher_call(module: str) -> None:
    source = (SERVERS_DIR / module).read_text(encoding="utf-8")
    assert _handler_count(source) > 10, "no tool handlers found; check the parser"
    violations = find_violations(source, module)
    assert not violations, (
        "Fetcher used on the event loop; wrap it in run_fetcher_call:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "body",
    [
        "x = f.get_issue('A-1')",
        "x = f.jira.get('rest/api/2/myself')",
        "v = f._v2_adapter\n    v.get_attachment_by_id('1')",
        "x = helper(fetch_fn=f.fetch_attachment_content)",
        "x = helper(f)",
        "x = [i for i in f.get_all_projects()]",
        "x = await run_fetcher_call(f.get_issue('A-1'))",
        "x = run_fetcher_call(f.get_issue, 'A-1')",
    ],
)
def test_checker_flags_on_loop_use(body: str) -> None:
    source = (
        f"async def handler(ctx):\n    f = await get_jira_fetcher(ctx)\n    {body}\n"
    )
    assert find_violations(source, "sample.py")


@pytest.mark.parametrize(
    "body",
    [
        "x = await run_fetcher_call(f.get_issue, 'A-1', fields=None)",
        "x = await run_fetcher_call(helper, fetch_fn=f.fetch_attachment_content)",
        "x = await run_fetcher_call(helper, f, '1')",
        "x = f.config.url.rstrip('/')",
        "x = f.config.is_cloud",
    ],
)
def test_checker_allows_offloaded_use(body: str) -> None:
    source = (
        "async def handler(ctx):\n"
        "    f = await get_confluence_fetcher(ctx)\n"
        f"    {body}\n"
    )
    assert find_violations(source, "sample.py") == []


@pytest.mark.parametrize(
    "binding",
    [
        "f: JiraFetcher = await get_jira_fetcher(ctx)",
        "f = await dependencies.get_jira_fetcher(ctx)",
        "f: Any = await deps.get_confluence_fetcher(ctx)",
    ],
)
def test_checker_finds_other_fetcher_bindings(binding: str) -> None:
    source = f"async def handler(ctx):\n    {binding}\n    x = f.get_issue('A-1')\n"
    assert find_violations(source, "sample.py")
