"""Confluence-specific text preprocessing module."""

import functools
import html
import importlib.util
import inspect
import logging
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import markdown  # type: ignore[import-untyped]
import md2conf.converter as md2conf_converter
from bs4 import BeautifulSoup, NavigableString, Tag
from markdown import (  # type: ignore[import-untyped]
    blockprocessors,
    inlinepatterns,
    preprocessors,
)
from md2conf.converter import (
    ConfluencePageCollection,
    ConfluenceStorageFormatConverter,
    ConfluenceUserCollection,
    ConverterOptions,
    attachment_name,
    elements_from_strings,
    elements_to_string,
)
from md2conf.metadata import ConfluenceSiteMetadata
from pymdownx import magiclink  # type: ignore[import-untyped]

from .base import BasePreprocessor

logger = logging.getLogger("mcp-atlassian")


#: The URL host part of pymdown-extensions 12.x magiclink. Host and path
#: both accept dots, so a short URL followed by a run of dots backtracks in
#: quadratic time (8000 dots took a second); before 11.0.1 a nested repeat
#: made it exponential. 13.0 rewrote the pattern without a host part.
_MAGIC_LINK_HOST = r"[^_\W](?:[-\w]|\.(?!=$))*"


def _linear_magic_link_re() -> re.Pattern[str] | None:
    """Return magiclink's URL pattern with the host cut to one character.

    The path part that follows accepts every host character, so the cut
    pattern matches the same spans. Returns ``None`` when the installed
    version has no such host part.
    """
    if magiclink.RE_LINK.count(_MAGIC_LINK_HOST) != 2:
        return None
    return re.compile(
        magiclink.RE_LINK.replace(_MAGIC_LINK_HOST, r"[^_\W]"),
        re.DOTALL | re.UNICODE,
    )


_MAGIC_LINK_RE = _linear_magic_link_re()


def _has_parameters(function: Any, names: list[str]) -> bool:
    """Whether ``function`` takes exactly these positional parameters.

    The hooks below replace Python-Markdown, pymdown-extensions and md2conf
    internals; each checks the shape it was written for and is not installed
    when an installed version differs.
    """
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False
    return list(parameters) == names and all(
        parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        for parameter in parameters.values()
    )


#: Pairs a new text is scanned for a close before the scanner compares it
#: with the text it has pairs for. Most links close within a few.
_NEAR_PAIRS = 16

#: Work allowed on one text node (a paragraph, heading, list item or table
#: cell) for the scans that cannot be made linear: pymdown-extensions'
#: delimiter searches and stock ``getLink`` on a target with a quote, per
#: character of the node and as a floor. Past it, that node keeps its source
#: text. A normal paragraph spends a small part of it: 8 unpaired ``~``
#: that each search to its end are allowed. pymdown-extensions spends a few
#: microseconds on each delimiter it pairs, so a larger allowance would let
#: 128 KiB of short paragraphs of ``.~a `` take tens of seconds.
_TEXT_WORK_PER_CHAR = 8
_TEXT_WORK_FLOOR = 1 << 14

#: Characters the inline pass may copy for one text node, per character of
#: the node and as a floor. Python-Markdown rebuilds the whole text of a
#: node for every inline match, so a node of many matches took time in the
#: square of its length (128 KiB of "<b>": ten seconds). A long paragraph
#: with a normal number of matches copies a small part of it; past it, the
#: node keeps its source text. A node copies at most the square of its
#: length, so the floor costs a document at most its length times the
#: floor's square root.
_INLINE_COPY_PER_CHAR = 1024
_INLINE_COPY_FLOOR = 1 << 28

#: Text no inline pattern can match: every pattern needs a punctuation mark,
#: a line break or a character outside ASCII to start.
_PLAIN_TEXT = re.compile(r"[A-Za-z0-9 ]*")


class _TextWork:
    """Work spent on the text node the inline pass is converting."""

    def __init__(self) -> None:
        self.left: int | None = None
        self.copy_left = 0
        self.over = False

    def start(self, length: int) -> None:
        self.left = _TEXT_WORK_PER_CHAR * length + _TEXT_WORK_FLOOR
        self.copy_left = _INLINE_COPY_PER_CHAR * length + _INLINE_COPY_FLOOR
        self.over = False

    def stop(self) -> None:
        self.left = None

    def spend(self, amount: int) -> None:
        if self.left is not None:
            self.left -= amount
            self.over = self.over or self.left < 0

    def copy(self, amount: int) -> None:
        if self.left is not None:
            self.copy_left -= amount
            self.over = self.over or self.copy_left < 0


