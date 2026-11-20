"""Conversions finish quickly on inputs built to make regexes backtrack.

Each case is one input that took seconds or longer before the fix. A case
must finish inside a short wall-clock budget; golden-output cases pin the
conversions that the rewritten patterns must keep unchanged.
"""

import re
import signal
import sys
import threading
import tracemalloc
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from bs4 import BeautifulSoup

from mcp_atlassian.preprocessing.base import (
    BasePreprocessor,
    _contains_html_tag,
    _restore_blocks,
    _restore_code_macro_blocks,
)
from mcp_atlassian.preprocessing.jira import JiraPreprocessor

BUDGET_SECONDS = 1.5

#: A coverage tracer slows pure-Python scans several times over, and CI runs
#: the suite under one. The inputs here took far longer than this before the
#: fix, so the wider budget still catches a return to the old behavior.
TRACED_BUDGET_FACTOR = 20


def _budget_seconds() -> float:
    """Return the wall-clock budget for one call in this test run."""
    try:
        import coverage

        traced = coverage.Coverage.current() is not None
    except ImportError:
        traced = False
    if traced or sys.gettrace() is not None:
        return BUDGET_SECONDS * TRACED_BUDGET_FACTOR
    return BUDGET_SECONDS


_CODE_MACRO = (
    '<ac:structured-macro ac:name="code"><ac:plain-text-body>'
    "<![CDATA[x]]></ac:plain-text-body></ac:structured-macro>"
)


class _BudgetExceededError(Exception):
    """Raised by SIGALRM when a call runs past its budget."""


@contextmanager
def _time_budget(seconds: float) -> Iterator[None]:
    """Interrupt the block with an exception once ``seconds`` have passed.

    The regex engine checks for signals while matching, so the alarm also
    stops a regex that is backtracking.
    """
    if threading.current_thread() is not threading.main_thread():
        pytest.skip("SIGALRM budget needs the main thread")

    def _on_alarm(signum: int, frame: Any) -> None:
        raise _BudgetExceededError(f"call ran longer than {seconds} s")

    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _finishes_in_budget(call: Callable[[], object]) -> None:
    with _time_budget(_budget_seconds()):
        call()


@pytest.fixture
def jira() -> JiraPreprocessor:
    return JiraPreprocessor(base_url="https://jira.example.invalid")


@pytest.fixture
def base() -> BasePreprocessor:
    return BasePreprocessor(base_url="https://example.invalid/wiki")


# --- Jira wiki markup -> Markdown (clean_jira_text) -----------------------

CLEAN_JIRA_TEXT_INPUTS = {
    "unterminated_smart_links": "[|" * 2000,
    "open_brackets": "[" * 20000,
    "unterminated_wiki_links": "[a|" * 10000,
    "brackets_before_link_targets": "[" * 10000 + "](x)" * 10000,
    "unterminated_wiki_link_targets": "[" * 10000 + "|" + "a" * 10000,
    "unterminated_inline_code_after_brace": "{{a}" * 10000,
    "unterminated_mentions": "[~accountid:" * 5000,
    "unterminated_inline_code": "{{" * 20000,
    "many_inline_code_spans": "{{a}} " * 12000,
    "unterminated_panels": "{panel:" * 9000,
    "panel_openers_before_one_brace": "{panel:" * 128000 + "}",
    "many_table_headers": "||a||\n" * 100000,
    "unterminated_colors": "{color:" * 12000,
    "unterminated_code_blocks": "{code:a}" * 8000,
    "repeated_alt_params": "!a|" + "alt=x" * 6000,
    "image_sources_without_terminator": "!a" * 30000,
    "open_angle_brackets": "<" * 60000,
}


