"""Jira-specific text preprocessing module."""

import bisect
import logging
import re
from array import array
from collections.abc import Callable
from typing import Any

from .base import BasePreprocessor, _extract_blocks, _restore_blocks

logger = logging.getLogger("mcp-atlassian")

_ISSUE_KEY_PATTERN = r"[A-Z][A-Z0-9_]+-\d+(?:-\d+)*"


def _sub_up_to_last(
    pattern: str,
    repl: str | Callable[[re.Match[str]], str],
    text: str,
    closer: str,
    flags: int = 0,
) -> str:
    """Run ``re.sub`` only on the text up to the last ``closer``.

    For a pattern whose match must end with the literal ``closer``, no match
    can start after the last ``closer``. Leaving that tail out keeps an
    opener that is never closed from scanning to the end of the text once
    per opener, which made the pass quadratic. The result is the same as
    ``re.sub`` on the whole text.
    """
    end = text.rfind(closer)
    if end == -1:
        return text
    end += len(closer)
    return re.sub(pattern, repl, text[:end], flags=flags) + text[end:]


def _convert_panel(params: str | None, content: str) -> str:
    """Convert a Jira {panel} block to markdown."""
    title = ""
    if params:
        title_match = re.search(r"title=([^|}]+)", params)
        if title_match:
            title = title_match.group(1).strip()
    content = content.strip()
    if title:
        return f"\n**{title}**\n{content}\n"
    return f"\n{content}\n"


class _NextIndex:
    """Find the next match of a pattern for start positions that only rise.

    The scanners below ask, opener by opener from left to right, where the
    next closing character is. The last answer stays valid for every later
    start up to it, so the text between is never searched twice and all
    queries together read the text once. ``re.sub`` searched again from
    every opener, which made unclosed openers quadratic.
    """

    def __init__(self, text: str, pattern: str) -> None:
        self._text = text
        self._pattern = re.compile(pattern)
        self._searched_from = 0
        self._found = -1

    def __call__(self, pos: int) -> int:
        """Return the first match position at or after ``pos``, else len(text)."""
        if self._searched_from <= pos <= self._found:
            return self._found
        match = self._pattern.search(self._text, pos)
        self._searched_from = pos
        self._found = match.start() if match else len(self._text)
        return self._found


def _scan_sub(
    text: str,
    opener: str,
    convert: Callable[[int, int], tuple[int, int, str] | None],
) -> str:
    """Replace matches left to right, the way ``re.sub`` does.

    ``convert(start, search_from)`` gets each ``opener`` position at or after
    the end of the previous match and returns ``(match_start, match_end,
    replacement)``, or None when no match starts there.
    """
    parts: list[str] = []
    copied = pos = 0
    while (start := text.find(opener, pos)) != -1:
        found = convert(start, pos)
        if found is None:
            pos = start + 1
            continue
        match_start, match_end, replacement = found
        parts.append(text[copied:match_start])
        parts.append(replacement)
        copied = pos = match_end
    parts.append(text[copied:])
    return "".join(parts)


def _sub_mentions(text: str) -> str:
    r"""``re.sub(r"\[~accountid:(.*?)\]", r"User:\1", text)`` in linear time."""
    opener = "[~accountid:"
    close = _NextIndex(text, r"[\]\n]")

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        body = start + len(opener)
        end = close(body)
        if end == len(text) or text[end] != "]":
            return None
        return start, end + 1, f"User:{text[body:end]}"

    return _scan_sub(text, opener, convert)


def _sub_smart_links(text: str, convert_link: Callable[[str, str], str]) -> str:
    r"""Replace ``\[(.*?)\|(.*?)\|smart-link\]`` matches in linear time.

    The link text ends at the first "|" after the "[", and the URL at the
    first "|smart-link]" after that, all on one line.
    """
    closer = "|smart-link]"
    pipe = _NextIndex(text, r"\|")
    close = _NextIndex(text, re.escape(closer))
    newline = _NextIndex(text, r"\n")

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        bar = pipe(start + 1)
        if bar == len(text):
            return None
        end = close(bar + 1)
        if end == len(text) or newline(start) < end:
            return None
        link = convert_link(text[start + 1 : bar], text[bar + 1 : end])
        return start, end + len(closer), link

    return _scan_sub(text, "[", convert)


_PAGE_ID = re.compile(r"\d+/")


def _confluence_page_title(url: str) -> str | None:
    r"""Group 1 of ``wiki/spaces/.+?/pages/\d+/(.+?)(?:\?|$)`` in ``url``.

    Only the first "wiki/spaces/" can match: a later one has fewer page
    paths after it. The title runs to the first "?" after its first
    character.
    """
    spaces = url.find("wiki/spaces/")
    if spaces == -1:
        return None
    pos = spaces + len("wiki/spaces/") + 1
    while (pages := url.find("/pages/", pos)) != -1:
        page_id = _PAGE_ID.match(url, pages + len("/pages/"))
        if page_id and page_id.end() < len(url):
            title_start = page_id.end()
            title_end = url.find("?", title_start + 1)
            return url[title_start : title_end if title_end != -1 else len(url)]
        pos = pages + 1
    return None