class _PairScanner:
    """Where each opener closes, with each opener and closer read once.

    Python-Markdown's ``getText`` walks from an opening ``[`` to its closing
    ``]`` one character at a time, and ``getLink`` does the same from ``(``
    to ``)``. An unclosed opener walks to the end of the text, and the link
    patterns do that again for every opener: 16 KiB of ``[`` took over
    three minutes, and 16 KiB of ``[a](`` six seconds. This scanner pairs
    all openers and closers from the first opener it is asked about to that
    opener's close (or the end) in one pass and answers later questions
    from the pairs. For ``(`` it also notes whether a quote comes before the
    close, where ``getLink`` starts reading a title.

    Where an opener closes depends only on the text after it, so pairs are
    stored by distance from the end of the text. When the inline processor
    replaces a match with a placeholder, the text after the placeholder is
    unchanged and its pairs stay valid. Pairs further from the end than
    ``valid`` may be from an older text and are scanned again. Comparing the
    texts costs a copy of the tail, so a new text is first scanned for a
    near close the way stock Python-Markdown would.
    """

    def __init__(self, opener: str, closer: str, quotes: str = "") -> None:
        self.opener = opener
        self.quotes = quotes
        self.pattern = re.compile("[" + re.escape(opener + closer + quotes) + "]")
        self.data = ""
        self.closes: dict[int, tuple[int | None, bool]] = {}
        self.valid = 0

    def _near(self, data: str, opener: int) -> tuple[int, bool] | None:
        depth = 1
        for count, match in enumerate(self.pattern.finditer(data, opener + 1)):
            char = match.group()
            if count == _NEAR_PAIRS:
                return None
            if char in self.quotes:
                return match.start(), True
            depth += 1 if char == self.opener else -1
            if depth == 0:
                return match.start(), False
        return -1, False

    def _sync(self, data: str, opener: int) -> None:
        tail = len(data) - opener
        if self.closes and self.data.endswith(data[opener:]):
            self.valid = min(self.valid, tail)
        else:
            self.closes, self.valid = {}, 0
        self.data = data

    def _scan(self, data: str, opener: int) -> None:
        end = len(data)
        quotes = 0
        stack = [(opener, 0)]
        for match in self.pattern.finditer(data, opener + 1):
            char, pos = match.group(), match.start()
            if char in self.quotes:
                quotes += 1
            elif char == self.opener:
                stack.append((pos, quotes))
            else:
                start, seen = stack.pop()
                self.closes[end - start] = (end - pos, quotes != seen)
                if not stack:
                    if end - pos <= self.valid:
                        self.valid = max(self.valid, end - opener)
                    return
        for start, seen in stack:
            self.closes[end - start] = (None, quotes != seen)
        self.valid = max(self.valid, end - opener)

    def close(self, data: str, opener: int) -> tuple[int, bool]:
        """Return where the opener at ``opener`` closes (or -1), and whether
        a quote comes first."""
        if data is not self.data:
            near = self._near(data, opener)
            if near is not None:
                return near
            self._sync(data, opener)
        tail = len(data) - opener
        if tail > self.valid or tail not in self.closes:
            self._scan(data, opener)
        close, quoted = self.closes[tail]
        return (-1 if close is None else len(data) - close), quoted


#: ``LinkInlineProcessor.RE_LINK``, whose groups ``get_link`` reads.
_LINK_TARGET = r"""\(\s*(?:(<[^<>]*>)\s*(?:('[^']*'|"[^"]*")\s*)?\))?"""


def _use_linear_link_scans(converter: Any, work: _TextWork) -> None:
    """Give the stock link patterns of ``converter`` linear text and target scans.

    ``getText`` answers from a ``_PairScanner`` of brackets. ``getLink``
    answers from one of parentheses unless the target is in angle brackets
    or has a quote before its close; those go to stock ``getLink``, and
    what it reads counts as ``work`` on the text node. Leaves the patterns
    alone when the installed Python-Markdown has no such methods.
    """
    base = getattr(inlinepatterns, "LinkInlineProcessor", None)
    stock_text = getattr(base, "getText", None)
    stock_link = getattr(base, "getLink", None)
    if (
        not _has_parameters(stock_text, ["self", "data", "index"])
        or not _has_parameters(stock_link, ["self", "data", "index"])
        or getattr(getattr(base, "RE_LINK", None), "pattern", None) != _LINK_TARGET
    ):
        return
    brackets = _PairScanner("[", "]")
    parens = _PairScanner("(", ")", "'\"")

    def get_text(data: str, index: int) -> tuple[str, int, bool]:
        close, _ = brackets.close(data, index - 1)
        if close < 0:
            # The link patterns drop the text of a link that is not handled.
            return "", len(data), False
        return data[index:close], close + 1, True

    def get_link(
        pattern: Any, data: str, index: int
    ) -> tuple[str, str | None, int, bool]:
        match = pattern.RE_LINK.match(data, pos=index)
        if match is None or match.group(1):
            return stock_link(pattern, data, index)
        close, quoted = parens.close(data, index)
        if quoted:
            if work.over:
                return "", None, index, False
            result = stock_link(pattern, data, index)
            work.spend((result[2] if result[3] else len(data)) - index)
            return result
        if close < 0:
            return "", None, len(data), False
        return (
            pattern.unescape(data[match.end() : close]).strip(),
            None,
            close + 1,
            True,
        )

    for pattern in converter.inlinePatterns:
        if not isinstance(pattern, base):
            continue
        if type(pattern).getText is stock_text:
            pattern.getText = lambda data, index, stock=pattern.getText: (
                get_text(data, index)
                if index > 0 and data[index - 1] == "["
                else stock(data, index)
            )
        if type(pattern).getLink is stock_link:
            pattern.getLink = lambda data, index, pattern=pattern: get_link(
                pattern, data, index
            )


_FOOTNOTE_REFERENCE = r"\[\^([^\]]*)\]"


class _UpToLastBracket:
    """A compiled ``\\[\\^([^\\]]*)\\]`` whose ``finditer`` stops at the last ``]``.

    A match ends with ``]``, so no match goes past the last one, and the
    matches are the same. Without the end, every ``[^`` that no ``]``
    follows scanned to the end of the text: 64 KiB of ``[^a `` took eight
    seconds in one regex call.
    """

    def __init__(self, compiled: re.Pattern[str]) -> None:
        self._compiled = compiled

    def __getattr__(self, name: str) -> Any:
        return getattr(self._compiled, name)

    def finditer(
        self, string: str, pos: int = 0, endpos: int = sys.maxsize
    ) -> Iterator[re.Match[str]]:
        return self._compiled.finditer(
            string, pos, min(endpos, string.rfind("]", pos) + 1)
        )