@pytest.mark.parametrize(
    "text",
    list(CLEAN_JIRA_TEXT_INPUTS.values()),
    ids=list(CLEAN_JIRA_TEXT_INPUTS),
)
def test_clean_jira_text_finishes_in_budget(jira: JiraPreprocessor, text: str) -> None:
    _finishes_in_budget(lambda: jira.clean_jira_text(text))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "[PROJ-1|https://jira.example.invalid/browse/PROJ-1|smart-link]",
            "[PROJ-1](https://jira.example.invalid/browse/PROJ-1)",
        ),
        (
            "see [x|https://site.example/wiki/spaces/S/pages/1/My+Page?a=1"
            "|smart-link] and [y|https://other.example/p?q=1|smart-link]",
            "see [My Page](https://site.example/wiki/spaces/S/pages/1/My+Page?a=1)"
            " and [y](https://other.example/p)",
        ),
        (
            "hi [~accountid:abc123] and [~accountid:abc123]",
            "hi User:abc123 and User:abc123",
        ),
        (
            "[docs|https://example.invalid/d] now",
            "[docs](https://example.invalid/d) now",
        ),
        ("plain [note] here", "plain note here"),
        ("use {{a{b}} here", "use `a{b` here"),
        ("{{x}} and {{y}}", "`x` and `y`"),
        ("{panel:title=T}body{panel}", "**T**\nbody"),
        ("{color:red}warm{color}", "warm"),
        ("!pic.png|alt=Pic,width=10!", "![Pic](pic.png)"),
        ("!pic.png|width=10!", "![](pic.png)"),
        ("!pic.png!", "![](pic.png)"),
        ("{code:java}int a;{code}", "```java\nint a;\n```"),
        ("{{a{{b}}", "`a{{b`"),
        ("{{x}y}} {{z}}", "{{x}y}} `z`"),
        ("!a|alt=,x alt=y,z!", "![y](a)"),
        ("[a [b|c] d", "[a [b](c) d"),
        ("[a[b]c", "a[bc"),
        ("[~accountid:a[b] x", "User:a[b x"),
        (
            "[t|https://s.example/wiki/spaces/A/B/pages/1/T?x|smart-link]",
            "[T](https://s.example/wiki/spaces/A/B/pages/1/T?x)",
        ),
    ],
)
def test_clean_jira_text_keeps_conversions(
    jira: JiraPreprocessor, text: str, expected: str
) -> None:
    assert jira.clean_jira_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{panel:title=T{x}body{panel}", "\n**T{x**\nbody\n"),
        ("{color:r{d}x{color}", '<span style=\\"color:r{d\\">x</span>'),
        ("!a!b|w=1!", "![]([](a)b)"),
        ("{{a{{b}}", "`a{{b`"),
    ],
)
def test_jira_to_markdown_keeps_conversions(
    jira: JiraPreprocessor, text: str, expected: str
) -> None:
    assert jira.jira_to_markdown(text) == expected


# --- Markdown -> Jira wiki markup (markdown_to_jira) ----------------------

MARKDOWN_TO_JIRA_INPUTS = {
    "asterisk_run": "*" * 4000,
    "underscore_run": "_" * 4000,
    "mixed_delimiter_run": "*_" * 2000,
    "open_brackets": "[" * 20000,
    "unterminated_link_targets": "[a](" * 15000,
    "open_angle_brackets": "<" * 30000,
    "unterminated_autolinks": "<a:" * 10000,
    "unterminated_color_spans": '<span style="color:#f">' * 4000,
    "unterminated_cite_tags": "<cite>" * 10000,
    "unterminated_image_alts": "![a" * 10000,
    "delimiter_runs_of_falling_length": " ".join("*" * n for n in range(300, 0, -1)),
    "unique_mixed_delimiter_runs": " ".join(
        format(n, "b").replace("0", "*").replace("1", "_") for n in range(2048, 6000)
    ),
    "unterminated_image_sources": "![](x" * 12000,
    "many_inline_code_spans": "`a` " * 20000,
    "blank_lines": "\n" * 16000,
    "blank_lines_before_number": "\n" * 16000 + "1",
    "many_tables": "|a|\n|-|\nx\n" * 50000,
}