def _extract_inline_code(text: str, storage: list[str]) -> str:
    r"""``_extract_blocks`` for ``\{\{([^}]+)\}\}`` in linear time."""
    close = _NextIndex(text, r"\}")

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        end = close(start + 2)
        if end == start + 2 or not text.startswith("}}", end):
            return None
        placeholder = f"\x00INLINECODE{len(storage)}\x00"
        storage.append(f"`{text[start + 2 : end]}`")
        return start, end + 2, placeholder

    return _scan_sub(text, "{{", convert)


def _sub_panels(text: str) -> str:
    r"""Convert ``\{panel(?::([^}]*))?\}([\s\S]*?)\{panel\}`` in linear time."""
    closer = "{panel}"
    brace = _NextIndex(text, r"\}")
    # One finder per branch keeps each one's queries rising.
    close_plain = _NextIndex(text, re.escape(closer))
    close_with_params = _NextIndex(text, re.escape(closer))

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        after = start + len("{panel")
        if text.startswith("}", after):
            body, close = after + 1, close_plain
        elif text.startswith(":", after):
            params_end = brace(after + 1)
            if params_end == len(text):
                return None
            body, close = params_end + 1, close_with_params
        else:
            return None
        end = close(body)
        if end == len(text):
            return None
        # Slice the parameters only for a panel that closes: copying them for
        # every unclosed opener made a run of openers quadratic.
        params = None if close is close_plain else text[after + 1 : body - 1]
        return start, end + len(closer), _convert_panel(params, text[body:end])

    return _scan_sub(text, "{panel", convert)


def _sub_images_with_params(text: str, *, with_alt: bool) -> str:
    r"""Convert Jira images that carry parameters, in linear time.

    With ``with_alt`` this is
    ``!([^|\n\s]+)\|([^\n!]*)alt=([^\n!\,]+?)(,([^\n!]*))?!`` -> ``![\3](\1)``,
    otherwise ``!([^|\n\s]+)\|([^\n!]*)!`` -> ``![](\1)``. The source runs to
    the first "|" or whitespace and the parameters to the first "!" or
    newline. The alt text is the value of the last "alt=" with one.
    """
    source_end = _NextIndex(text, r"[|\s]")
    params_end = _NextIndex(text, r"[!\n]")
    # Openers inside one source share its parameters; look them up once.
    alts: dict[int, str | None] = {}

    def last_alt(params: int, end: int) -> str | None:
        if params not in alts:
            alts[params] = None
            key = text.rfind("alt=", params, end)
            while key != -1:
                value = key + len("alt=")
                if value < end and text[value] != ",":
                    comma = text.find(",", value, end)
                    alts[params] = text[value : comma if comma != -1 else end]
                    break
                key = text.rfind("alt=", params, key)
        return alts[params]

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        pipe = source_end(start + 1)
        if pipe == start + 1 or pipe == len(text) or text[pipe] != "|":
            return None
        end = params_end(pipe + 1)
        if end == len(text) or text[end] != "!":
            return None
        alt = ""
        if with_alt:
            found = last_alt(pipe + 1, end)
            if found is None:
                return None
            alt = found
        return start, end + 1, f"![{alt}]({text[start + 1 : pipe]})"

    return _scan_sub(text, "!", convert)


def _sub_wiki_links(text: str) -> str:
    r"""``re.sub(r"\[([^|]+)\|(.+?)\]", r"[\1](\2)", text)`` in linear time."""
    pipe = _NextIndex(text, r"\|")
    close = _NextIndex(text, r"\]")
    newline = _NextIndex(text, r"\n")

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        bar = pipe(start + 1)
        if bar == start + 1 or bar == len(text):
            return None
        end = close(bar + 2)
        if end == len(text) or newline(bar + 1) < end:
            return None
        return start, end + 1, f"[{text[start + 1 : bar]}]({text[bar + 1 : end]})"

    return _scan_sub(text, "[", convert)


def _sub_bracketed_text(text: str) -> str:
    r"""Drop the brackets of ``[text]`` not followed by "(", in linear time.

    Like ``re.sub(r"\[(.+?)\]([^\(])", r"\1\2", text)``, except that the
    text ends at its first "]": when that "]" opened a Markdown link target,
    the old pattern ran on to a later "]" and broke the link.
    """
    close = _NextIndex(text, r"\]")
    newline = _NextIndex(text, r"\n")

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        end = close(start + 2)
        if end >= len(text) - 1 or text[end + 1] == "(" or newline(start) < end:
            return None
        return start, end + 2, text[start + 1 : end] + text[end + 1]

    return _scan_sub(text, "[", convert)


