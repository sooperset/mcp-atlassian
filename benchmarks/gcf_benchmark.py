"""Benchmark: JSON vs GCF token usage for mcp-atlassian payloads.

Generates realistic Jira and Confluence data matching the actual payload
shapes returned by mcp-atlassian tool functions, then compares JSON vs
GCF (Graph Compact Format) serialization in terms of estimated token count.

Token estimation: len(text) // 4  (standard approximation)

Usage:
    python benchmarks/gcf_benchmark.py
    # or
    uv run python benchmarks/gcf_benchmark.py
"""

import json
import random
import string
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

STATUSES = ["To Do", "In Progress", "In Review", "Done", "Blocked", "Backlog"]
PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"]
ISSUE_TYPES = ["Bug", "Story", "Task", "Epic", "Sub-task"]
LABELS = [
    "frontend",
    "backend",
    "api",
    "database",
    "security",
    "performance",
    "documentation",
    "testing",
    "infrastructure",
    "devops",
    "ux",
    "mobile",
]
COMPONENTS = [
    "auth-service",
    "web-app",
    "mobile-app",
    "api-gateway",
    "data-pipeline",
    "notification-service",
    "search-engine",
    "admin-panel",
]
SPACES = ["DEV", "TEAM", "ENG", "PRODUCT", "OPS", "HR", "DESIGN", "QA"]
NAMES = [
    "Alice Johnson",
    "Bob Smith",
    "Charlie Brown",
    "Diana Prince",
    "Eve Wilson",
    "Frank Castle",
    "Grace Hopper",
    "Henry Ford",
    "Iris West",
    "Jack Ryan",
    "Karen Page",
    "Leo Messi",
]
SUMMARIES = [
    "Fix authentication timeout on login page",
    "Add pagination to search results API",
    "Update user profile validation logic",
    "Refactor database connection pooling",
    "Implement rate limiting for public endpoints",
    "Fix memory leak in WebSocket handler",
    "Add unit tests for payment module",
    "Update dependencies to latest versions",
    "Implement SSO integration with Okta",
    "Fix broken CSS on mobile dashboard",
    "Add audit logging for admin actions",
    "Optimize SQL queries for reports page",
    "Migrate legacy API to REST v2",
    "Fix timezone handling in scheduler",
    "Add dark mode support to settings page",
    "Implement bulk import for users",
    "Fix race condition in queue processor",
    "Add retry logic for external API calls",
    "Update documentation for API v3",
    "Fix file upload size limit error",
]
PAGE_TITLES = [
    "Architecture Decision Records",
    "Sprint Planning Guidelines",
    "API Design Standards",
    "Onboarding Checklist",
    "Production Runbook",
    "Database Migration Guide",
    "Security Incident Response",
    "Release Process Documentation",
    "Code Review Best Practices",
    "Infrastructure Cost Analysis",
    "Quarterly OKRs",
    "Team Retrospective Notes",
    "Feature Flag Management",
    "Monitoring and Alerting Setup",
    "Disaster Recovery Plan",
]