@pytest.mark.parametrize(
    "text",
    list(MARKDOWN_TO_JIRA_INPUTS.values()),
    ids=list(MARKDOWN_TO_JIRA_INPUTS),
)
def test_markdown_to_jira_finishes_in_budget(jira: JiraPreprocessor, text: str) -> None:
    _finishes_in_budget(lambda: jira.markdown_to_jira(text))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**bold** and *it* and ***both***", "*bold* and _it_ and *both*"),
        ("__strong__ and _em_", "*strong* and _em_"),
        ("snake_case_name", r"snake\_case\_name"),
        ("[a](https://x.example/p?f[a]=1)", "[a|https://x.example/p?f[a]=1]"),
        ("[a [b](https://x.example)", "[a [b|https://x.example]"),
        ("<https://x.example/a>", "[https://x.example/a]"),
        ("<user@example.invalid>", "[user@example.invalid]"),
        ("<cite>c</cite> <del>d</del> <sup>s</sup>", "??c?? -d- ^s^"),
        ('<span style="color:#ff0000">red</span>', "{color:#ff0000}red{color}"),
        (
            '<span style="color:#f00">a</span> <span style="color:#0f0">b</span>',
            "{color:#f00}a{color} {color:#0f0}b{color}",
        ),
        ("![](https://x.example/i.png)", "!https://x.example/i.png!"),
        ("![Alt](https://x.example/i.png)", "!https://x.example/i.png|alt=Alt!"),
        ("~~gone~~", "-gone-"),
        ("use `a_b` and `c`", "use {{a_b}} and {{c}}"),
        ("```python\nx = 1\n```", "{code:python}\nx = 1\n{code}"),
        ("****bold****", "*bold*"),
        ("*" * 9, "***"),
        ("**_x_** and *****y*****", "*_x_* and *y*"),
        ("[a](b[c)", "[a|b[c]"),
        ("<a:b<c>", "[a:b<c]"),
        ("<cite>a<cite>b</cite>", "??a[cite]b??"),
        ("![a[b](c)", "!c|alt=a[b!"),
        ("[a]b](c)", "[a]b](c)"),
    ],
)
def test_markdown_to_jira_keeps_conversions(
    jira: JiraPreprocessor, text: str, expected: str
) -> None:
    assert jira.markdown_to_jira(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\n\n  - a\nb", "*** a\nb"),
        (" \n 1. x\n\n2. y", "## x\n# y"),
        ("- a\n  - b\n+ c", "* a\n** b\n* c"),
        ("|h|g|\n|-|-|\n| a | b |\nx\n|c|\n|:-:|", "||h||g||\n|a|b|\nx\n||c||"),
    ],
)
def test_markdown_to_jira_keeps_lists_and_tables(
    jira: JiraPreprocessor, text: str, expected: str
) -> None:
    assert jira.markdown_to_jira(text) == expected


def test_jira_to_markdown_keeps_table_separators(jira: JiraPreprocessor) -> None:
    assert jira.jira_to_markdown("||a||b||\n|1|2|\n||x||") == (
        "|a|b|\n|---|---|\n|1|2|\n|x|\n|---|"
    )


def test_emphasis_on_long_delimiter_run_stays_small(jira: JiraPreprocessor) -> None:
    """The extra allocation peak for a 128,000-character run stays under 32 MiB."""
    text = "x" + "*_" * 64000
    tracemalloc.start()
    try:
        jira.markdown_to_jira(text)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 32 * 2**20


def test_bracketed_text_after_wiki_link_keeps_link_unlike_base(
    jira: JiraPreprocessor,
) -> None:
    """Intended difference from base 9336987, which gave ``a](b) [c x``.

    Base dropped the brackets of ``[c]`` by running on from the ``](`` of the
    link before it, which broke that link.
    """
    assert jira.jira_to_markdown("[a|b] [c] x") == "[a](b) c x"


def test_mention_inside_mention_is_replaced_once_unlike_base(
    jira: JiraPreprocessor,
) -> None:
    """Intended difference from base 9336987.

    Base replaced each mention string everywhere, one after another, so the
    inner ``[~accountid:abc]`` was also rewritten inside the outer mention:
    ``User:abc and[~accountid: User:abc``. Each match is now replaced once.
    """
    text = "[~accountid:abc] and[~accountid: [~accountid:abc]"
    assert jira.clean_jira_text(text) == "User:abc andUser: [~accountid:abc"