def _sub_colors(text: str) -> str:
    r"""Convert ``\{color:([^}]+)\}([\s\S]*?)\{color\}`` in linear time."""
    opener, closer = "{color:", "{color}"
    brace = _NextIndex(text, r"\}")
    close = _NextIndex(text, re.escape(closer))

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        color = start + len(opener)
        color_end = brace(color)
        if color_end == color or color_end == len(text):
            return None
        end = close(color_end + 1)
        if end == len(text):
            return None
        # The backslashes match the raw replacement string used before.
        span = (
            f'<span style=\\"color:{text[color:color_end]}\\">'
            f"{text[color_end + 1 : end]}</span>"
        )
        return start, end + len(closer), span

    return _scan_sub(text, opener, convert)


def _protect_markdown_link_targets(text: str, store: Callable[[str], str]) -> str:
    r"""Store link targets of ``(!?\[[^\]\n]*\]\()([^)]+)(\))`` in linear time."""
    label_end = _NextIndex(text, r"[\]\n]")
    target_end = _NextIndex(text, r"\)")

    def convert(start: int, search_from: int) -> tuple[int, int, str] | None:
        close = label_end(start + 1)
        if close >= len(text) - 1 or text[close] != "]" or text[close + 1] != "(":
            return None
        end = target_end(close + 2)
        if end == close + 2 or end == len(text):
            return None
        if start > search_from and text[start - 1] == "!":
            start -= 1
        return (
            start,
            end + 1,
            f"{text[start : close + 2]}{store(text[close + 2 : end])})",
        )

    return _scan_sub(text, "[", convert)


_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*")


def _protect_markdown_autolinks(text: str, store: Callable[[str], str]) -> str:
    r"""Store autolink targets in linear time.

    Same as ``<((?:[A-Za-z][A-Za-z0-9+.-]*:[^>\s]+|[^<>\s@]+@[^<>\s@]+))>``.
    """
    url_end = _NextIndex(text, r"[>\s]")
    local_end = _NextIndex(text, r"[<>\s@]")
    domain_end = _NextIndex(text, r"[<>\s@]")

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        scheme = _URL_SCHEME.match(text, start + 1)
        if scheme and text.startswith(":", scheme.end()):
            end = url_end(scheme.end() + 1)
            if scheme.end() + 1 < end < len(text) and text[end] == ">":
                return start, end + 1, f"<{store(text[start + 1 : end])}>"
        at = local_end(start + 1)
        if at == start + 1 or at == len(text) or text[at] != "@":
            return None
        end = domain_end(at + 1)
        if end == at + 1 or end == len(text) or text[end] != ">":
            return None
        return start, end + 1, f"<{store(text[start + 1 : end])}>"

    return _scan_sub(text, "<", convert)


def _sub_html_tag(text: str, tag: str, delimiter: str) -> str:
    r"""``re.sub(rf"<{tag}>(.*?)<\/{tag}>", ...)`` in linear time."""
    opener, closer = f"<{tag}>", f"</{tag}>"
    close = _NextIndex(text, re.escape(closer))
    newline = _NextIndex(text, r"\n")

    def convert(start: int, _: int) -> tuple[int, int, str] | None:
        body = start + len(opener)
        end = close(body)
        if end == len(text) or newline(body) < end:
            return None
        return start, end + len(closer), f"{delimiter}{text[body:end]}{delimiter}"

    return _scan_sub(text, opener, convert)


def _sub_markdown_images(text: str) -> str:
    r"""Convert Markdown images to Jira images in linear time.

    Same as ``!\[\]\(([^)\n\s]+)\)`` -> ``!\1!`` followed by
    ``!\[([^\]\n]+)\]\(([^)\n\s]+)\)`` -> ``!\2|alt=\1!``.
    """
    source_end = _NextIndex(text, r"[)\s]")

    def convert_plain(start: int, _: int) -> tuple[int, int, str] | None:
        source = start + len("![](")
        end = source_end(source)
        if end == source or end == len(text) or text[end] != ")":
            return None
        return start, end + 1, f"!{text[source:end]}!"

    text = _scan_sub(text, "![](", convert_plain)
    alt_end = _NextIndex(text, r"[\]\n]")
    source_end = _NextIndex(text, r"[)\s]")

    def convert_alt(start: int, _: int) -> tuple[int, int, str] | None:
        alt = start + 2
        close = alt_end(alt)
        if close == alt or close >= len(text) - 1:
            return None
        if text[close] != "]" or text[close + 1] != "(":
            return None
        end = source_end(close + 2)
        if end == close + 2 or end == len(text) or text[end] != ")":
            return None
        return start, end + 1, f"!{text[close + 2 : end]}|alt={text[alt:close]}!"

    return _scan_sub(text, "![", convert_alt)