def _rand_date(days_back: int = 365) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(
        days=random.randint(0, days_back),  # noqa: S311
        hours=random.randint(0, 23),  # noqa: S311
        minutes=random.randint(0, 59),  # noqa: S311
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _rand_id() -> str:
    return "".join(random.choices(string.digits, k=5))  # noqa: S311


def generate_jira_issues(n: int) -> list[dict]:
    """Generate n realistic Jira issue dicts matching to_simplified_dict output."""
    issues = []
    for i in range(1, n + 1):
        assignee = random.choice(NAMES)  # noqa: S311
        reporter = random.choice(NAMES)  # noqa: S311
        created = _rand_date()
        updated = _rand_date(30)
        issue = {
            "id": str(10000 + i),
            "key": f"PROJ-{i}",
            "summary": random.choice(SUMMARIES),  # noqa: S311
            "url": f"https://company.atlassian.net/browse/PROJ-{i}",
            "description": f"Detailed description for issue PROJ-{i}. "
            f"This involves changes to the {random.choice(COMPONENTS)} component. "  # noqa: S311
            f"Expected completion by end of sprint.",
            "status": {
                "name": random.choice(STATUSES),  # noqa: S311
                "category": random.choice(["To Do", "In Progress", "Done"]),  # noqa: S311
            },
            "issue_type": {
                "name": random.choice(ISSUE_TYPES),  # noqa: S311
            },
            "priority": {
                "name": random.choice(PRIORITIES),  # noqa: S311
            },
            "project": {
                "key": "PROJ",
                "name": "Main Project",
            },
            "assignee": {
                "display_name": assignee,
                "email": assignee.lower().replace(" ", ".") + "@company.com",
            },
            "reporter": {
                "display_name": reporter,
                "email": reporter.lower().replace(" ", ".") + "@company.com",
            },
            "labels": random.sample(LABELS, k=random.randint(0, 3)),  # noqa: S311
            "components": random.sample(COMPONENTS, k=random.randint(0, 2)),  # noqa: S311
            "created": created,
            "updated": updated,
        }
        issues.append(issue)
    return issues


def generate_jira_search_result(n: int) -> dict:
    """Generate a JiraSearchResult wrapper dict."""
    return {
        "total": n * 3,  # simulate more results than returned
        "start_at": 0,
        "max_results": n,
        "issues": generate_jira_issues(n),
    }


def generate_confluence_pages(n: int) -> list[dict]:
    """Generate n realistic Confluence page dicts matching to_simplified_dict output."""
    pages = []
    for i in range(1, n + 1):
        space = random.choice(SPACES)  # noqa: S311
        author = random.choice(NAMES)  # noqa: S311
        page = {
            "id": str(100000 + i),
            "title": random.choice(PAGE_TITLES),  # noqa: S311
            "url": f"https://company.atlassian.net/wiki/spaces/{space}/pages/{100000 + i}",  # noqa: E501
            "space": {
                "key": space,
                "name": f"{space} Space",
            },
            "version": {
                "number": random.randint(1, 25),  # noqa: S311
                "when": _rand_date(90),
                "by": {
                    "display_name": author,
                    "email": author.lower().replace(" ", ".") + "@company.com",
                },
            },
            "created": _rand_date(365),
            "updated": _rand_date(30),
            "body_excerpt": f"This page documents the {random.choice(PAGE_TITLES).lower()} "  # noqa: S311, E501
            f"for the {space} team. Last reviewed by {author}.",
            "ancestors": [
                {"id": str(90000 + i), "title": f"{space} Home"},
            ],
            "labels": random.sample(  # noqa: S311
                [
                    "documentation",
                    "process",
                    "architecture",
                    "runbook",
                    "guide",
                    "template",
                ],
                k=random.randint(0, 3),  # noqa: S311
            ),
        }
        pages.append(page)
    return pages


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def run_benchmark(
    name: str,
    data_generator: Any,
    sizes: list[int],
    encode_gcf: Any,
) -> list[dict]:
    """Run benchmark for one data type at multiple sizes."""
    results = []
    for size in sizes:
        data = data_generator(size)

        # JSON serialization
        t0 = time.perf_counter()
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        json_time = time.perf_counter() - t0
        json_tokens = estimate_tokens(json_str)

        # GCF serialization (using our serializer module)
        # Need to import with env var set
        t0 = time.perf_counter()
        gcf_str = encode_gcf(data)
        gcf_time = time.perf_counter() - t0
        gcf_tokens = estimate_tokens(gcf_str)

        savings_pct = (
            ((json_tokens - gcf_tokens) / json_tokens * 100) if json_tokens > 0 else 0
        )

        results.append(
            {
                "name": name,
                "rows": size,
                "json_chars": len(json_str),
                "json_tokens": json_tokens,
                "json_time_ms": round(json_time * 1000, 2),
                "gcf_chars": len(gcf_str),
                "gcf_tokens": gcf_tokens,
                "gcf_time_ms": round(gcf_time * 1000, 2),
                "savings_pct": round(savings_pct, 1),
            }
        )
    return results


def main() -> None:
    try:
        from gcf import encode_generic
    except ImportError:
        print("ERROR: gcf-python not installed. Install with: pip install gcf-python")
        sys.exit(1)

    sizes = [10, 50, 100, 200]

    def encode_gcf(data: Any) -> str:
        """Encode data using GCF."""
        return encode_generic(data)

    all_results = []

    # Benchmark 1: Jira issues (flat list, as from search results display)
    print("Running: Jira Issues (list)...")
    all_results.extend(
        run_benchmark("Jira Issues (list)", generate_jira_issues, sizes, encode_gcf)
    )

    # Benchmark 2: Jira search result (wrapper with issues key)
    print("Running: Jira Search Result (wrapper)...")
    all_results.extend(
        run_benchmark(
            "Jira Search Result", generate_jira_search_result, sizes, encode_gcf
        )
    )

    # Benchmark 3: Confluence pages (flat list)
    print("Running: Confluence Pages (list)...")
    all_results.extend(
        run_benchmark(
            "Confluence Pages (list)", generate_confluence_pages, sizes, encode_gcf
        )
    )

    # Print results
    print()
    print("=" * 90)
    print("GCF Benchmark Results: mcp-atlassian")
    print(f"Date: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"gcf-python version: {__import__('gcf').__version__}")
    print("Token estimation: len(text) // 4")
    print("=" * 90)
    print()
    print(
        f"{'Dataset':<30} {'Rows':>5} {'JSON tok':>10} {'GCF tok':>10} {'Savings':>10} {'JSON ms':>10} {'GCF ms':>10}"  # noqa: E501
    )
    print("-" * 90)

    output_lines = []
    output_lines.append("=" * 90)
    output_lines.append("GCF Benchmark Results: mcp-atlassian")
    output_lines.append(
        f"Date: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    output_lines.append(f"gcf-python version: {__import__('gcf').__version__}")
    output_lines.append("Token estimation: len(text) // 4")
    output_lines.append("=" * 90)
    output_lines.append("")
    output_lines.append(
        f"{'Dataset':<30} {'Rows':>5} {'JSON tok':>10} {'GCF tok':>10} {'Savings':>10} {'JSON ms':>10} {'GCF ms':>10}"  # noqa: E501
    )
    output_lines.append("-" * 90)

    for r in all_results:
        line = (
            f"{r['name']:<30} {r['rows']:>5} {r['json_tokens']:>10,} {r['gcf_tokens']:>10,}"  # noqa: E501
            f" {r['savings_pct']:>9.1f}% {r['json_time_ms']:>9.2f} {r['gcf_time_ms']:>9.2f}"  # noqa: E501
        )
        print(line)
        output_lines.append(line)

    # Summary
    total_json = sum(r["json_tokens"] for r in all_results)
    total_gcf = sum(r["gcf_tokens"] for r in all_results)
    avg_savings = ((total_json - total_gcf) / total_json * 100) if total_json > 0 else 0

    print()
    print(
        f"Overall: {total_json:,} JSON tokens -> {total_gcf:,} GCF tokens ({avg_savings:.1f}% reduction)"  # noqa: E501
    )
    print()

    # Sample output comparison
    sample_issues = generate_jira_issues(3)
    json_sample = json.dumps(sample_issues, indent=2, ensure_ascii=False)
    gcf_sample = encode_gcf(sample_issues)

    print("=" * 90)
    print("Sample: 3 Jira issues")
    print("=" * 90)
    print()
    print("--- JSON ---")
    print(json_sample[:600] + "..." if len(json_sample) > 600 else json_sample)
    print()
    print("--- GCF ---")
    print(gcf_sample)
    print()

    output_lines.append("")
    output_lines.append(
        f"Overall: {total_json:,} JSON tokens -> {total_gcf:,} GCF tokens ({avg_savings:.1f}% reduction)"  # noqa: E501
    )
    output_lines.append("")
    output_lines.append("=" * 90)
    output_lines.append("Sample: 3 Jira issues")
    output_lines.append("=" * 90)
    output_lines.append("")
    output_lines.append("--- JSON ---")
    output_lines.append(
        json_sample[:600] + "..." if len(json_sample) > 600 else json_sample
    )
    output_lines.append("")
    output_lines.append("--- GCF ---")
    output_lines.append(gcf_sample)

    # Write results file
    results_file = "benchmarks/results-2026-06-17.txt"
    with open(results_file, "w") as f:
        f.write("\n".join(output_lines) + "\n")
    print(f"Results written to {results_file}")


if __name__ == "__main__":
    main()