def test_restore_blocks_restores_nested_placeholders() -> None:
    """A stored block may hold a placeholder stored before it."""
    storage = ["inner", "outer(\x00P0\x00)"]
    assert _restore_blocks("[\x00P1\x00|\x00P0\x00]", storage, "P") == (
        "[outer(inner)|inner]"
    )


def test_restore_blocks_leaves_unknown_placeholders() -> None:
    storage = ["a"]
    text = "\x00P0\x00 \x00P7\x00 \x00P00\x00 \x00P" + "9" * 5000 + "\x00"
    assert _restore_blocks(text, storage, "P") == (
        "a \x00P7\x00 \x00P00\x00 \x00P" + "9" * 5000 + "\x00"
    )


# --- Confluence storage -> Markdown (process_html_content) ----------------


def test_inline_code_macro_after_backtick_run_finishes_in_budget() -> None:
    line = "| " + "`" * 20000 + "y | ``` "
    text = line + "\x00MCPCODEMACRO0\x00 ``` |"
    _finishes_in_budget(
        lambda: _restore_code_macro_blocks(
            text, {"\x00MCPCODEMACRO0\x00": "```\nx\n```"}
        )
    )


def test_inline_code_macro_opening_is_last_backtick_run() -> None:
    line = "| ``x`` y | ``` "
    text = line + "\x00MCPCODEMACRO0\x00 ``` |"
    assert _restore_code_macro_blocks(
        text, {"\x00MCPCODEMACRO0\x00": "```\nz\n```"}
    ) == ("| ``x`` y | ``` z ``` |")


def test_table_cell_backtick_run_next_to_code_macro_finishes_in_budget(
    base: BasePreprocessor,
) -> None:
    html = (
        "<table><tr><td>" + "`" * 20000 + "y</td><td>" + _CODE_MACRO + "</td></tr>"
        "</table>"
    )
    _finishes_in_budget(lambda: base.process_html_content(html))


def test_many_code_macro_placeholders_restore_in_budget() -> None:
    count = 12000
    code_blocks = {f"\x00MCPCODEMACRO{i}\x00": f"```\nx{i}\n```" for i in range(count)}
    markdown = "\n\n".join(f"```\n{placeholder}\n```" for placeholder in code_blocks)
    restored: list[str] = []
    _finishes_in_budget(
        lambda: restored.append(_restore_code_macro_blocks(markdown, code_blocks))
    )
    assert restored == ["\n\n".join(code_blocks.values())]


def test_many_inline_code_macro_placeholders_restore_in_budget() -> None:
    count = 12000
    code_blocks = {f"\x00MCPCODEMACRO{i}\x00": f"```\nx{i}\n```" for i in range(count)}
    markdown = "|" + "|".join(f" `{placeholder}` " for placeholder in code_blocks)
    restored: list[str] = []
    _finishes_in_budget(
        lambda: restored.append(_restore_code_macro_blocks(markdown + "|", code_blocks))
    )
    assert restored == ["|" + "|".join(f" ``` x{i} ``` " for i in range(count)) + "|"]


def test_many_sibling_code_macros_convert_in_budget(base: BasePreprocessor) -> None:
    soup = BeautifulSoup(_CODE_MACRO * 8000, "html.parser")
    code_blocks: list[dict[str, str]] = []
    _finishes_in_budget(
        lambda: code_blocks.append(base._process_code_macros_in_soup(soup))
    )
    assert list(code_blocks[0].values()) == ["```\nx\n```"] * 8000
    assert (
        str(soup)
        == "<pre><code>\x00MCPCODEMACRO"
        + (
            "\x00</code></pre><pre><code>\x00MCPCODEMACRO".join(
                str(i) for i in range(8000)
            )
        )
        + "\x00</code></pre>"
    )


def test_sibling_code_macros_keep_markdown(base: BasePreprocessor) -> None:
    html = "".join(
        f"<p>p{i}</p>" + _CODE_MACRO.replace("[x]", f"[x{i}]") for i in range(3)
    )
    _, markdown = base.process_html_content(html)
    assert markdown == "\n\n".join(f"p{i}\n\n```\nx{i}\n```" for i in range(3))