def _end_footnote_scans(converter: Any) -> None:
    """Give the footnote reference pattern an ``_UpToLastBracket`` regex."""
    if "footnote" not in converter.inlinePatterns:
        return
    pattern = converter.inlinePatterns["footnote"]
    compiled = getattr(pattern, "compiled_re", None)
    if isinstance(compiled, re.Pattern) and compiled.pattern == _FOOTNOTE_REFERENCE:
        pattern.compiled_re = _UpToLastBracket(compiled)


def _bound_delimiter_search(converter: Any, work: _TextWork) -> None:
    """Count pymdown-extensions' delimiter searches as ``work`` on the text node.

    Since pymdown-extensions 12.0, an opening ``~``, ``^`` or ``=`` that
    finds no closer makes the processor search the rest of the paragraph,
    and the next opener searches it again: 16 KiB of ``.~a `` took over 30
    seconds. Which delimiters pair depends on all the ones before them, so
    the searches are counted instead of shared; past the node's allowance a
    search finds nothing and the node keeps its source text. Leaves the
    processor alone when its ``search`` is not ``(data, start)``.
    """
    for pattern in converter.inlinePatterns:
        if type(pattern).__module__ != "pymdownx.delimiterprocessor":
            continue
        search = getattr(pattern, "search", None)
        if not _has_parameters(search, ["data", "start"]):
            continue

        def bounded_search(
            data: str, start: int, search: Callable[[str, int], Any] = search
        ) -> Any:
            if work.over:
                return None
            found = search(data, start)
            work.spend((len(data) if found is None else found.end()) - start)
            return found

        pattern.search = bounded_search


class _SuffixSearch:
    """A compiled regex whose ``search`` reuses what it found in a longer text.

    Python-Markdown splits a block at a heading, a rule or a quote and gives
    the rest of the block back to every block processor, whose ``search``
    then reads that rest again: a block of many such lines took time in the
    square of its length (128 KiB of "# a" lines: over two minutes). The
    rest is the end of the text searched before. A match at a position past
    the first one depends only on the text around it, which is the same in
    both, so where the longer text's first match was tells where the shorter
    one's is; position 0 is tried on its own. Only for patterns without
    lookbehind.
    """

    def __init__(self, compiled: re.Pattern[str]) -> None:
        self._compiled = compiled
        # Recent (text, start of its first match or -1), latest first: the
        # part of a block before a split is parsed in between.
        self._recent: list[tuple[str, int]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._compiled, name)

    def search(
        self, string: str, pos: int = 0, endpos: int = sys.maxsize
    ) -> re.Match[str] | None:
        compiled = self._compiled
        if pos != 0 or endpos != sys.maxsize:
            return compiled.search(string, pos, endpos)
        for index, (text, first) in enumerate(self._recent):
            offset = len(text) - len(string)
            if offset < 0 or not text.endswith(string):
                continue
            if first < 0 or first > offset:
                self._recent.insert(0, self._recent.pop(index))
                at_start = compiled.match(string)
                if at_start is not None or first < 0:
                    return at_start
                return compiled.search(string, first - offset)
            break
        found = compiled.search(string)
        self._recent.insert(0, (string, -1 if found is None else found.start()))
        del self._recent[_RECENT_TEXTS:]
        return found


_RECENT_TEXTS = 4


#: Block processors whose regex reads a whole block, by registry name, and
#: the attribute that holds it.
_BLOCK_SEARCHES = {
    "admonition": "RE",
    "hashheader": "RE",
    "hr": "SEARCH_RE",
    "quote": "RE",
    "reference": "RE",
    "footnote": "RE",
}


def _table_test(processor: Any, parent: Any, block: str) -> bool:
    """``TableProcessor.test`` reading only the rows it looks at.

    The stock method strips every row of the block before it looks at the
    first two, so each retest of the rest of a long block read all of it.
    """
    is_table = False
    first_end = block.find("\n")
    if first_end >= 0:
        header0 = block[:first_end].strip(" ")
        processor.border = 0
        if header0.startswith("|"):
            processor.border |= 1
        if processor.RE_END_BORDER.search(header0) is not None:
            processor.border |= 2
        row = processor._split_row(header0)
        row0_len = len(row)
        is_table = row0_len > 1

        # Each row in a single column table needs at least one pipe.
        if not is_table and row0_len == 1 and processor.border:
            start = first_end + 1
            while True:
                end = block.find("\n", start)
                line = block[start : len(block) if end < 0 else end].strip(" ")
                is_table = line.startswith("|")
                if not is_table:
                    is_table = processor.RE_END_BORDER.search(line) is not None
                if not is_table or end < 0:
                    break
                start = end + 1

        if is_table:
            second_end = block.find("\n", first_end + 1)
            second = block[first_end + 1 : len(block) if second_end < 0 else second_end]
            row = processor._split_row(second.strip(" "))
            is_table = (len(row) == row0_len) and set("".join(row)) <= set("|:- ")
            if is_table:
                processor.separator = row
    return is_table


def _setext_run(processor: Any, parent: Any, blocks: list[str]) -> None:
    """``SetextHeaderProcessor.run`` cutting only the first two lines.

    The stock method splits the whole block into lines and joins all but
    two of them back, so a block of many underlined lines read all of it
    again at each heading.
    """
    block = blocks.pop(0)
    first_end = block.find("\n")
    second_end = block.find("\n", first_end + 1)
    underline = block[first_end + 1 : len(block) if second_end < 0 else second_end]
    level = 1 if underline.startswith("=") else 2
    heading = ET.SubElement(parent, f"h{level}")
    heading.text = block[:first_end].strip()
    if second_end >= 0:
        # Block contains additional lines. Add to master blocks for later.
        blocks.insert(0, block[second_end + 1 :])