def _sub_markdown_links(text: str) -> str:
    r"""Convert Markdown links and ``<...>`` to Jira links in linear time.

    Same as ``\[([^\]]+)\]\(([^)]+)\)`` -> ``[\1|\2]`` followed by
    ``<([^>]+)>`` -> ``[\1]``.
    """
    label_end = _NextIndex(text, r"\]")
    target_end = _NextIndex(text, r"\)")

    def convert_link(start: int, _: int) -> tuple[int, int, str] | None:
        close = label_end(start + 1)
        if close == start + 1 or close >= len(text) - 1 or text[close + 1] != "(":
            return None
        end = target_end(close + 2)
        if end == close + 2 or end == len(text):
            return None
        return start, end + 1, f"[{text[start + 1 : close]}|{text[close + 2 : end]}]"

    text = _scan_sub(text, "[", convert_link)
    angle_end = _NextIndex(text, r">")

    def convert_angle(start: int, _: int) -> tuple[int, int, str] | None:
        end = angle_end(start + 1)
        if end == start + 1 or end == len(text):
            return None
        return start, end + 1, f"[{text[start + 1 : end]}]"

    return _scan_sub(text, "<", convert_angle)


_BULLET = re.compile(r"[-+*] ")
_NUMBER = re.compile(r"\d+\. ")


def _sub_list_items(text: str, marker: re.Pattern[str], bullet: str) -> str:
    r"""``re.sub(r"^(\s+)?<marker>(.*)$", ...)`` with MULTILINE, in linear time.

    The optional indent is the whole whitespace run from a line start, which
    may cross blank lines. Every line start inside one run reaches the same
    end, so the regex scanned the run again from each of them. Here the run
    end is looked up once and only the first line start in it can match.
    """
    run_end = _NextIndex(text, r"\S")
    parts: list[str] = []
    copied = line_start = 0
    while line_start <= len(text):
        content = run_end(line_start)
        found = marker.match(text, content) if content < len(text) else None
        if found:
            line_end = text.find("\n", found.end())
            if line_end == -1:
                line_end = len(text)
            level = (content - line_start) // 2 + 1
            parts.append(text[copied:line_start])
            parts.append(bullet * level + " " + text[found.end() : line_end])
            copied = line_end
            line_start = line_end + 1
            continue
        newline = text.find("\n", line_start)
        if newline == -1:
            break
        line_start = newline + 1
    parts.append(text[copied:])
    return "".join(parts)


_EMPHASIS = re.compile(r"([*_]+)(.*?)\1")
_LONG_DELIMITER_RUN = re.compile(r"[*_]{4}")
_DELIMITER = re.compile(r"[*_]")


def _emphasis_to_jira(match: re.Match[str]) -> str:
    mark = "_" if len(match.group(1)) == 1 else "*"
    return mark + match.group(2) + mark


def _convert_emphasis(line: str) -> str:
    r"""``re.sub(r"([*_]+)(.*?)\1", ...)`` on one line, in linear time.

    At each delimiter the pattern takes the longest run prefix that occurs
    again after itself and pairs it with the first such occurrence. The
    regex engine tried every run length against the rest of the line, which
    was cubic in the run length. With runs of at most three delimiters that
    cost stays linear, so the pattern runs as is; longer runs go through a
    suffix automaton that answers "does this prefix occur again later" for
    one prefix length after another.
    """
    if not _LONG_DELIMITER_RUN.search(line):
        return _EMPHASIS.sub(_emphasis_to_jira, line)
    occurrences = _DelimiterOccurrences(line)
    parts: list[str] = []
    copied = pos = 0
    while match := _DELIMITER.search(line, pos):
        start = match.start()
        length = occurrences.longest_repeated_prefix(start)
        if not length:
            pos = start + 1
            continue
        delimiter = line[start : start + length]
        close = _find_from(line, delimiter, start + length)
        mark = "_" if length == 1 else "*"
        parts.append(line[copied:start])
        parts.append(mark + line[start + length : close] + mark)
        copied = pos = close + length
    parts.append(line[copied:])
    return "".join(parts)


def _find_from(text: str, needle: str, pos: int) -> int:
    """Return the first ``needle`` at or after ``pos`` (KMP, linear time)."""
    failure = [0] * len(needle)
    k = 0
    for i in range(1, len(needle)):
        while k and needle[i] != needle[k]:
            k = failure[k - 1]
        if needle[i] == needle[k]:
            k += 1
        failure[i] = k
    k = 0
    for i in range(pos, len(text)):
        while k and text[i] != needle[k]:
            k = failure[k - 1]
        if text[i] == needle[k]:
            k += 1
            if k == len(needle):
                return i - k + 1
    raise ValueError("needle not found")


