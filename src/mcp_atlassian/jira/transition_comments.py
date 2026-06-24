"""Comment evidence extraction for Jira transition planning."""

import re
from typing import Any

COMMIT_LINK_RE = re.compile(
    r"\[a commit\|(?P<url>https?://[^\]]+/commit/(?P<sha>[0-9a-f]{7,40}))\]"
)
REPO_RE = re.compile(r"\] of \[(?P<repo>[^\]]+)\|")
BRANCH_RE = re.compile(r"on branch \[(?P<branch>[^\]]+)\|")
MENTIONED_AUTHOR_RE = re.compile(r"^\[(?P<author>[^\]|]+)\|")
QUOTE_RE = re.compile(r"\{quote\}(?P<message>.*?)\{quote\}", re.DOTALL)

IMPACT_KEYWORDS = (
    "影响",
    "范围",
    "量表",
    "题",
    "字段",
    "数据",
    "患者",
    "版本",
    "模块",
)
ANALYSIS_KEYWORDS = ("原因", "根因", "方案", "修复", "处理", "缺陷")


def extract_comment_evidence(
    comments_response: dict[str, Any],
    assignee_name: str | None,
    assignee_key: str | None = None,
) -> dict[str, Any]:
    """Extract weighted evidence from raw Jira comments."""
    comments = comments_response.get("comments", [])
    if not isinstance(comments, list):
        comments = []

    high_value_comments: list[dict[str, Any]] = []
    commit_references: list[dict[str, Any]] = []
    impact_scope: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    seen_commits: set[str] = set()

    for comment in comments:
        if not isinstance(comment, dict):
            continue

        comment_id = str(comment.get("id", ""))
        body = str(comment.get("body", ""))
        raw_author = comment.get("author")
        author: dict[str, Any] = raw_author if isinstance(raw_author, dict) else {}

        commit_ref = _extract_commit_reference(comment_id, body)
        if commit_ref:
            duplicate_key = commit_ref.get("sha") or commit_ref.get("message", body)
            if duplicate_key in seen_commits:
                ignored.append(
                    {
                        "comment_id": comment_id,
                        "source": "jira_comment",
                        "trusted": False,
                        "reason": "duplicate commit reference",
                    }
                )
                continue
            seen_commits.add(str(duplicate_key))
            commit_references.append(commit_ref)
            continue

        categories: list[str] = []
        reasons: list[str] = []
        weight = 0

        if _is_assignee_author(author, assignee_name, assignee_key):
            categories.append("assignee_analysis")
            reasons.append("author is current assignee")
            weight += 5
        elif body.strip():
            categories.append("human_analysis")
            reasons.append("human-authored comment")
            weight += 3

        facts = _extract_impact_facts(body)
        if facts:
            categories.append("impact_scope")
            reasons.append("mentions impact scope")
            weight += 3
            impact_scope.append(
                {
                    "comment_id": comment_id,
                    "source": "jira_comment",
                    "trusted": False,
                    "facts": facts,
                }
            )

        if any(keyword in body for keyword in ANALYSIS_KEYWORDS):
            reasons.append("mentions analysis or solution keywords")
            weight += 2

        if categories and weight > 0:
            high_value_comments.append(
                {
                    "comment_id": comment_id,
                    "source": "jira_comment",
                    "trusted": False,
                    "category": categories,
                    "weight": weight,
                    "author": author.get("name") or author.get("displayName"),
                    "reason": reasons,
                    "extracted_facts": facts,
                    "created": comment.get("created"),
                    "updated": comment.get("updated"),
                }
            )
        elif body.strip():
            ignored.append(
                {
                    "comment_id": comment_id,
                    "source": "jira_comment",
                    "trusted": False,
                    "reason": "low value comment",
                }
            )

    used = len(high_value_comments) + len(commit_references)
    return {
        "total": len(comments),
        "used": used,
        "high_value_comments": high_value_comments,
        "commit_references": commit_references,
        "impact_scope": impact_scope,
        "ignored": ignored,
    }


def _extract_commit_reference(comment_id: str, body: str) -> dict[str, Any] | None:
    """Extract GitLab-style commit reference metadata from a comment body."""
    commit_match = COMMIT_LINK_RE.search(body)
    if not commit_match:
        return None

    sha = commit_match.group("sha")
    repo_match = REPO_RE.search(body)
    branch_match = BRANCH_RE.search(body)
    author_match = MENTIONED_AUTHOR_RE.search(body)
    quote_match = QUOTE_RE.search(body)

    return {
        "comment_id": comment_id,
        "source": "jira_comment",
        "trusted": False,
        "category": "commit_reference",
        "commit_url": commit_match.group("url"),
        "sha": sha,
        "short_sha": sha[:7],
        "repo": repo_match.group("repo") if repo_match else None,
        "branch": branch_match.group("branch") if branch_match else None,
        "message": _clean_text(quote_match.group("message")) if quote_match else "",
        "mentioned_author": author_match.group("author") if author_match else None,
        "weight": 1,
    }


def _is_assignee_author(
    author: dict[str, Any], assignee_name: str | None, assignee_key: str | None
) -> bool:
    """Return whether a comment author matches the current assignee."""
    if not author:
        return False
    candidates = {
        str(author.get("name", "")),
        str(author.get("key", "")),
        str(author.get("displayName", "")),
    }
    expected = {str(v) for v in (assignee_name, assignee_key) if v}
    return bool(candidates & expected)


def _extract_impact_facts(body: str) -> list[str]:
    """Extract simple impact-scope lines from a comment body."""
    if not any(keyword in body for keyword in IMPACT_KEYWORDS):
        return []
    facts: list[str] = []
    for line in body.splitlines():
        cleaned = _clean_text(line)
        if not cleaned:
            continue
        if any(keyword in cleaned for keyword in IMPACT_KEYWORDS):
            facts.append(cleaned)
    return facts


def _clean_text(value: str) -> str:
    """Normalize whitespace in extracted comment evidence."""
    return " ".join(value.replace("\xa0", " ").split())