def _detab(processor: Any, text: str, length: int | None = None) -> tuple[str, str]:
    """``BlockProcessor.detab`` reading only the lines it keeps.

    The stock method splits the whole text into lines to keep the indented
    ones at its start and joins the rest back, so a block of many
    admonitions or list items read all of it again for each.
    """
    if length is None:
        length = processor.tab_length
    prefix = " " * length
    kept: list[str] = []
    pos = 0
    while pos <= len(text):
        end = text.find("\n", pos)
        line = text[pos : len(text) if end < 0 else end]
        if line.startswith(prefix):
            kept.append(line[length:])
        elif not line.strip():
            kept.append("")
        else:
            break
        pos = len(text) + 1 if end < 0 else end + 1
    return "\n".join(kept), text[pos:]


def _linear_block_retests(converter: Any) -> None:
    """Give the block processors that read a whole block linear retests."""
    processors = getattr(getattr(converter, "parser", None), "blockprocessors", None)
    if processors is None:
        return
    for name, attribute in _BLOCK_SEARCHES.items():
        if name not in processors:
            continue
        compiled = getattr(processors[name], attribute, None)
        if isinstance(compiled, re.Pattern) and "(?<" not in compiled.pattern:
            setattr(processors[name], attribute, _SuffixSearch(compiled))
    try:
        from markdown.extensions import tables  # type: ignore[import-untyped]
    except ImportError:
        return
    table = processors["table"] if "table" in processors else None
    stock = getattr(getattr(tables, "TableProcessor", None), "test", None)
    if (
        type(table) is getattr(tables, "TableProcessor", None)
        and _has_parameters(stock, ["self", "parent", "block"])
        and all(hasattr(table, name) for name in ("RE_END_BORDER", "_split_row"))
    ):
        table.test = functools.partial(_table_test, table)
    stock_detab = getattr(
        getattr(blockprocessors, "BlockProcessor", None), "detab", None
    )
    if _has_parameters(stock_detab, ["self", "text", "length"]):
        for processor in processors:
            if type(processor).detab is stock_detab:
                processor.detab = functools.partial(_detab, processor)
    setext = processors["setextheader"] if "setextheader" in processors else None
    stock_setext = getattr(blockprocessors, "SetextHeaderProcessor", None)
    if type(setext) is stock_setext and _has_parameters(
        getattr(stock_setext, "run", None), ["self", "parent", "blocks"]
    ):
        setext.run = functools.partial(_setext_run, setext)


#: Nesting allowed in a list or quote block: leading whitespace (64 levels
#: of four-space nesting) and list or quote markers on one line. Python-
#: Markdown re-reads a block at every nesting level and recurses once per
#: level, so deeper nesting took time in the square of the depth or raised
#: RecursionError. A deeper block keeps its source text.
_MAX_NESTING_INDENT = 256
_MAX_NESTING_MARKERS = 64
_NESTED_BLOCK_START = re.compile(r"[ ]{0,3}(?:[-*+]|\d+[.)]|>)(?:[ \t]|$)")
_NESTING_MARKERS = re.compile(r"(?:[ \t]*(?:[-*+]|\d+[.)]|>)(?=[ \t]|$))+")
_NESTING_MARKER = re.compile(r"[-*+>]|\d+[.)]")


def _too_deep(lines: list[str]) -> bool:
    """Whether a list or quote block nests deeper than the limits."""
    if not _NESTED_BLOCK_START.match(lines[0]):
        return False
    for line in lines:
        # Only a line that opens a list item or a quote nests; the spaces of
        # a continuation line are its content.
        markers = _NESTING_MARKERS.match(line)
        if markers is None:
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        if indent > _MAX_NESTING_INDENT or (
            len(_NESTING_MARKER.findall(markers.group())) > _MAX_NESTING_MARKERS
        ):
            return True
    return False


class _NestingLimitPreprocessor(preprocessors.Preprocessor):  # type: ignore[misc]
    """Keep a list or quote block that nests too deep as its source text."""

    def run(self, lines: list[str]) -> list[str]:
        result: list[str] = []
        start = 0
        for index in range(len(lines) + 1):
            if index < len(lines) and lines[index].strip():
                continue
            block = lines[start:index]
            if block and _too_deep(block):
                text = html.escape("\n".join(block), quote=False)
                result.append(self.md.htmlStash.store(f"<p>{text}</p>"))
            else:
                result.extend(block)
            if index < len(lines):
                result.append(lines[index])
            start = index + 1
        return result


def _limit_nesting(converter: Any) -> None:
    """Run ``_NestingLimitPreprocessor`` after the other preprocessors."""
    registry = getattr(converter, "preprocessors", None)
    stash = getattr(converter, "htmlStash", None)
    if callable(getattr(registry, "register", None)) and callable(
        getattr(stash, "store", None)
    ):
        registry.register(_NestingLimitPreprocessor(converter), "nesting_limit", 1)


#: The start-tag pattern of the HTML block parser (the standard library's
#: ``html.parser`` as copied by Python-Markdown), as the hook below was
#: written for.
_LOCATE_TAG_END = r"""
  [a-zA-Z][^`\t\n\r\f />]*           # tag name
  [\t\n\r\f /]*                     # optional whitespace before attribute name
  (?:(?<=['"\t\n\r\f /])[^`\t\n\r\f />][^\t\n\r\f /=>]*  # attribute name
    (?:=                            # value indicator
      (?:'[^']*'                    # LITA-enclosed value
        |"[^"]*"                    # LIT-enclosed value
        |(?!['"])[^>\t\n\r\f ]*     # bare value
       )
     )?
    [\t\n\r\f /]*                   # possibly followed by a space
   )*
   >?
"""
_TAG_NAME = re.compile(r"[a-zA-Z][^`\t\n\r\f />]*[\t\n\r\f /]*")
_TAG_ATTRIBUTE = re.compile(
    r"""(?<=['"\t\n\r\f /])[^`\t\n\r\f />][^\t\n\r\f /=>]*"""
    r"""(?:=(?:'[^']*'|"[^"]*"|(?!['"])[^>\t\n\r\f ]*))?[\t\n\r\f /]*"""
)