class _DelimiterOccurrences:
    """Suffix automaton over the "*" and "_" runs of one line.

    Each state records the last position where its strings end, so the
    latest occurrence of any run substring is known in time proportional
    to its length. States live in flat integer arrays, one per symbol for
    the transitions, a few bytes per state instead of a dict.
    """

    def __init__(self, line: str) -> None:
        # Other characters collapse to one separator, which no delimiter
        # string contains; positions map back to the line.
        symbols = bytearray()
        position = array("i")
        for index, char in enumerate(line):
            if char in "*_":
                symbols.append(0 if char == "*" else 1)
                position.append(index)
            elif not symbols or symbols[-1] != 2:
                symbols.append(2)
                position.append(index)
        size = 2 * len(symbols) + 1
        tables = tuple(array("i", [-1]) * size for _ in range(3))
        link = array("i", [-1]) * size
        length = array("i", [0]) * size
        last_end = array("i", [-1]) * size
        states = 1
        last = 0
        for i, symbol in enumerate(symbols):
            nxt = tables[symbol]
            current = states
            states += 1
            length[current] = length[last] + 1
            link[current] = 0
            last_end[current] = i
            state = last
            while state != -1 and nxt[state] == -1:
                nxt[state] = current
                state = link[state]
            if state != -1:
                target = nxt[state]
                if length[state] + 1 == length[target]:
                    link[current] = target
                else:
                    clone = states
                    states += 1
                    for table in tables:
                        table[clone] = table[target]
                    length[clone] = length[state] + 1
                    link[clone] = link[target]
                    while state != -1 and nxt[state] == target:
                        nxt[state] = clone
                        state = link[state]
                    link[target] = clone
                    link[current] = clone
            last = current
        # Longer states first, by counting sort, so each end reaches its link.
        count = array("i", [0]) * (len(symbols) + 2)
        for state in range(states):
            count[length[state] + 1] += 1
        for index in range(1, len(count)):
            count[index] += count[index - 1]
        order = array("i", [0]) * states
        for state in range(states):
            order[count[length[state]]] = state
            count[length[state]] += 1
        for index in range(states - 1, 0, -1):
            state = order[index]
            parent = link[state]
            if last_end[state] > last_end[parent]:
                last_end[parent] = last_end[state]
        self.symbols = symbols
        self.position = position
        self.tables = tables
        self.last_end = last_end

    def longest_repeated_prefix(self, start: int) -> int:
        """Longest k with ``line[start:start+k]`` again at or after start+k.

        The prefix comes from the delimiter run at ``start``. A prefix that
        occurs again after itself has every shorter prefix doing so too, so
        the walk stops at the first one that does not.
        """
        state = 0
        best = 0
        i = bisect.bisect_left(self.position, start)
        while i < len(self.symbols) and self.symbols[i] != 2:
            state = self.tables[self.symbols[i]][state]
            size = best + 1
            last_start = self.position[self.last_end[state]] - size + 1
            if last_start < start + size:
                break
            best = size
            i += 1
        return best


