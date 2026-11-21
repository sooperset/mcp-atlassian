"""Base preprocessing module."""

import bisect
import contextvars
import functools
import logging
import re
import urllib.parse
import warnings
from collections.abc import Callable, Iterator
from typing import Any, ParamSpec, Protocol, TypeVar

from bs4 import BeautifulSoup, NavigableString, PageElement, Tag
from markdownify import MarkdownConverter

logger = logging.getLogger("mcp-atlassian")

_P = ParamSpec("_P")
_R = TypeVar("_R")

# Every substring shaped like a code-macro placeholder. The lookahead keeps
# matches that share a NUL boundary with their neighbour.
_PLACEHOLDER_SHAPED = re.compile("(?=(\x00MCPCODEMACRO[0-9]+\x00))")

_QUOTED_MACROS = frozenset({"panel", "info", "note", "warning", "tip"})
_RESOURCE_ATTRS = (
    ("ri:page", "ri:content-title"),
    ("ri:attachment", "ri:filename"),
    ("ri:url", "ri:value"),
    ("ri:space", "ri:space-key"),
)


class _MarkdownConverter(MarkdownConverter):
    """markdownify converter whose list and table numbering stays linear.

    markdownify numbers each ordered-list item by counting its previous
    siblings and checks every header row by listing all rows of its
    ``thead``. Both scans repeat for every item, so long lists and tables
    took quadratic time. This converter computes each count once per parent
    element; the output is the same.
    """

    options: dict[str, Any]

    def __init__(self, **options: Any) -> None:
        super().__init__(**options)
        self._li_positions: dict[int, dict[int, int]] = {}
        self._tr_counts: dict[int, int] = {}

    def _li_position(self, parent: Tag, item: Tag) -> int:
        positions = self._li_positions.get(id(parent))
        if positions is None:
            positions = {}
            for child in parent.children:
                if isinstance(child, Tag) and child.name == "li":
                    positions[id(child)] = len(positions)
            self._li_positions[id(parent)] = positions
        return positions[id(item)]

    def _tr_count(self, parent: Tag) -> int:
        count = self._tr_counts.get(id(parent))
        if count is None:
            count = len(parent.find_all("tr"))
            self._tr_counts[id(parent)] = count
        return count

    def convert_li(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        parent = el.parent
        if parent is None or parent.name != "ol":
            return str(super().convert_li(el, text, parent_tags))

        text = (text or "").strip()
        if not text:
            return "\n"
        start_attr = parent.get("start")
        if start_attr and str(start_attr).isnumeric():
            start = int(str(start_attr))
        else:
            start = 1
        bullet = f"{start + self._li_position(parent, el)}. "
        bullet_width = len(bullet)
        bullet_indent = " " * bullet_width

        def _indent_for_li(match: re.Match[str]) -> str:
            line_content = match.group(1)
            return bullet_indent + line_content if line_content else ""

        text = re.sub(r"^(.*)", _indent_for_li, text, flags=re.MULTILINE)
        return f"{bullet}{text[bullet_width:]}\n"

    def convert_tr(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        parent = el.parent
        cells = el.find_all(["td", "th"])
        is_first_row = el.find_previous_sibling() is None
        is_headrow = all(cell.name == "th" for cell in cells) or (
            parent is not None
            and parent.name == "thead"
            and self._tr_count(parent) == 1
        )
        parent_name = parent.name if parent is not None else None
        grandparent = parent.parent if parent is not None else None
        is_head_row_missing = (is_first_row and parent_name != "tbody") or (
            is_first_row
            and parent_name == "tbody"
            and grandparent is not None
            and len(grandparent.find_all(["thead"])) < 1
        )
        overline = ""
        underline = ""
        full_colspan = 0
        for cell in cells:
            colspan = cell.attrs.get("colspan")
            if isinstance(colspan, str) and colspan.isdigit():
                full_colspan += max(1, min(1000, int(colspan)))
            else:
                full_colspan += 1
        if (
            is_headrow or (is_head_row_missing and self.options["table_infer_header"])
        ) and is_first_row:
            underline += "| " + " | ".join(["---"] * full_colspan) + " |" + "\n"
        elif (is_head_row_missing and not self.options["table_infer_header"]) or (
            is_first_row
            and (
                parent_name == "table"
                or (
                    parent_name == "tbody"
                    and parent is not None
                    and not parent.find_previous_sibling()
                )
            )
        ):
            overline += "| " + " | ".join([""] * full_colspan) + " |" + "\n"
            overline += "| " + " | ".join(["---"] * full_colspan) + " |" + "\n"
        return overline + "|" + text + "\n" + underline


def md(html: str, **options: Any) -> str:
    """Convert HTML to Markdown with markdownify options."""
    return str(_MarkdownConverter(**options).convert(html))


# Child positions per parent, kept while a soup pass replaces elements.
_SIBLING_POSITIONS: contextvars.ContextVar[
    dict[int, tuple[Tag, dict[int, int]]] | None
] = contextvars.ContextVar("mcp_atlassian_sibling_positions", default=None)


def _replace_with(element: PageElement, *nodes: PageElement | str) -> None:
    """Replace ``element`` like ``element.replace_with(*nodes)``.

    bs4 finds the element's position by scanning its parent's children, so
    replacing many siblings one after another was quadratic. While
    process_html_content runs, positions are computed once per parent and
    reused; a position that no longer holds the element is recomputed. The
    passes replace one element with one node, or go from the last sibling to
    the first, so earlier positions stay valid. Outside a pass marked with
    ``_keeps_sibling_positions`` this is plain ``replace_with``.
    """
    positions = _SIBLING_POSITIONS.get()
    parent = element.parent
    if positions is None or parent is None:
        element.replace_with(*nodes)
        return
    index: int | None = None
    entry = positions.get(id(parent))
    if entry is not None and entry[0] is parent:
        index = entry[1].get(id(element))
        if index is not None and (
            index >= len(parent.contents) or parent.contents[index] is not element
        ):
            index = None
    if index is None:
        mapping = {id(child): i for i, child in enumerate(parent.contents)}
        positions[id(parent)] = (parent, mapping)
        index = mapping[id(element)]
    element.extract(_self_index=index)
    for offset, node in enumerate(nodes):
        parent.insert(index + offset, node)


def _keeps_sibling_positions(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """Let ``_replace_with`` reuse child positions while ``function`` runs."""

    @functools.wraps(function)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        if _SIBLING_POSITIONS.get() is not None:
            return function(*args, **kwargs)
        token = _SIBLING_POSITIONS.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _SIBLING_POSITIONS.reset(token)

    return wrapper


def _macro_placeholder(name: str, macro: Tag, params: dict[str, str]) -> str:
    if name == "jira" and params.get("key"):
        return f"[{params['key']}]"
    for param_name in ("key", "jqlQuery", "jql", "url"):
        if value := params.get(param_name):
            return f"[{name}: {value}]"
    for tag_name, attr_name in _RESOURCE_ATTRS:
        ref = macro.find(tag_name)
        if isinstance(ref, Tag) and (value := str(ref.get(attr_name, "")).strip()):
            return f"[{name}: {value}]"
    return f"[{name} macro]"


def _extract_blocks(
    text: str,
    pattern: str,
    transform_fn: Callable[[re.Match[str]], str],
    storage: list[str],
    prefix: str,
    flags: int = 0,
) -> str:
    """Extract blocks matching pattern, transform, store, and replace with placeholders.

    Args:
        text: Input text to process.
        pattern: Regex pattern to match blocks.
        transform_fn: Function to transform the match into the target format.
        storage: List to store transformed blocks.
        prefix: Placeholder prefix (e.g., "CODEBLOCK").
        flags: Regex flags to pass to ``re.sub``.

    Returns:
        Text with blocks replaced by placeholders.
    """

    def _replacer(match: re.Match[str]) -> str:
        transformed = transform_fn(match)
        placeholder = f"\x00{prefix}{len(storage)}\x00"
        storage.append(transformed)
        return placeholder

    return re.sub(pattern, _replacer, text, flags=flags)


def _restore_blocks(text: str, storage: list[str], prefix: str) -> str:
    """Restore blocks from placeholders.

    Replaces in reverse order (highest index first) to avoid
    index collisions when placeholder text contains digits.

    Args:
        text: Text with placeholders.
        storage: List of stored blocks.
        prefix: Placeholder prefix used during extraction.

    Returns:
        Text with placeholders replaced by stored blocks.
    """
    if not storage:
        return text
    pattern = re.compile(f"\x00{re.escape(prefix)}([0-9]+)\x00")
    max_digits = len(str(len(storage) - 1))
    expanded: list[str] = []

    def _index(match: re.Match[str], limit: int) -> int | None:
        digits = match.group(1)
        if len(digits) > max_digits or digits != str(int(digits)):
            return None
        index = int(digits)
        return index if index < limit else None

    # Restoring from the highest index down let a block take in the blocks
    # stored before it; expanding each block once in storage order keeps that,
    # and the text is then restored in a single pass instead of once per block.
    for limit, block in enumerate(storage):
        if "\x00" in block:
            block = pattern.sub(
                lambda m, limit=limit: (
                    m.group(0) if (i := _index(m, limit)) is None else expanded[i]
                ),
                block,
            )
        expanded.append(block)

    return pattern.sub(
        lambda m: (
            m.group(0) if (i := _index(m, len(expanded))) is None else expanded[i]
        ),
        text,
    )


class _TreeIndex:
    """Document-order positions of the tags under ``root``, from one walk.

    ``first(element, kind)`` returns what ``element.find(...)`` returned for
    that kind of tag on the tree as it was when the index was built, by a
    binary search instead of a walk over the element's subtree; nested
    elements made those walks quadratic. ``inside(element)`` tells whether
    an element lies inside the subtree of an element passed to ``skip``.
    """

    def __init__(self, root: Tag, kinds: dict[str, Callable[[Tag], bool]]) -> None:
        self._span: dict[int, tuple[int, int]] = {}
        self._kinds: dict[str, tuple[list[int], list[Tag]]] = {
            kind: ([], []) for kind in kinds
        }
        self._skip_until = -1
        counter = 0
        enter = {id(root): 0}
        stack = [(root, iter(root.contents))]
        while stack:
            node, children = stack[-1]
            for child in children:
                if isinstance(child, Tag):
                    counter += 1
                    enter[id(child)] = counter
                    for kind, matches in kinds.items():
                        if matches(child):
                            positions, tags = self._kinds[kind]
                            positions.append(counter)
                            tags.append(child)
                    stack.append((child, iter(child.contents)))
                    break
            else:
                self._span[id(node)] = (enter[id(node)], counter)
                stack.pop()

    def first(self, element: Tag, kind: str) -> Tag | None:
        """Return the first ``kind`` tag below ``element`` in document order."""
        start, end = self._span[id(element)]
        positions, tags = self._kinds[kind]
        index = bisect.bisect_right(positions, start)
        if index < len(positions) and positions[index] <= end:
            return tags[index]
        return None

    def skip(self, element: Tag) -> None:
        """Mark ``element``'s subtree as replaced."""
        self._skip_until = max(self._skip_until, self._span[id(element)][1])

    def inside(self, element: Tag) -> bool:
        """Return whether ``element`` lies in a subtree marked by ``skip``."""
        return self._span[id(element)][0] <= self._skip_until


def _named(name: str, **attrs: str) -> Callable[[Tag], bool]:
    def matches(tag: Tag) -> bool:
        return tag.name == name and all(tag.get(k) == v for k, v in attrs.items())

    return matches


def _contains_html_tag(text: str) -> bool:
    """Return whether ``re.search(r"<[^>]+>", text)`` would match.

    That search rescans the rest of the text from every "<" that is never
    closed, which is quadratic. A match needs a "<" before a ">" with at
    least one character between them and no ">" in between, so it is enough
    to look inside each piece that a ">" ends.
    """
    return any("<" in piece[:-1] for piece in text.split(">")[:-1])


def _code_language_from_element(el: Tag) -> str:
    """Extract a language-* class from a pre element or its code child."""
    for candidate in (el, el.find("code")):
        if candidate is None or isinstance(candidate, str):
            continue
        classes = candidate.get("class") or []
        for cls in classes:
            if cls.startswith("language-"):
                return cls.removeprefix("language-")
    return ""


def _fenced_code_block(code_text: str, language: str) -> str:
    """Wrap code text in a fence that cannot occur in the code body."""
    longest_backtick_run = max(
        (len(run) for run in re.findall(r"`+", code_text)),
        default=0,
    )
    fence = "`" * max(3, longest_backtick_run + 1)
    closing_newline = "" if code_text.endswith(("\n", "\r")) else "\n"
    return f"{fence}{language}\n{code_text}{closing_newline}{fence}"


def _prefix_code_block(code_block: str, prefix: str) -> str:
    """Add a Markdown container prefix to every line in a code block."""
    return re.sub(
        r"\r\n|\r|\n",
        lambda match: f"{match.group()}{prefix}",
        code_block,
    )


_LINE_TEXT = re.compile(r"\S|\n")
_SPACES_AND_BACKTICKS = re.compile(r"[ \t`]*")
_SPAN_CLOSING = re.compile(r"[ \t]*`+")


class _RightToLeftText:
    """Text rewritten from right to left without copying it per edit.

    The current text is the untouched original up to ``head_end`` followed by
    the rewritten tail, kept as pieces. Every edit starts inside the
    untouched part, so positions there stay original positions. Reads walk
    only as far as they need into the tail.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.head_end = len(text)
        # Tail pieces, leftmost last, each with the offset where it starts.
        self._pieces: list[tuple[str, int]] = []
        self._tail_length = 0

    def __len__(self) -> int:
        return self.head_end + self._tail_length

    def _chunks(self, pos: int) -> Iterator[tuple[str, int, int, int]]:
        """Yield ``(string, start, end, position)`` pieces from ``pos`` on."""
        if pos < self.head_end:
            yield self.text, pos, self.head_end, pos
            skip = 0
        else:
            skip = pos - self.head_end
        position = max(pos, self.head_end)
        for piece, offset in reversed(self._pieces):
            size = len(piece) - offset
            if skip >= size:
                skip -= size
                continue
            yield piece, offset + skip, len(piece), position
            position += size - skip
            skip = 0

    def find_newline(self, pos: int) -> int:
        """Return the position of the first newline at or after ``pos``."""
        for chunk, start, end, position in self._chunks(pos):
            index = chunk.find("\n", start, end)
            if index != -1:
                return position + index - start
        return -1

    def slice(self, start: int, end: int) -> str:
        """Return the current text from ``start`` to ``end``."""
        parts: list[str] = []
        remaining = end - start
        for chunk, chunk_start, chunk_end, _ in self._chunks(start):
            if remaining <= 0:
                break
            take = min(remaining, chunk_end - chunk_start)
            parts.append(chunk[chunk_start : chunk_start + take])
            remaining -= take
        return "".join(parts)

    def line_has_text(self, pos: int) -> bool:
        """Return whether the line holds non-whitespace from ``pos`` on."""
        for chunk, start, end, _ in self._chunks(pos):
            match = _LINE_TEXT.search(chunk, start, end)
            if match:
                return match.group() != "\n"
        return False

    def span_closing_length(self, pos: int) -> int | None:
        """Return the length of ``[ \\t]*`+`` matched at ``pos``, if any."""
        parts: list[str] = []
        for chunk, start, end, _ in self._chunks(pos):
            # The pattern matches the empty string, so it always matches.
            match = _SPACES_AND_BACKTICKS.match(chunk, start, end)
            run_end = match.end() if match else start
            parts.append(chunk[start:run_end])
            if run_end < end:
                break
        closing = _SPAN_CLOSING.match("".join(parts))
        return closing.end() if closing else None

    def replace(self, start: int, end: int, replacement: str) -> None:
        """Replace the current text from ``start`` (untouched) to ``end``."""
        if end <= self.head_end:
            if end < self.head_end:
                self._push(self.text[end : self.head_end])
        else:
            self._drop(end - self.head_end)
        self.head_end = start
        self._push(replacement)

    def _push(self, piece: str) -> None:
        if piece:
            self._pieces.append((piece, 0))
            self._tail_length += len(piece)

    def _drop(self, count: int) -> None:
        self._tail_length -= count
        while count:
            piece, offset = self._pieces.pop()
            size = len(piece) - offset
            if count < size:
                self._pieces.append((piece, offset + count))
                return
            count -= size

    def result(self) -> str:
        """Return the whole current text."""
        tail = [piece[offset:] for piece, offset in reversed(self._pieces)]
        return self.text[: self.head_end] + "".join(tail)


class _CodeMacroRestorer:
    """Replace code-macro placeholders in markdownify output, right to left.

    Each placeholder is restored from the fence context markdownify left
    around it: a block fence on the lines before and after, or an inline
    backtick span inside a table cell. Placeholders are handled from the last
    one to the first, as the placeholder-by-placeholder version did, but the
    text is rewritten in place and line and backtick positions are looked up
    in indexes built once, so each placeholder costs only its own context.
    """

    def __init__(self, markdown_text: str) -> None:
        self.doc = _RightToLeftText(markdown_text)
        self.newlines = [m.start() for m in re.finditer("\n", markdown_text)]
        self.carriage_returns = [m.start() for m in re.finditer("\r", markdown_text)]
        runs = [m.span() for m in re.finditer("`+", markdown_text)]
        self.run_starts = [run[0] for run in runs]
        self.run_ends = [run[1] for run in runs]

    def _line_start(self, pos: int) -> int:
        index = bisect.bisect_left(self.newlines, pos)
        return self.newlines[index - 1] + 1 if index else 0

    def restore(self, start: int, placeholder: str, code_block: str) -> None:
        """Restore one placeholder found at original position ``start``."""
        doc = self.doc
        end = start + len(placeholder)
        line_start = self._line_start(start)
        stored = _stored_fence(code_block)

        if doc.line_has_text(end):
            if stored is not None and self._restore_inline(
                start, end, line_start, code_block, *stored
            ):
                return
            doc.replace(start, end, code_block)
            return

        if stored is None or line_start == 0:
            doc.replace(start, end, code_block)
            return
        line_end = doc.find_newline(end)
        if line_end == -1:
            doc.replace(start, end, code_block)
            return
        opening_line_start = self._line_start(line_start - 1)
        opening_line = doc.text[opening_line_start : line_start - 1]
        closing_line_start = line_end + 1
        closing_line_end = doc.find_newline(closing_line_start)
        if closing_line_end == -1:
            closing_line_end = len(doc)
        closing_line = doc.slice(closing_line_start, closing_line_end)

        # Same as re.search(r"`{3,}[^\r\n]*$", opening_line).start() and
        # re.search(r"`{3,}[ \t]*$", closing_line).start(), without the
        # backtracking those patterns do inside a long backtick run.
        opening_fence = opening_line.find("```", opening_line.rfind("\r") + 1)
        closing_text = closing_line.rstrip(" \t")
        closing_fence = len(closing_text.rstrip("`"))
        if opening_fence == -1 or len(closing_text) - closing_fence < 3:
            doc.replace(start, end, code_block)
            return

        fence, opening_end = stored
        body = code_block[opening_end : -len(fence)]
        # The closing line contains only markdownify's continuation prefix and
        # the fence, making it the reliable prefix for every restored body
        # line. The placeholder line can also carry list or quote context, but
        # unlike the closing line it may be adjacent to content in malformed
        # HTML.
        continuation_prefix = closing_line[:closing_fence]
        stored_opening_line = code_block[:opening_end].rstrip("\n")
        restored = (
            f"{stored_opening_line}\n"
            f"{continuation_prefix}{_prefix_code_block(body, continuation_prefix)}"
            f"{fence}"
        )
        # The container prefix before the opening fence stays as it is.
        doc.replace(opening_line_start + opening_fence, closing_line_end, restored)

    def _restore_inline(
        self,
        start: int,
        end: int,
        line_start: int,
        code_block: str,
        fence: str,
        opening_end: int,
    ) -> bool:
        """Restore a code macro that markdownify collapsed into an inline span.

        Inside a table cell markdownify flattens the pre/code wrapper onto the
        row's line as a backtick span, where a multi-line fence would split
        the row. Mirror markdownify's own handling of pre/code in that
        position: collapse the body onto one line inside a span wide enough
        for any backtick run it contains.
        """
        # The opening is the last backtick run on the line before the
        # placeholder, with no line break after it.
        run = bisect.bisect_left(self.run_starts, start) - 1
        if run < 0 or self.run_starts[run] < line_start:
            return False
        returns = bisect.bisect_left(self.carriage_returns, self.run_ends[run])
        if (
            returns < len(self.carriage_returns)
            and self.carriage_returns[returns] < start
        ):
            return False
        closing = self.doc.span_closing_length(end)
        if closing is None:
            return False

        collapsed = code_block[opening_end : -len(fence)].strip("\n").replace("\n", " ")
        longest_backtick_run = max(
            (len(run) for run in re.findall(r"`+", collapsed)),
            default=0,
        )
        delimiter = "`" * max(3, longest_backtick_run + 1)
        self.doc.replace(
            self.run_starts[run],
            end + closing,
            f"{delimiter} {collapsed} {delimiter}",
        )
        return True


def _stored_fence(code_block: str) -> tuple[str, int] | None:
    """Return a stored block's fence and where its opening line ends.

    Same as ``re.match(r"(`+)[^\\r\\n]*\\n", code_block)`` followed by a check
    that the block ends with that fence, without the backtracking.
    """
    fence = code_block[: len(code_block) - len(code_block.lstrip("`"))]
    newline = code_block.find("\n")
    carriage_return = code_block.find("\r", 0, newline)
    if not fence or newline == -1 or carriage_return != -1:
        return None
    if not code_block.endswith(fence):
        return None
    return fence, newline + 1


def _restore_code_macro_blocks(markdown_text: str, code_blocks: dict[str, str]) -> str:
    """Replace code-macro placeholders with fenced blocks in Markdown context."""
    if not code_blocks:
        return markdown_text
    last_position: dict[str, int] = {}
    for match in _PLACEHOLDER_SHAPED.finditer(markdown_text):
        if match.group(1) in code_blocks:
            last_position[match.group(1)] = match.start()

    restorer = _CodeMacroRestorer(markdown_text)
    for placeholder, start in sorted(
        last_position.items(), key=lambda item: item[1], reverse=True
    ):
        # A later placeholder's context can take in text before it; a
        # placeholder in that text was replaced along with it.
        if start + len(placeholder) > restorer.doc.head_end:
            continue
        restorer.restore(start, placeholder, code_blocks[placeholder])
    return restorer.doc.result()


class ConfluenceClient(Protocol):
    """Protocol for Confluence client."""

    def get_user_details_by_accountid(self, account_id: str) -> dict[str, Any]:
        """Get user details by account ID."""
        ...

    def get_user_details_by_username(self, username: str) -> dict[str, Any]:
        """Get user details by username (for Server/DC compatibility)."""
        ...

    def get_user_details_by_userkey(self, userkey: str) -> dict[str, Any]:
        """Get user details by userkey (for Server/DC compatibility)."""
        ...


MAX_USER_LOOKUPS_PER_DOCUMENT = 50


class _DocumentUserLookups:
    """User lookups for one document: one request per distinct user, capped.

    A page can mention the same user many times, or many users. Each distinct
    identifier is looked up once; after ``MAX_USER_LOOKUPS_PER_DOCUMENT``
    distinct lookups the rest get no display name and fall back to the stored
    identifier.
    """

    def __init__(self, client: ConfluenceClient) -> None:
        self._client = client
        self._results: dict[tuple[str, str], dict[str, Any]] = {}

    def _lookup(
        self, kind: str, identifier: str, fetch: Callable[[str], dict[str, Any]]
    ) -> dict[str, Any]:
        key = (kind, identifier)
        if key in self._results:
            return self._results[key]
        if len(self._results) >= MAX_USER_LOOKUPS_PER_DOCUMENT:
            return {}
        try:
            details = fetch(identifier)
        except Exception as e:  # noqa: BLE001 - a failed lookup falls back
            logger.warning(f"Error fetching user details ({kind}): {e}")
            details = {}
        self._results[key] = details if isinstance(details, dict) else {}
        return self._results[key]

    def get_user_details_by_accountid(self, account_id: str) -> dict[str, Any]:
        return self._lookup(
            "accountid", account_id, self._client.get_user_details_by_accountid
        )

    def get_user_details_by_username(self, username: str) -> dict[str, Any]:
        return self._lookup(
            "username", username, self._client.get_user_details_by_username
        )

    def get_user_details_by_userkey(self, userkey: str) -> dict[str, Any]:
        return self._lookup(
            "userkey", userkey, self._client.get_user_details_by_userkey
        )


class BasePreprocessor:
    """Base class for text preprocessing operations."""

    def __init__(self, base_url: str = "") -> None:
        """
        Initialize the base text preprocessor.

        Args:
            base_url: Base URL for API server
        """
        self.base_url = base_url.rstrip("/") if base_url else ""

    def process_html_content(
        self,
        html_content: str,
        space_key: str = "",
        confluence_client: ConfluenceClient | None = None,
        content_id: str = "",
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str]:
        """
        Process HTML content to replace user refs and page links.

        Args:
            html_content: The HTML content to process
            space_key: Optional space key for context
            confluence_client: Optional Confluence client for user lookups
            content_id: Optional page/content ID for attachment URL
                construction
            attachments: Optional list of attachment dicts from
                Confluence API for URL lookup

        Returns:
            Tuple of (processed_html, processed_markdown)
        """
        try:
            # Parse the HTML content
            soup = BeautifulSoup(html_content, "html.parser")

            # Process user mentions (one lookup per distinct user, capped)
            lookups = (
                _DocumentUserLookups(confluence_client)
                if confluence_client is not None
                else None
            )
            self._process_user_mentions_in_soup(soup, lookups)
            self._process_user_profile_macros_in_soup(soup, lookups)

            # Preserve Confluence date lozenges, whose value is stored only in
            # the datetime attribute and would otherwise be dropped by markdownify.
            self._process_date_elements_in_soup(soup)

            # Process Confluence image tags
            self._process_images_in_soup(soup, content_id, attachments)

            # Convert to string before the code-macro rewrite so the HTML
            # output keeps the original storage-format macros intact
            processed_html = str(soup)

            # Convert code-block macros before markdownify strips them
            # (markdown path only). Keep their contents out of markdownify so
            # it cannot shorten their fences or strip boundary newlines, while
            # the pre/code wrapper keeps nested Markdown containers intact.
            code_macro_blocks = self._process_code_macros_in_soup(soup)
            self._process_remaining_macros_in_soup(soup)
            processed_markdown = md(
                str(soup),
                code_language_callback=_code_language_from_element,
            )
            if code_macro_blocks:
                processed_markdown = _restore_code_macro_blocks(
                    processed_markdown, code_macro_blocks
                )

            return processed_html, processed_markdown

        except Exception as e:
            logger.error(f"Error in process_html_content: {str(e)}")
            raise

    @staticmethod
    def _process_code_macros_in_soup(soup: BeautifulSoup) -> dict[str, str]:
        """Convert Confluence code/noformat macros to standard pre/code blocks.

        markdownify does not know the ``ac:structured-macro`` element: it strips
        the tags, leaks the parameter values (language, line numbers) into the
        output as literal text, and collapses the whitespace of the code body.
        Replacing the macro with a ``pre/code`` wrapper containing a placeholder
        lets markdownify establish the surrounding list or blockquote structure
        while the code body is preserved verbatim for restoration afterward.

        Returns:
            Mapping of markdownify-safe placeholders to fenced code blocks.
        """
        code_blocks: dict[str, str] = {}
        # A placeholder has to avoid three things: placeholder-shaped text
        # already in the document, the placeholders handed out so far, and the
        # language names this loop writes back into the document. The document
        # is scanned once for such text instead of being serialized again for
        # every macro, which made pages with many code macros quadratic.
        taken = set(_PLACEHOLDER_SHAPED.findall(str(soup)))
        index = _TreeIndex(
            soup,
            {
                "body": _named("ac:plain-text-body"),
                "language": _named("ac:parameter", **{"ac:name": "language"}),
            },
        )
        for macro in soup.find_all(
            "ac:structured-macro", attrs={"ac:name": ["code", "noformat"]}
        ):
            # A macro inside a converted one was dropped with its body.
            if index.inside(macro):
                continue
            body = index.first(macro, "body")
            if body is None:
                # Without a plain-text body, the macro's child text consists
                # of parameters rather than code. Leave it untouched so
                # potentially meaningful content is not replaced by a bogus
                # code block.
                continue

            # Empty and whitespace-only bodies still convert: leaving the
            # macro in place would leak its parameter values as literal text
            # once markdownify strips the unknown tags.
            code_text = body.get_text()

            language_param = index.first(macro, "language")
            language = language_param.get_text(strip=True) if language_param else ""

            placeholder = f"\x00MCPCODEMACRO{len(code_blocks)}\x00"
            collision = 0
            taken.update(_PLACEHOLDER_SHAPED.findall(language))
            while placeholder in taken:
                collision += 1
                placeholder = f"\x00MCPCODEMACRO{len(code_blocks)}{collision}\x00"

            taken.add(placeholder)
            code_blocks[placeholder] = _fenced_code_block(code_text, language)

            code_tag = soup.new_tag("code")
            if language:
                code_tag["class"] = f"language-{language}"
            code_tag.string = placeholder
            # Turn the macro itself into the pre wrapper. replace_with looks
            # the element up among its siblings, which made many sibling
            # macros quadratic. Its children are detached as a whole, as
            # replace_with detached the macro with them.
            index.skip(macro)
            macro.name = "pre"
            macro.attrs = {}
            macro.clear()
            macro.append(code_tag)

        return code_blocks

    @staticmethod
    @_keeps_sibling_positions
    def _process_remaining_macros_in_soup(soup: BeautifulSoup) -> None:
        """Replace macros without a dedicated handler with their visible text.

        Runs after the code-macro pass, so only macros nobody handled reach
        here. Their ``ac:parameter`` values are configuration (colours, widths,
        flags) and are dropped with the macro. Panels and their info/note/
        warning/tip variants become a blockquote led by the bold ``title``, a
        status becomes ``[title]``, other macros keep their title and body, and
        a bodyless macro keeps its content parameter (such as a Jira issue
        ``key`` or ``ri:*`` target) before falling back to ``[name macro]``.
        Innermost macros go first so nested bodies are already flattened.
        """
        for macro in reversed(soup.find_all("ac:structured-macro")):
            name = str(macro.get("ac:name", "")).lower()
            params: dict[str, str] = {
                str(param.get("ac:name", "")): param.get_text(strip=True)
                for param in macro.find_all("ac:parameter", recursive=False)
            }
            title = params.get("title", "")

            if name == "status":
                _replace_with(macro, f"[{title or 'status'}]")
                continue

            body = macro.find(
                ["ac:rich-text-body", "ac:plain-text-body"], recursive=False
            )
            content: list[Any] = []
            if body is not None and body.name == "ac:plain-text-body":
                if text := body.get_text().strip():
                    content.append(NavigableString(text))
            elif body is not None:
                content = list(body.contents)

            if not title and not content:
                _replace_with(macro, _macro_placeholder(name, macro, params))
                continue

            if title:
                heading = soup.new_tag("p")
                strong = soup.new_tag("strong")
                strong.string = title
                heading.append(strong)
                content.insert(0, heading)

            if name in _QUOTED_MACROS:
                quote = soup.new_tag("blockquote")
                for node in content:
                    quote.append(node)
                _replace_with(macro, quote)
            else:
                _replace_with(macro, *content)
                macro.decompose()

    @staticmethod
    def _process_date_elements_in_soup(soup: BeautifulSoup) -> None:
        """Expose Confluence date-lozenge values as element text."""
        for date_element in soup.find_all("time"):
            datetime_value = date_element.get("datetime")
            if (
                isinstance(datetime_value, str)
                and datetime_value
                and not date_element.get_text(strip=True)
            ):
                date_element.string = datetime_value

    @_keeps_sibling_positions
    def _process_user_mentions_in_soup(
        self, soup: BeautifulSoup, confluence_client: ConfluenceClient | None = None
    ) -> None:
        """
        Process user mentions in BeautifulSoup object.

        Handles both Cloud (ri:account-id) and Server/DC (ri:userkey,
        ri:username) user reference formats.

        Args:
            soup: BeautifulSoup object containing HTML
            confluence_client: Optional Confluence client for user lookups
        """
        # Find all ac:link elements that might contain user mentions
        user_mentions = soup.find_all("ac:link")
        index = _TreeIndex(soup, {"user": _named("ri:user")})

        for user_element in user_mentions:
            # A link inside a replaced one left the page with it.
            if index.inside(user_element):
                continue
            user_ref = index.first(user_element, "user")
            if not user_ref:
                continue

            account_id = user_ref.get("ri:account-id")
            userkey = user_ref.get("ri:userkey")
            username = user_ref.get("ri:username")

            if account_id and isinstance(account_id, str):
                # Cloud: use account-id
                self._replace_user_mention(user_element, account_id, confluence_client)
            elif userkey and isinstance(userkey, str):
                # Server/DC: use userkey (internal key, needs /rest/api/user?key=)
                self._replace_user_mention_by_userkey(
                    user_element, userkey, confluence_client
                )
            elif username and isinstance(username, str):
                # Server/DC fallback: use username
                self._replace_user_mention_by_username(
                    user_element, username, confluence_client
                )
            if user_element.parent is None:
                index.skip(user_element)

    @_keeps_sibling_positions
    def _process_user_profile_macros_in_soup(
        self, soup: BeautifulSoup, confluence_client: ConfluenceClient | None = None
    ) -> None:
        """
        Process Confluence User Profile macros in BeautifulSoup object.
        Replaces <ac:structured-macro ac:name="profile">...</ac:structured-macro>
        with the user's display name, typically formatted as @DisplayName.

        Args:
            soup: BeautifulSoup object containing HTML
            confluence_client: Optional Confluence client for user lookups
        """
        profile_macros = soup.find_all(
            "ac:structured-macro", attrs={"ac:name": "profile"}
        )

        for macro_element in profile_macros:
            user_param = macro_element.find("ac:parameter", attrs={"ac:name": "user"})
            if not user_param:
                logger.debug(
                    "User profile macro found without a 'user' parameter. Replacing with placeholder."
                )
                _replace_with(macro_element, "[User Profile Macro (Malformed)]")
                continue

            user_ref = user_param.find("ri:user")
            if not user_ref:
                logger.debug(
                    "User profile macro's 'user' parameter found without 'ri:user' tag. Replacing with placeholder."
                )
                _replace_with(macro_element, "[User Profile Macro (Malformed)]")
                continue

            account_id = user_ref.get("ri:account-id")
            userkey = user_ref.get("ri:userkey")  # Fallback for Confluence Server/DC
            username = user_ref.get("ri:username")  # Fallback for older Server/DC

            user_identifier_for_log = account_id or userkey or username
            display_name = None

            if confluence_client and user_identifier_for_log:
                try:
                    if account_id and isinstance(account_id, str):
                        user_details = confluence_client.get_user_details_by_accountid(
                            account_id
                        )
                        display_name = user_details.get("displayName")
                    elif userkey and isinstance(userkey, str):
                        # For Confluence Server/DC, use userkey endpoint
                        user_details = confluence_client.get_user_details_by_userkey(
                            userkey
                        )
                        display_name = user_details.get("displayName")
                    elif username and isinstance(username, str):
                        # For older Confluence Server/DC, use username endpoint
                        user_details = confluence_client.get_user_details_by_username(
                            username
                        )
                        display_name = user_details.get("displayName")
                except Exception as e:
                    logger.warning(
                        f"Error fetching user details for profile macro (user: {user_identifier_for_log}): {e}"
                    )
            elif not confluence_client:
                logger.warning(
                    "Confluence client not available for User Profile Macro processing."
                )

            if display_name:
                replacement_text = f"@{display_name}"
                _replace_with(macro_element, replacement_text)
            else:
                fallback_identifier = (
                    user_identifier_for_log
                    if user_identifier_for_log
                    else "unknown_user"
                )
                fallback_text = f"[User Profile: {fallback_identifier}]"
                _replace_with(macro_element, fallback_text)
                logger.debug(f"Using fallback for user profile macro: {fallback_text}")

    def _replace_user_mention(
        self,
        user_element: Tag,
        account_id: str,
        confluence_client: ConfluenceClient | None = None,
    ) -> None:
        """
        Replace a user mention with the user's display name.

        Args:
            user_element: The HTML element containing the user mention
            account_id: The user's account ID
            confluence_client: Optional Confluence client for user lookups
        """
        try:
            # Only attempt to get user details if we have a valid confluence client
            if confluence_client is not None:
                user_details = confluence_client.get_user_details_by_accountid(
                    account_id
                )
                display_name = user_details.get("displayName", "")
                if display_name:
                    new_text = f"@{display_name}"
                    _replace_with(user_element, new_text)
                    return
            # If we don't have a confluence client or couldn't get user details,
            # use fallback
            self._use_fallback_user_mention(user_element, account_id)
        except Exception as e:
            logger.warning(f"Error processing user mention: {str(e)}")
            self._use_fallback_user_mention(user_element, account_id)

    def _use_fallback_user_mention(self, user_element: Tag, account_id: str) -> None:
        """
        Replace user mention with a fallback when the API call fails.

        Args:
            user_element: The HTML element containing the user mention
            account_id: The user's account ID
        """
        # Fallback: just use the account ID
        new_text = f"@user_{account_id}"
        _replace_with(user_element, new_text)

    def _replace_user_mention_by_userkey(
        self,
        user_element: Tag,
        userkey: str,
        confluence_client: ConfluenceClient | None = None,
    ) -> None:
        """
        Replace a user mention using userkey (Server/DC).

        Uses the /rest/api/user?key= endpoint to resolve the display name.

        Args:
            user_element: The HTML element containing the user mention
            userkey: The user's internal userkey
            confluence_client: Optional Confluence client for user lookups
        """
        try:
            if confluence_client is not None:
                user_details = confluence_client.get_user_details_by_userkey(userkey)
                display_name = user_details.get("displayName", "")
                if display_name:
                    _replace_with(user_element, f"@{display_name}")
                    return
            _replace_with(user_element, f"@user_{userkey}")
        except Exception as e:
            logger.warning(f"Error processing user mention by userkey: {str(e)}")
            _replace_with(user_element, f"@user_{userkey}")

    def _replace_user_mention_by_username(
        self,
        user_element: Tag,
        username: str,
        confluence_client: ConfluenceClient | None = None,
    ) -> None:
        """
        Replace a user mention using username/userkey (Server/DC).

        Args:
            user_element: The HTML element containing the user mention
            username: The user's username or userkey
            confluence_client: Optional Confluence client for user lookups
        """
        try:
            if confluence_client is not None:
                user_details = confluence_client.get_user_details_by_username(username)
                display_name = user_details.get("displayName", "")
                if display_name:
                    _replace_with(user_element, f"@{display_name}")
                    return
            # Fallback: use the username directly
            _replace_with(user_element, f"@{username}")
        except Exception as e:
            logger.warning(f"Error processing user mention by username: {str(e)}")
            _replace_with(user_element, f"@{username}")

    def _find_attachment_url(
        self,
        filename: str,
        attachments: list[dict[str, Any]] | None,
    ) -> str | None:
        """Find an attachment's download URL by filename.

        Args:
            filename: The attachment filename to look up
            attachments: List of attachment dicts from Confluence API

        Returns:
            The download URL if found, None otherwise
        """
        if not attachments:
            return None
        for att in attachments:
            if att.get("title") == filename:
                download = att.get("_links", {}).get("download")
                if download:
                    return str(download)
        return None

    @_keeps_sibling_positions
    def _process_images_in_soup(
        self,
        soup: BeautifulSoup,
        content_id: str = "",
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        """Convert Confluence ac:image tags to standard HTML img tags.

        Args:
            soup: BeautifulSoup object containing HTML
            content_id: Optional page/content ID for fallback URL
            attachments: Optional attachment list for URL lookup
        """
        index = _TreeIndex(
            soup,
            {"attachment": _named("ri:attachment"), "url": _named("ri:url")},
        )
        for ac_image in soup.find_all("ac:image"):
            # An image inside a replaced one left the page with it.
            if index.inside(ac_image):
                continue
            index.skip(ac_image)
            src = ""
            alt = ""

            # Case 1: ri:attachment (file attached to the page)
            ri_att = index.first(ac_image, "attachment")
            if ri_att:
                filename = ri_att.get("ri:filename", "")
                alt = filename

                # Check if this references a different page
                is_cross_page = ri_att.find("ri:page") is not None

                # Try attachment list lookup first
                url = self._find_attachment_url(filename, attachments)
                if url:
                    # Prepend base_url if relative path
                    if url.startswith("/") and self.base_url:
                        src = f"{self.base_url}{url}"
                    else:
                        src = url
                elif content_id and not is_cross_page:
                    encoded = urllib.parse.quote(filename, safe="")
                    src = f"{self.base_url}/download/attachments/{content_id}/{encoded}"
                else:
                    src = filename
            else:
                # Case 2: ri:url (external URL)
                ri_url = index.first(ac_image, "url")
                if ri_url:
                    src = ri_url.get("ri:value", "")
                    # Extract filename from URL path for alt text
                    path = urllib.parse.urlparse(src).path
                    alt = path.rsplit("/", 1)[-1] if "/" in path else src
                else:
                    # Unknown inner element
                    # Log child names only: serializing the element made
                    # nested images quadratic.
                    logger.warning(
                        "ac:image tag with unsupported children: %s",
                        [child.name for child in ac_image.find_all(recursive=False)],
                    )
                    _replace_with(ac_image, "[unsupported image]")
                    continue

            # Build a standard <img> tag
            img_tag = soup.new_tag("img", src=src, alt=alt)

            # Preserve dimension attributes
            width = ac_image.get("ac:width")
            if width:
                img_tag["width"] = width
            height = ac_image.get("ac:height")
            if height:
                img_tag["height"] = height

            _replace_with(ac_image, img_tag)

    def _convert_html_to_markdown(self, text: str) -> str:
        """Convert HTML content to markdown if needed.

        Protects markdown code spans (fenced and inline) from being
        interpreted as HTML by BeautifulSoup before conversion.
        """
        # Protect fenced code blocks and inline code from HTML parsing
        code_blocks: list[str] = []
        inline_codes: list[str] = []

        text = _extract_blocks(
            text,
            r"```[^\n]*\n[\s\S]*?\n```",
            lambda m: m.group(0),
            code_blocks,
            "HTMLCVTBLOCK",
        )
        text = _extract_blocks(
            text,
            r"`[^`]+`",
            lambda m: m.group(0),
            inline_codes,
            "HTMLCVTINLINE",
        )

        if _contains_html_tag(text):
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    soup = BeautifulSoup(f"<div>{text}</div>", "html.parser")
                    html = str(soup.div.decode_contents()) if soup.div else text
                    text = md(html)
            except Exception as e:
                logger.warning(f"Error converting HTML to markdown: {str(e)}")

        # Restore in reverse order: inline first, then blocks
        text = _restore_blocks(text, inline_codes, "HTMLCVTINLINE")
        text = _restore_blocks(text, code_blocks, "HTMLCVTBLOCK")
        return text