class _TagEnds:
    """Where ``html.parser``'s start-tag pattern ends, from each position.

    The pattern is a tag name, then attributes, then an optional ``>``. The
    parser matched it from every ``<`` followed by a letter, and the
    attributes of one ``<`` run on over the next ones, so 128 KiB of
    ``<a b`` took three minutes. Where the attributes end from a position
    depends only on the text from there, so each position's end is found
    once and shared by every tag whose attributes pass through it.
    """

    def __init__(self) -> None:
        self.data = ""
        self.ends: dict[int, int] = {}

    def check_for_whole_start_tag(self, data: str, i: int) -> int:
        """``HTMLParser.check_for_whole_start_tag``: the end, or -1."""
        if data is not self.data:
            self.data, self.ends = data, {}
        name = _TAG_NAME.match(data, i + 1)
        if name is None:
            return -1
        pos = name.end()
        chain = []
        while pos not in self.ends:
            attribute = _TAG_ATTRIBUTE.match(data, pos)
            if attribute is None or attribute.end() == pos:
                self.ends[pos] = pos
                break
            chain.append(pos)
            pos = attribute.end()
        end = self.ends[pos]
        for visited in chain:
            self.ends[visited] = end
        if data.startswith(">", end):
            end += 1
        return end if data[end - 1] == ">" else -1


def _linear_start_tags(converter: Any) -> None:
    """Give the HTML block parser a ``_TagEnds`` start-tag check.

    Only when the parser's start-tag pattern is ``_LOCATE_TAG_END`` and the
    preprocessor's ``run`` is Python-Markdown's own.
    """
    try:
        from markdown import htmlparser  # type: ignore[import-untyped]
        from markdown.extensions import md_in_html  # type: ignore[import-untyped]
    except ImportError:
        return
    copied = getattr(htmlparser, "htmlparser", None)
    pattern = getattr(getattr(copied, "locatetagend", None), "pattern", None)
    registry = getattr(converter, "preprocessors", None)
    if pattern != _LOCATE_TAG_END or registry is None or "html_block" not in registry:
        return
    block = registry["html_block"]
    extractors = {
        getattr(md_in_html, "HtmlBlockPreprocessor", None): "HTMLExtractorExtra",
        getattr(preprocessors, "HtmlBlockPreprocessor", None): "HTMLExtractor",
    }
    name = extractors.get(type(block))
    module = md_in_html if name == "HTMLExtractorExtra" else htmlparser
    extractor = getattr(module, name or "", None)
    if (
        extractor is None
        or not _has_parameters(type(block).run, ["self", "lines"])
        or not _has_parameters(extractor.check_for_whole_start_tag, ["self", "i"])
    ):
        return
    tag_ends = _TagEnds()

    class Extractor(extractor):  # type: ignore[misc, valid-type]
        def check_for_whole_start_tag(self, i: int) -> int:
            return tag_ends.check_for_whole_start_tag(self.rawdata, i)

    def run(lines: list[str]) -> list[str]:
        # Python-Markdown's run, with the extractor above.
        parser = Extractor(block.md)
        parser.feed("\n".join(lines))
        parser.close()
        return "".join(parser.cleandoc).split("\n")

    block.run = run


def _reassemble_fences(processor: Any, lines: list[str]) -> list[str]:
    """pymdownx superfences' ``reassemble`` in one pass.

    The stock method rebuilds the whole line list once per fenced block, so
    many fenced blocks took time in the square of their number. The stack
    holds non-overlapping ``(block, start, end)`` line ranges in the order
    they were found, and replacing them front to back gives the same lines.
    """
    result: list[str] = []
    done = 0
    for fenced, start, end in processor.stack:
        result.extend(lines[done:start])
        result.append(fenced)
        done = end
    result.extend(lines[done:])
    processor.stack.clear()
    return result


def _linear_fence_reassembly(converter: Any) -> None:
    """Give superfences' block preprocessor ``_reassemble_fences``.

    Only for the class whose ``reassemble`` it matches; the raw-block variant
    transforms each block and keeps its own.
    """
    try:
        from pymdownx import superfences  # type: ignore[import-untyped]
    except ImportError:
        return
    stock = getattr(superfences, "SuperFencesBlockPreprocessor", None)
    registry = getattr(converter, "preprocessors", None)
    if stock is None or registry is None or "fenced_code_block" not in registry:
        return
    fences = registry["fenced_code_block"]
    if type(fences) is stock and _has_parameters(stock.reassemble, ["self", "lines"]):
        fences.reassemble = functools.partial(_reassemble_fences, fences)