class JiraPreprocessor(BasePreprocessor):
    """Handles text preprocessing for Jira content."""

    # Step 1: Jira Server/Data Center source-code formatter tags.
    # Keep this set to tags the Jira wiki renderer accepts directly.
    VALID_JIRA_LANGUAGES = {
        "actionscript",
        "ada",
        "applescript",
        "bash",
        "c",
        "c#",
        "c++",
        "cpp",
        "css",
        "erlang",
        "go",
        "groovy",
        "haskell",
        "html",
        "java",
        "javascript",
        "js",
        "json",
        "lua",
        "none",
        "nyan",
        "objc",
        "perl",
        "php",
        "python",
        "r",
        "rainbow",
        "ruby",
        "scala",
        "sh",
        "sql",
        "swift",
        "visualbasic",
        "xml",
        "yaml",
    }

    # Step 2: Mapping for unsupported languages to closest valid JIRA alternative
    # Only map to actual JIRA languages; unmapped languages will return None → {code}
    LANGUAGE_MAPPING = {
        # Common aliases for Jira-supported formatters
        "actionscript3": "actionscript",
        "csharp": "c#",
        "cs": "c#",
        "erl": "erlang",
        "objective-c": "objc",
        "py": "python",
        "rb": "ruby",
        "vb": "visualbasic",
        "yml": "yaml",
        # Related formats without their own Jira formatter
        "diff": "none",
        "patch": "none",
        "less": "css",
        "sass": "css",
        "powershell": "bash",
        "ps1": "bash",
        # Dockerfile → bash (similar shell syntax)
        "dockerfile": "bash",
        "docker": "bash",
        # TypeScript → javascript
        "typescript": "javascript",
        "ts": "javascript",
        "tsx": "javascript",
        # JSX/React → javascript
        "jsx": "javascript",
        # Kotlin → java (JVM-based language)
        "kotlin": "java",
        "kt": "java",
        # Build files → bash
        "makefile": "bash",
        "make": "bash",
        "cmake": "bash",
    }

    def __init__(
        self, base_url: str = "", disable_translation: bool = False, **kwargs: Any
    ) -> None:
        """
        Initialize the Jira text preprocessor.

        Args:
            base_url: Base URL for Jira API
            disable_translation: If True, disable markup translation between formats
            **kwargs: Additional arguments for the base class
        """
        super().__init__(base_url=base_url, **kwargs)
        self.disable_translation = disable_translation

    def clean_jira_text(self, text: str) -> str:
        """
        Clean Jira text content by:
        1. Processing user mentions and links
        2. Converting Jira markup to markdown (if translation enabled)
        3. Converting HTML/wiki markup to markdown (if translation enabled)
        """
        if not text:
            return ""

        # Process user mentions
        text = self._process_mentions(text)

        # Process Jira smart links
        text = self._process_smart_links(text)

        # Convert markup only if translation is enabled
        if not self.disable_translation:
            # First convert any Jira markup to Markdown
            text = self.jira_to_markdown(text)

            # Then convert any remaining HTML to markdown
            text = self._convert_html_to_markdown(text)

        return text.strip()

    def _process_mentions(self, text: str, pattern: str | None = None) -> str:
        """
        Process user mentions in text.

        Args:
            text: The text containing mentions
            pattern: Optional regular expression for mentions; the default
                ``[~accountid:...]`` form is matched in linear time

        Returns:
            Text with mentions replaced with display names
        """
        # Note: This is a placeholder - actual user fetching should be injected.
        # One substitution pass; replacing each mention separately rescanned
        # the whole text once per mention.
        if pattern is None:
            return _sub_mentions(text)
        return re.sub(pattern, lambda match: f"User:{match.group(1)}", text)

    def _process_smart_links(self, text: str) -> str:
        """Process Jira/Confluence smart links."""

        # Matches [text|url|smart-link]; see _sub_smart_links.
        def _convert(link_text: str, link_url: str) -> str:
            # Extract issue key if it's a Jira issue link
            issue_key_match = re.search(
                rf"browse/({_ISSUE_KEY_PATTERN})(?=$|[/?#])", link_url
            )
            # Check if it's a Confluence wiki link
            url_title = _confluence_page_title(link_url)

            if issue_key_match:
                issue_key = issue_key_match.group(1)
                clean_url = f"{self.base_url}/browse/{issue_key}"
                return f"[{issue_key}]({clean_url})"
            if url_title is not None:
                readable_title = url_title.replace("+", " ")
                readable_title = re.sub(
                    rf"^{_ISSUE_KEY_PATTERN}\s+", "", readable_title
                )
                return f"[{readable_title}]({link_url})"
            clean_url = link_url.split("?")[0]
            return f"[{link_text}]({clean_url})"

        return _sub_smart_links(text, _convert)

    def jira_to_markdown(self, input_text: str) -> str:
        """
        Convert Jira markup to Markdown format.

        Args:
            input_text: Text in Jira markup format

        Returns:
            Text in Markdown format (or original text if translation disabled)
        """
        if not input_text:
            return ""

        if self.disable_translation:
            return input_text

        output = input_text

        # Protect code/noformat/inline-code blocks from downstream
        # transformations by replacing them with placeholders.
        #
        # Trade-off: when {quote} wraps a {code} block, the code
        # content is extracted *before* the {quote} handler runs.
        # The {quote} handler prefixes each remaining line with
        # "> " but cannot reach inside the already-extracted block.
        # After restoration the opening fence line may carry "> "
        # while inner code lines do not, breaking blockquote
        # continuity.  This is intentional: protecting code content
        # from markup corruption is more important than preserving
        # blockquote indentation around code fences.
        code_blocks: list[str] = []
        inline_codes: list[str] = []

        def _jira_code_to_md(match: re.Match[str]) -> str:
            lang = match.group(1) or ""
            content = match.group(2)
            return f"```{lang}\n{content}\n```"

        code_end = output.rfind("{code}")
        if code_end != -1:
            # Stop at the last closer so an unclosed {code:x} opener cannot
            # scan to the end once per opener (see _sub_up_to_last).
            code_end += len("{code}")
            output = (
                _extract_blocks(
                    output[:code_end],
                    r"\{code(?::([a-z]+))?\}([\s\S]*?)\{code\}",
                    _jira_code_to_md,
                    code_blocks,
                    "CODEBLOCK",
                    flags=re.MULTILINE,
                )
                + output[code_end:]
            )
        output = _extract_blocks(
            output,
            r"\{noformat\}([\s\S]*?)\{noformat\}",
            lambda m: f"```\n{m.group(1)}\n```",
            code_blocks,
            "CODEBLOCK",
        )
        output = _extract_inline_code(output, inline_codes)

        # Block quotes
        output = re.sub(r"^bq\.(.*?)$", r"> \1\n", output, flags=re.MULTILINE)

        # Convert list markers before emphasis so leading asterisks do not
        # pair with bold delimiters or get counted as extra nesting (#1651).
        output = re.sub(
            r"^((?:#|-|\+|\*)+) (.*)$",
            lambda match: self._convert_jira_list_to_markdown(match),
            output,
            flags=re.MULTILINE,
        )

        # Text formatting (bold, italic). Delimiters preceded by a backslash
        # are wiki escapes (e.g. the intraword `\_` this module's
        # markdown_to_jira writes), not markup, so they must neither open nor
        # close a span.
        output = re.sub(
            r"(?<!\\)([*_])(.*?)(?<!\\)\1",
            lambda match: (
                ("**" if match.group(1) == "*" else "*")
                + match.group(2)
                + ("**" if match.group(1) == "*" else "*")
            ),
            output,
        )

        # Headers
        output = re.sub(
            r"^h([0-6])\.(.*)$",
            lambda match: "#" * int(match.group(1)) + match.group(2),
            output,
            flags=re.MULTILINE,
        )

        # Citation (non-overlapping alternation to avoid catastrophic backtracking)
        output = re.sub(
            r"\?\?([^?]+(?:\?[^?]+)*)\?\?",
            r"<cite>\1</cite>",
            output,
        )

        # Inserted text
        output = re.sub(r"\+([^+]*)\+", r"<ins>\1</ins>", output)

        # Superscript
        output = re.sub(r"\^([^^]*)\^", r"<sup>\1</sup>", output)

        # Subscript
        output = re.sub(r"~([^~]*)~", r"<sub>\1</sub>", output)

        # Strikethrough
        output = re.sub(r"-([^-]*)-", r"-\1-", output)

        # Quote blocks
        output = re.sub(
            r"\{quote\}([\s\S]*)\{quote\}",
            lambda match: "\n".join(
                [f"> {line}" for line in match.group(1).split("\n")]
            ),
            output,
            flags=re.MULTILINE,
        )

        # Panel blocks - extract content, optionally show title as bold
        output = _sub_panels(output)

        # Images with alt text, then images with other parameters (ignore them)
        output = _sub_images_with_params(output, with_alt=True)
        output = _sub_images_with_params(output, with_alt=False)

        # Images without parameters
        output = re.sub(r"!([^\n\s!]+)!", r"![](\1)", output)

        # Links
        output = _sub_wiki_links(output)
        output = _sub_bracketed_text(output)

        # Colored text
        output = _sub_colors(output)

        # Convert Jira table headers (||) to markdown table format
        # The output list grows in order; inserting each separator into the
        # middle of the line list was quadratic.
        lines = []
        for line in output.split("\n"):
            if "||" not in line:
                lines.append(line)
                continue
            # Replace Jira table headers
            line = line.replace("||", "|")
            lines.append(line)

            # Add a separator line for markdown tables
            header_cells = line.count("|") - 1
            if header_cells > 0:
                lines.append("|" + "---|" * header_cells)

        # Rejoin the lines
        output = "\n".join(lines)

        # Restore code/noformat blocks and inline code
        output = _restore_blocks(output, code_blocks, "CODEBLOCK")
        output = _restore_blocks(output, inline_codes, "INLINECODE")

        return output

    def _normalize_code_language(self, lang: str | None) -> str | None:
        """
        Normalize and map markdown code language to JIRA-supported language.

        Step 3: Default handling - unmapped languages return None for plain {code}

        Args:
            lang: Language identifier from markdown code block

        Returns:
            Valid JIRA language string, or None for plain {code} block
        """
        if not lang:
            return None

        lang_lower = lang.lower()

        # Step 1: Check if already valid JIRA language
        if lang_lower in self.VALID_JIRA_LANGUAGES:
            return lang_lower

        # Step 2: Check language mapping
        if lang_lower in self.LANGUAGE_MAPPING:
            return self.LANGUAGE_MAPPING[lang_lower]

        # Step 3: Default - unmapped language returns None for plain {code}
        return None

    def markdown_to_jira(self, input_text: str) -> str:
        """
        Convert Markdown syntax to Jira markup syntax.

        Args:
            input_text: Text in Markdown format

        Returns:
            Text in Jira markup format (or original text if translation disabled)
        """
        if not input_text:
            return ""

        if self.disable_translation:
            return input_text

        code_blocks: list[str] = []
        inline_codes: list[str] = []

        def _md_code_to_jira(match: re.Match[str]) -> str:
            syntax = match.group(1) or ""
            content = match.group(2)
            jira_lang = self._normalize_code_language(syntax)
            code = "{code"
            if jira_lang:
                code += ":" + jira_lang
            code += "}\n" + content + "{code}"
            return code

        def _md_inline_to_jira(
            match: re.Match[str],
        ) -> str:
            return "{{" + match.group(1) + "}}"

        # Extract code blocks and inline code before
        # any other transformations.
        output = _extract_blocks(
            input_text,
            r"```([\w#+.-]*)\n([\s\S]+?)```",
            _md_code_to_jira,
            code_blocks,
            "CODEBLOCK",
        )
        output = _extract_blocks(
            output,
            r"`([^`]+)`",
            _md_inline_to_jira,
            inline_codes,
            "INLINECODE",
        )

        # Headers with = or - underlines. A setext heading needs actual text on
        # the line above the underline, so the lookahead keeps a blank line from
        # matching: `\n\n----\n` is a horizontal rule, which is already valid
        # Jira markup, not an empty `h2.` (issue #1587).
        output = re.sub(
            r"^(?=[^\n]*\S)(.*?)\n([=-])+$",
            lambda match: f"h{1 if match.group(2)[0] == '=' else 2}. {match.group(1)}",
            output,
            flags=re.MULTILINE,
        )

        # Headers with # prefix - require space after #
        # to distinguish from Jira lists (issue #786)
        output = re.sub(
            r"^([#]+) (.*)$",
            lambda match: f"h{len(match.group(1))}. " + match.group(2),
            output,
            flags=re.MULTILINE,
        )

        markdown_url_targets: list[str] = []

        def store_markdown_url_target(target: str) -> str:
            placeholder = f"\x00MARKDOWNURL{len(markdown_url_targets)}\x00"
            markdown_url_targets.append(target)
            return placeholder

        def protect_markdown_link_target(match: re.Match[str]) -> str:
            return (
                match.group(1)
                + store_markdown_url_target(match.group(2))
                + match.group(3)
            )

        def protect_markdown_autolink_target(match: re.Match[str]) -> str:
            return "<" + store_markdown_url_target(match.group(1)) + ">"

        output = _protect_markdown_link_targets(output, store_markdown_url_target)
        output = _protect_markdown_autolinks(output, store_markdown_url_target)

        # Bold and italic - skip lines starting with
        # asterisks+space (Jira list syntax, issue #786)
        def escape_intraword_underscore_runs(match: re.Match[str]) -> str:
            return r"\_" * len(match.group(0))

        def convert_bold_italic_line(line: str) -> str:
            # CommonMark treats underscores between two word characters as
            # literal text, not emphasis. The Jira wiki renderer does not:
            # it italicizes any ``_word_`` span, so identifiers such as
            # snake_case, customfield_10101 or foo_bar_baz would render with
            # spurious italics (and adjacent identifiers can pair into a
            # cross-token italic span). Escape intraword underscore runs as
            # ``\_`` so Jira renders them literally; genuine word-boundary
            # ``_emphasis_``/``__strong__`` is left intact for conversion below.
            line = re.sub(
                r"(?<=[^\W_])_+(?=[^\W_])",
                escape_intraword_underscore_runs,
                line,
            )
            if re.match(r"^[*_]+\s", line):
                return line
            return _convert_emphasis(line)

        lines = output.split("\n")
        output = "\n".join(convert_bold_italic_line(line) for line in lines)
        output = _restore_blocks(output, markdown_url_targets, "MARKDOWNURL")

        # Multi-level bulleted and numbered lists
        output = _sub_list_items(output, _BULLET, "*")
        output = _sub_list_items(output, _NUMBER, "#")

        # HTML formatting tags to Jira markup
        tag_map = {
            "cite": "??",
            "del": "-",
            "ins": "+",
            "sup": "^",
            "sub": "~",
        }

        for tag, replacement in tag_map.items():
            output = _sub_html_tag(output, tag, replacement)

        # Colored text
        output = _sub_up_to_last(
            r"<span style=\"color:(#[^\"]+)\">"
            r"([\s\S]*?)</span>",
            r"{color:\1}\2{color}",
            output,
            "</span>",
            flags=re.MULTILINE,
        )

        # Strikethrough
        output = re.sub(r"~~(.*?)~~", r"-\1-", output)

        # Images, then links
        output = _sub_markdown_images(output)
        output = _sub_markdown_links(output)

        # Convert markdown tables to Jira table format
        # Issue #1343: parse full table blocks (header + separator + data rows),
        # strip whitespace from each cell, convert header to ||cell|| and data
        # rows to |cell|.
        # The output list grows in order; popping each separator out of the
        # middle of the line list was quadratic.
        source = output.split("\n")
        lines = []
        i = 0
        while i < len(source):
            # Look for a header row followed by a markdown separator line
            if (
                i < len(source) - 1
                and re.match(r"^\|[-\s|:]+\|$", source[i + 1])
                and re.match(r"^\|.*\|$", source[i])
            ):
                # Header row; the separator is dropped
                header_cells = [cell.strip() for cell in source[i].split("|")[1:-1]]
                lines.append("||" + "||".join(header_cells) + "||")
                i += 2

                # Consume data rows while they look like table rows
                while i < len(source) and re.match(r"^\|.*\|$", source[i]):
                    data_cells = [cell.strip() for cell in source[i].split("|")[1:-1]]
                    lines.append("|" + "|".join(data_cells) + "|")
                    i += 1
                continue
            lines.append(source[i])
            i += 1

        # Rejoin the lines
        output = "\n".join(lines)

        # Restore code blocks and inline code
        output = _restore_blocks(output, code_blocks, "CODEBLOCK")
        output = _restore_blocks(output, inline_codes, "INLINECODE")

        return output

    def _convert_jira_list_to_markdown(self, match: re.Match) -> str:
        """
        Helper method to convert Jira lists to Markdown format.

        Args:
            match: Regex match object containing the Jira list markup

        Returns:
            Markdown-formatted list item
        """
        jira_bullets = match.group(1)
        content = match.group(2)

        # Calculate indentation level based on number of symbols
        indent_level = len(jira_bullets) - 1
        indent = " " * (indent_level * 2)

        # Determine the marker based on the last character
        last_char = jira_bullets[-1]
        prefix = "1." if last_char == "#" else "-"

        return f"{indent}{prefix} {content}"