@pytest.mark.parametrize(
    ("tag", "depth", "process"),
    [
        ("ac:link", 3000, "_process_user_mentions_in_soup"),
        ("ac:image", 1500, "_process_images_in_soup"),
        ('ac:structured-macro ac:name="code"', 3000, "_process_code_macros_in_soup"),
    ],
    ids=["nested_links", "nested_images", "nested_code_macros"],
)
def test_nested_storage_elements_finish_in_budget(
    base: BasePreprocessor, tag: str, depth: int, process: str
) -> None:
    soup = BeautifulSoup(f"<{tag}>" * depth, "html.parser")
    _finishes_in_budget(lambda: getattr(base, process)(soup))


@pytest.mark.parametrize(
    ("element", "process"),
    [
        (
            '<ac:image><ri:url ri:value="https://i.example/a.png"/></ac:image>',
            "_process_images_in_soup",
        ),
        (
            '<ac:link><ri:user ri:account-id="u"/></ac:link>',
            "_process_user_mentions_in_soup",
        ),
        (
            '<ac:structured-macro ac:name="expand"><ac:rich-text-body>'
            "<p>a</p><p>b</p></ac:rich-text-body></ac:structured-macro>",
            "_process_remaining_macros_in_soup",
        ),
    ],
    ids=["sibling_images", "sibling_links", "sibling_macros"],
)
def test_sibling_storage_elements_finish_in_budget(
    base: BasePreprocessor, element: str, process: str
) -> None:
    soup = BeautifulSoup(element * 8000, "html.parser")
    _finishes_in_budget(lambda: getattr(base, process)(soup))
    assert "ac:" not in str(soup)


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            '<ac:image><ri:url ri:value="https://i.example/a.png"/>'
            '<ac:image><ri:attachment ri:filename="f.png"/></ac:image></ac:image>',
            "![f.png](f.png)",
        ),
        (
            '<ac:structured-macro ac:name="code"><ac:structured-macro ac:name="info">'
            "<ac:plain-text-body><![CDATA[x]]></ac:plain-text-body>"
            "</ac:structured-macro></ac:structured-macro>",
            "```\nx\n```",
        ),
        (
            '<ac:link><ac:link><ri:user ri:account-id="u"/></ac:link></ac:link>',
            "@user\\_u",
        ),
    ],
    ids=["nested_image", "nested_code_macro", "nested_link"],
)
def test_nested_storage_elements_keep_markdown(
    base: BasePreprocessor, html: str, expected: str
) -> None:
    """The outer element takes the first matching child anywhere below it."""
    _, markdown = base.process_html_content(html)
    assert markdown == expected


def test_sibling_storage_elements_keep_markdown(base: BasePreprocessor) -> None:
    html = (
        '<ac:image><ri:url ri:value="https://i.example/a.png"/></ac:image>'
        '<ac:link><ri:user ri:account-id="u"/></ac:link>'
        '<ac:structured-macro ac:name="expand"><ac:rich-text-body>'
        "<p>a</p><p>b</p></ac:rich-text-body></ac:structured-macro>"
    ) * 3
    _, markdown = base.process_html_content(html)
    assert (
        markdown
        == "![a.png](https://i.example/a.png)@user\\_u\n\na\n\nb\n\n" * 2
        + ("![a.png](https://i.example/a.png)@user\\_u\n\na\n\nb")
    )