def _bound_inline_pass(converter: Any, work: _TextWork) -> None:
    """Bound the inline pass per text node, and resume after matches before 3.11.

    A text node whose ``work`` runs out (the scans, or the copying of the
    node for each match) keeps its source text: no inline syntax is applied
    to it, so its markup stays balanced (a raw ``<b>`` matched before the limit would
    otherwise lose its ``</b>``). Other nodes are not affected.

    Before Python-Markdown 3.11.0 the inline pass also searched a text again
    from its start after every match (64 KiB of code spans: four minutes);
    3.11 needs Python 3.11, so Python 3.10 always has an older one. There
    the pass goes on after the placeholder that replaced the match, as 3.11
    does. pymdownx delimiter patterns are left to search again: they pair
    ``x^2^^3^`` only when the text after their own placeholder is searched
    once more. Does nothing when the inline pass is not shaped as expected.
    """
    inline = (
        converter.treeprocessors["inline"]
        if "inline" in converter.treeprocessors
        else None
    )
    handle = getattr(inline, "_InlineProcessor__handleInline", None)
    apply = getattr(inline, "_InlineProcessor__applyPattern", None)
    if not _has_parameters(
        getattr(type(inline), "_InlineProcessor__handleInline", None),
        ["self", "data", "patternIndex"],
    ) or not _has_parameters(
        getattr(type(inline), "_InlineProcessor__applyPattern", None),
        ["self", "pattern", "data", "patternIndex", "startIndex"],
    ):
        return
    version = getattr(markdown, "__version_info__", (3, 11))
    placeholder = getattr(getattr(markdown, "util", None), "INLINE_PLACEHOLDER", None)
    resume = version < (3, 11) and placeholder is not None
    depth = [0]

    def apply_bounded(
        pattern: Any, data: str, pattern_index: int, start_index: int = 0
    ) -> tuple[str, bool, int]:
        if work.over:
            return data, False, 0
        result, matched, index = apply(pattern, data, pattern_index, start_index)
        if not matched:
            return result, matched, index
        work.copy(len(result))
        stashed = getattr(inline, "stashed_nodes", None)
        if (
            resume
            and index == 0
            and isinstance(stashed, dict)
            and stashed
            and type(pattern).__module__ != "pymdownx.delimiterprocessor"
        ):
            last = placeholder % f"{len(stashed) - 1:04d}"
            if (found := result.find(last, start_index)) >= 0:
                index = found + len(last)
        return result, matched, index

    def handle_bounded(data: str, pattern_index: int = 0) -> str:
        if depth[0] == 0:
            if _PLAIN_TEXT.fullmatch(data):
                return data
            work.start(len(data))
        elif work.over:
            return data
        depth[0] += 1
        try:
            result = handle(data, pattern_index)
        finally:
            depth[0] -= 1
        if depth[0] == 0:
            over = work.over
            work.stop()
            if over:
                return data
        return result

    inline._InlineProcessor__applyPattern = apply_bounded
    inline._InlineProcessor__handleInline = handle_bounded


def _linear_visit(self: Any, node: Any) -> None:
    """``NodeVisitor.visit`` of md2conf, stepping from child to child.

    md2conf reads and writes ``node[index]`` for every child, and lxml finds
    a child by index by walking the siblings from the first one, so a
    paragraph of many links or a page of many paragraphs took time in the
    square of their number (40000 paragraphs, 120 KB: half a minute). This
    visits the same children in the same order with the same actions. A
    transform changes its element and the element's own children, never the
    element's siblings, so the next child is known before the transform.
    """
    recurse, remove = _ELEMENT_ACTION.RECURSE, _ELEMENT_ACTION.REMOVE
    count = len(node)
    source = node[0] if count else None
    index = 0
    while index < count and source is not None:
        following = source.getnext()
        target = self.transform(source)
        if target is recurse:
            self.visit(source)
            index += 1
        elif target is remove:
            # md2conf's remove_element, without its search for the index
            if source.tail:
                previous = source.getprevious()
                if previous is not None:
                    previous.tail = (previous.tail or "") + source.tail
                else:
                    node.text = (node.text or "") + source.tail
            node.remove(source)
            count -= 1
        else:
            target.tail = source.tail
            source.tail = None
            node.replace(source, target)
            index += 1
        source = following


_ELEMENT_ACTION = getattr(md2conf_converter, "ElementAction", None)
_NODE_VISITOR = getattr(md2conf_converter, "NodeVisitor", None)


def _storage_converter_class() -> type[ConfluenceStorageFormatConverter]:
    """Return md2conf's converter with ``_linear_visit``, when it fits.

    Returns md2conf's own class when the installed version visits in some
    other way than the ``NodeVisitor.visit`` that ``_linear_visit`` follows.
    """
    actions = getattr(_ELEMENT_ACTION, "__members__", {})
    if (
        _NODE_VISITOR is None
        or getattr(ConfluenceStorageFormatConverter, "visit", None)
        is not getattr(_NODE_VISITOR, "visit", None)
        or set(actions) != {"RECURSE", "REMOVE"}
        or not _has_parameters(getattr(_NODE_VISITOR, "visit", None), ["self", "node"])
    ):
        return ConfluenceStorageFormatConverter
    return type(
        "_StorageFormatConverter",
        (ConfluenceStorageFormatConverter,),
        {"visit": _linear_visit},
    )


_STORAGE_CONVERTER = _storage_converter_class()


def markdown_to_html(content: str) -> str:
    """Convert Markdown like ``md2conf.converter.markdown_to_html``.

    md2conf keeps one module-level Markdown converter that every call resets
    and reuses: calls from two worker threads at once mixed their documents,
    and a conversion that failed inside it left state behind that broke
    every later one. Each call here runs a private copy of the
    ``md2conf.markdown`` module, so it gets a converter of its own, built
    with the settings of whichever md2conf version is installed.
    """
    spec = importlib.util.find_spec("md2conf.markdown")
    if spec is None or spec.loader is None:
        raise RuntimeError("md2conf.markdown is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if _MAGIC_LINK_RE is not None:
        module._CONVERTER.inlinePatterns["magic-link"].compiled_re = _MAGIC_LINK_RE
    work = _TextWork()
    _use_linear_link_scans(module._CONVERTER, work)
    _bound_delimiter_search(module._CONVERTER, work)
    _end_footnote_scans(module._CONVERTER)
    _linear_block_retests(module._CONVERTER)
    _limit_nesting(module._CONVERTER)
    _linear_start_tags(module._CONVERTER)
    _linear_fence_reassembly(module._CONVERTER)
    _bound_inline_pass(module._CONVERTER, work)
    return str(module.markdown_to_html(content))


class ConfluencePreprocessor(BasePreprocessor):
    """Handles text preprocessing for Confluence content."""

    # Use a private-use sequence that is absent from the converted HTML so
    # restoring an opt-out task list cannot remove user-supplied characters.
    _TASK_MARKER_PREFIX = "\ue000"
    _TASK_MARKER_PATTERN = re.compile(r"(<li\b[^>]*>)(\[[ xX]\])")

    def __init__(self, base_url: str) -> None:
        """
        Initialize the Confluence text preprocessor.

        Args:
            base_url: Base URL for Confluence API
        """
        super().__init__(base_url=base_url)

    # Table width and layout keyed by the caller-supplied table_layout value.
    _TABLE_WIDTHS: dict[str, str] = {
        "full-width": "1800",
        "wide": "960",
        "default": "760",
    }
    _TABLE_LAYOUTS: dict[str, str] = {
        "full-width": "full-width",
        "wide": "wide",
        "default": "default",
    }

    def markdown_to_confluence_storage(
        self,
        markdown_content: str,
        *,
        enable_heading_anchors: bool = False,
        apply_task_lists: bool = True,
        table_layout: str | None = None,
    ) -> str:
        """
        Convert Markdown content to Confluence storage format (XHTML)

        Args:
            markdown_content: Markdown text to convert
            enable_heading_anchors: Whether to enable automatic heading anchor
                generation (default: False)
            apply_task_lists: Whether to convert GFM task-list items
                (``- [ ]`` / ``- [x]``) to Confluence ``ac:task-list`` macros
                (default: True)
            table_layout: Optional table width preset applied to all tables in the output.
                Values: 'full-width' (1800 px), 'wide' (960 px), or 'default'
                (760 px / Confluence default).
                When None, tables retain the default 760 px width emitted by the converter.

        Returns:
            Confluence storage format (XHTML) string
        """
        try:
            # First convert markdown to HTML
            html_content = self._fix_attachment_images(
                markdown_to_html(markdown_content)
            )
            task_marker_prefix: str | None = None
            if not apply_task_lists:
                task_marker_prefix = self._get_task_list_marker_prefix(html_content)
                html_content = self._protect_task_list_markers(
                    html_content, task_marker_prefix
                )

            with tempfile.TemporaryDirectory() as temp_dir:
                root_dir = Path(temp_dir)
                path = root_dir / "temp.md"
                path.write_text(markdown_content, encoding="utf-8")

                # Parse the HTML into an element tree
                root = elements_from_strings([html_content])

                parsed_url = urlparse(self.base_url)
                base_path = parsed_url.path or "/wiki/"
                if not base_path.endswith("/"):
                    base_path += "/"

                # Diagram extensions are off: they start external renderers
                # on caller-supplied source, and their images and source
                # attachments are never uploaded. Diagram blocks stay code.
                options = ConverterOptions(
                    force_valid_url=False,
                    heading_anchors=enable_heading_anchors,
                    extensions=[],
                )

                # Create a converter
                converter = _STORAGE_CONVERTER(
                    options=options,
                    path=path,
                    root_dir=root_dir,
                    site_metadata=ConfluenceSiteMetadata(
                        domain=parsed_url.netloc,
                        base_path=base_path,
                        space_key=None,
                    ),
                    page_metadata=ConfluencePageCollection(),
                    user_metadata=ConfluenceUserCollection(),
                )

                # Transform the HTML to Confluence storage format
                converter.visit(root)

                # Convert the element tree back to a string
                storage_format = self._fix_attachment_images(
                    str(elements_to_string(root))
                )
                if task_marker_prefix is not None:
                    storage_format = self._restore_task_list_markers(
                        storage_format, task_marker_prefix
                    )
                if apply_task_lists:
                    storage_format = self._normalize_task_list_bodies(storage_format)

                if apply_task_lists:
                    storage_format = self._apply_task_lists(storage_format)
                if table_layout is not None and table_layout in self._TABLE_WIDTHS:
                    storage_format = self._apply_table_layout(
                        storage_format, table_layout
                    )
                return storage_format

        except Exception as e:
            logger.error(f"Error converting markdown to Confluence storage format: {e}")
            logger.exception(e)

            # Fall back to a simpler method if the conversion fails. Markdown
            # nested deeper than Python-Markdown can recurse fails there too;
            # it is then kept as escaped text.
            try:
                if isinstance(e, RecursionError):
                    raise RecursionError from e
                html_content = markdown_to_html(markdown_content)
            except RecursionError:
                html_content = html.escape(markdown_content, quote=False)

            # This creates a proper Confluence storage format document
            storage_format = self._fix_attachment_images(f"""<p>{html_content}</p>""")
            if apply_task_lists:
                storage_format = self._apply_task_lists(storage_format)
            if table_layout is not None and table_layout in self._TABLE_WIDTHS:
                storage_format = self._apply_table_layout(storage_format, table_layout)

            return storage_format

    @classmethod
    def _get_task_list_marker_prefix(cls, html_content: str) -> str:
        """Return a private-use marker sequence absent from the HTML."""
        marker_prefix = cls._TASK_MARKER_PREFIX
        while marker_prefix in html_content:
            marker_prefix += cls._TASK_MARKER_PREFIX
        return marker_prefix

    @classmethod
    def _protect_task_list_markers(cls, html_content: str, marker_prefix: str) -> str:
        """Prevent md2conf from converting task lists when requested."""
        return cls._TASK_MARKER_PATTERN.sub(rf"\1{marker_prefix}\2", html_content)

    @classmethod
    def _restore_task_list_markers(cls, storage_html: str, marker_prefix: str) -> str:
        """Remove task-list conversion sentinels from converted HTML."""
        return storage_html.replace(marker_prefix, "")

    @staticmethod
    def _normalize_task_list_bodies(storage_html: str) -> str:
        """Match legacy task-body whitespace after md2conf 0.6 conversion."""
        return re.sub(r"(<ac:task-body>)[ \t]+", r"\1", storage_html)

    @classmethod
    def _apply_task_lists(cls, storage_html: str) -> str:
        """Convert GFM-style task list items to Confluence ac:task-list macros.

        md2conf renders GFM task list items (``- [ ]`` / ``- [x]``) as plain
        ``<ul><li>`` elements with the checkbox marker as literal text.
        Confluence needs ``<ac:task-list>`` / ``<ac:task>`` elements to render
        interactive checkboxes.

        Only converts unnested ``<ul>`` blocks whose every direct ``<li>``
        begins with a checkbox marker. Mixed and nested lists are left unchanged.

        Args:
            storage_html: Confluence storage-format string to post-process.

        Returns:
            Updated storage-format string with task lists converted.
        """
        if "<ul" not in storage_html.lower() or "[" not in storage_html:
            return storage_html

        marker_pattern = re.compile(
            r"^\s*\[(?P<checked>[ xX])\](?:[ \t]+|$)(?P<body>.*)$",
            re.DOTALL,
        )
        soup = BeautifulSoup(storage_html, "html.parser")
        rewritten = False

        for unordered_list in soup.find_all("ul"):
            if not isinstance(unordered_list, Tag):
                continue
            if unordered_list.find("ul") or unordered_list.find_parent("ul"):
                continue

            items = unordered_list.find_all("li", recursive=False)
            if not items:
                continue

            matches: list[tuple[Tag, NavigableString, re.Match[str]]] = []
            for item in items:
                if not isinstance(item, Tag):
                    break
                first_content = next(
                    (
                        child
                        for child in item.contents
                        if not isinstance(child, NavigableString) or str(child).strip()
                    ),
                    None,
                )
                if not isinstance(first_content, NavigableString):
                    break
                match = marker_pattern.match(str(first_content))
                if match is None:
                    break
                matches.append((item, first_content, match))

            if len(matches) != len(items):
                continue

            task_list = soup.new_tag("ac:task-list")
            for item, marker_text, match in matches:
                marker_text.replace_with(match.group("body"))

                task = soup.new_tag("ac:task")
                status = soup.new_tag("ac:task-status")
                status.string = (
                    "complete"
                    if match.group("checked").lower() == "x"
                    else "incomplete"
                )
                body = soup.new_tag("ac:task-body")
                while item.contents:
                    body.append(item.contents[0].extract())
                task.extend((status, body))
                task_list.append(task)

            unordered_list.replace_with(task_list)
            rewritten = True

        return str(soup) if rewritten else storage_html

    @classmethod
    def _apply_table_layout(cls, storage_html: str, table_layout: str) -> str:
        """Set table width and layout attributes in Confluence storage format.

        The md2conf converter emits bare ``<table>`` tags with no width or
        layout attributes.  Confluence renders these at its default narrow
        width.  This method injects ``data-table-width`` and ``data-layout``
        attributes so tables render at the requested width.

        If attributes already exist (e.g. content edited via another tool)
        they are replaced rather than duplicated.

        Args:
            storage_html: Confluence storage-format string to post-process.
            table_layout: One of 'full-width', 'wide', or 'default'.

        Returns:
            Updated storage-format string with table width attributes set.
        """
        width = cls._TABLE_WIDTHS.get(table_layout, "760")
        layout = cls._TABLE_LAYOUTS.get(table_layout, "default")
        attrs = f'data-table-width="{width}" data-layout="{layout}"'

        def _replace_table_tag(m: re.Match) -> str:
            tag = m.group(0)
            # Strip any existing data-table-width / data-layout attributes first
            tag = re.sub(r'\s*data-table-width="[^"]*"', "", tag)
            tag = re.sub(r'\s*data-layout="[^"]*"', "", tag)
            # Inject new attributes after <table
            return re.sub(r"^<table", f"<table {attrs}", tag)

        return re.sub(r"<table\b[^>]*>", _replace_table_tag, storage_html)

    @staticmethod
    def _is_attachment_image_source(src: str) -> bool:
        """Return whether an image source should resolve as an attachment."""
        parsed_src = urlparse(src)
        return not parsed_src.scheme and not src.startswith(("/", "#"))

    @staticmethod
    def _fix_attachment_images(storage_html: str) -> str:
        """Replace bare-filename ``<img>`` tags with Confluence attachment macros.

        Confluence Storage Format cannot resolve bare filenames in
        ``<img src="filename.ext"/>``. Attachment references must use the
        ``ac:image`` / ``ri:attachment`` macro instead. External URLs
        (``http``/``https``/``data``) and absolute paths are left untouched.

        Args:
            storage_html: Confluence storage format HTML string.

        Returns:
            Storage HTML with bare-filename img tags replaced by attachment macros.
        """
        if "<img" not in storage_html.lower():
            return storage_html

        soup = BeautifulSoup(storage_html, "html.parser")
        rewritten = False

        for image in soup.find_all("img"):
            src = image.get("src")
            if not isinstance(src, str):
                continue
            if not ConfluencePreprocessor._is_attachment_image_source(src):
                continue

            attachment_image = soup.new_tag("ac:image")
            alt = image.get("alt", "")
            attachment_image["ac:alt"] = alt if isinstance(alt, str) else ""

            for html_attr, confluence_attr in (
                ("width", "ac:width"),
                ("height", "ac:height"),
            ):
                value = image.get(html_attr)
                if isinstance(value, str):
                    attachment_image[confluence_attr] = value

            attachment = soup.new_tag("ri:attachment")
            attachment["ri:filename"] = attachment_name(src)
            attachment_image.append(attachment)
            image.replace_with(attachment_image)
            rewritten = True

        return str(soup) if rewritten else storage_html