@pytest.mark.parametrize(
    "html",
    [
        "<ol>" + "<li>a</li>" * 6000 + "</ol>",
        "<table><thead>" + "<tr><td>a</td></tr>" * 3000 + "</thead></table>",
    ],
    ids=["long_ordered_list", "many_header_rows"],
)
def test_long_lists_and_tables_finish_in_budget(
    base: BasePreprocessor, html: str
) -> None:
    _finishes_in_budget(lambda: base.process_html_content(html))


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<ol><li>a</li><li>b</li><li>c</li></ol>", "1. a\n2. b\n3. c"),
        ('<ol start="4"><li>a</li><li>b</li></ol>', "4. a\n5. b"),
        (
            "<ol><li>a<ol><li>x</li><li>y</li></ol></li><li>b</li></ol>",
            "1. a\n   1. x\n   2. y\n2. b",
        ),
        ("<ol><li>a\n<p>more</p></li><li>b</li></ol>", "1. a\n\n   more\n2. b"),
        ("<ul><li>a<ul><li>b</li></ul></li></ul>", "* a\n  + b"),
        (
            "<table><thead><tr><th>h</th></tr></thead>"
            "<tbody><tr><td>v</td></tr></tbody></table>",
            "| h |\n| --- |\n| v |",
        ),
        (
            "<table><thead><tr><td>a</td></tr><tr><td>b</td></tr></thead></table>",
            "|  |\n| --- |\n| a |\n| b |",
        ),
        (
            "<table><tr><td>a</td></tr><tr><td>b</td></tr></table>",
            "|  |\n| --- |\n| a |\n| b |",
        ),
    ],
)
def test_lists_and_tables_keep_markdown(
    base: BasePreprocessor, html: str, expected: str
) -> None:
    _, markdown = base.process_html_content(html)
    assert markdown.strip() == expected


def test_storage_references_keep_conversions(base: BasePreprocessor) -> None:
    html = (
        '<p><ac:link><ri:user ri:account-id="acc-1"/></ac:link> '
        '<ac:image ac:width="20"><ri:attachment ri:filename="pic.png"/>'
        "</ac:image> "
        '<ac:image><ri:url ri:value="https://img.example/a/b.png"/></ac:image></p>'
        + _CODE_MACRO.replace(
            "<ac:plain", '<ac:parameter ac:name="language">py</ac:parameter><ac:plain'
        )
    )
    _, markdown = base.process_html_content(html, content_id="42")
    assert "@user\\_acc-1" in markdown
    assert (
        "![pic.png](https://example.invalid/wiki/download/attachments/42/pic.png)"
        in markdown
    )
    assert "![b.png](https://img.example/a/b.png)" in markdown
    assert "```py\nx\n```" in markdown


@pytest.mark.parametrize(
    "text",
    ["<a>", "<<a>", "<a<>", "<>", "<>|>", "a > b < c", "x <b", "> <", "<\n>", ""],
)
def test_contains_html_tag_matches_regex_search(text: str) -> None:
    assert _contains_html_tag(text) == bool(re.search(r"<[^>]+>", text))


_DOT_RUN_SCRIPT = """
import sys
from mcp_atlassian.preprocessing.confluence import ConfluencePreprocessor
confluence = ConfluencePreprocessor(base_url="https://example.atlassian.net")
confluence.markdown_to_confluence_storage(sys.argv[1] + "." * 64000)
"""


@pytest.mark.parametrize("prefix", ["http://a", "https://a", "ftp://a", "www.a"])
def test_short_url_with_dot_run_converts_in_budget(prefix: str) -> None:
    # A short URL followed by a run of dots made magiclink backtrack in
    # exponential (before pymdown-extensions 11.0.1) or quadratic (12.x) time
    # inside one regex call, which no signal interrupts and the converter's
    # fallback would run again, so the call runs in a child process.
    import subprocess

    subprocess.run(
        [sys.executable, "-c", _DOT_RUN_SCRIPT, prefix],
        check=True,
        timeout=30,
    )


def test_magic_link_pattern_matches_like_stock() -> None:
    import random

    from pymdownx import magiclink

    from mcp_atlassian.preprocessing.confluence import _MAGIC_LINK_RE

    if _MAGIC_LINK_RE is None:
        pytest.skip("installed magiclink has no host part to cut")
    stock = re.compile(magiclink.RE_LINK, re.DOTALL | re.UNICODE)
    rng = random.Random(0)
    alphabet = "a_-.=(/)?#w:ht\u00fc1 "
    for _ in range(20000):
        body = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 14)))
        text = rng.choice(["http://", "https://", "ftp://", "www.", ""]) + body
        for pos in range(len(text)):
            a = stock.match(text, pos)
            b = _MAGIC_LINK_RE.match(text, pos)
            assert (a and (a.span(), a.group("www"))) == (
                b and (b.span(), b.group("www"))
            ), text
