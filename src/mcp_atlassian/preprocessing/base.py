"""Base preprocessing module."""

import logging
import re
import urllib.parse
import warnings
from collections.abc import Callable
from typing import Any, Protocol

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

logger = logging.getLogger("mcp-atlassian")


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
    for i in range(len(storage) - 1, -1, -1):
        text = text.replace(f"\x00{prefix}{i}\x00", storage[i])
    return text


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


def _restore_inline_code_macro(
    text: str, start: int, placeholder: str, code_block: str
) -> str | None:
    """Restore a code macro that markdownify collapsed into an inline span.

    Inside a table cell markdownify flattens the pre/code wrapper onto the
    row's line as a backtick span, where a multi-line fence would split the
    row. Mirror markdownify's own handling of pre/code in that position:
    collapse the body onto one line inside a span wide enough for any
    backtick run it contains.
    """
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end == -1:
        line_end = len(text)

    line_before = text[line_start:start]
    line_after = text[start + len(placeholder) : line_end]
    opening = re.search(r"`+[^`\r\n]*$", line_before)
    closing = re.match(r"[ \t]*`+", line_after)
    stored_opening = re.match(r"(?P<fence>`+)[^\r\n]*\n", code_block)
    if not opening or not closing or not stored_opening:
        return None

    stored_fence = stored_opening.group("fence")
    if not code_block.endswith(stored_fence):
        return None

    body = code_block[stored_opening.end() : -len(stored_fence)]
    collapsed = body.strip("\n").replace("\n", " ")
    longest_backtick_run = max(
        (len(run) for run in re.findall(r"`+", collapsed)),
        default=0,
    )
    delimiter = "`" * max(3, longest_backtick_run + 1)

    span_start = line_start + opening.start()
    span_end = start + len(placeholder) + closing.end()
    return f"{text[:span_start]}{delimiter} {collapsed} {delimiter}{text[span_end:]}"


def _restore_code_macro_block(
    text: str, start: int, placeholder: str, code_block: str
) -> str:
    """Restore one code block using the fence context from markdownify."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end == -1:
        line_end = len(text)

    line_before = text[line_start:start]
    line_after = text[start + len(placeholder) : line_end]
    if line_after.strip():
        inline = _restore_inline_code_macro(text, start, placeholder, code_block)
        if inline is not None:
            return inline
        return text.replace(placeholder, code_block, 1)

    opening_line_end = line_start - 1
    if opening_line_end < 0:
        return text.replace(placeholder, code_block, 1)
    opening_line_start = text.rfind("\n", 0, opening_line_end) + 1
    opening_line = text[opening_line_start:opening_line_end]

    closing_line_start = line_end + 1
    if closing_line_start > len(text):
        return text.replace(placeholder, code_block, 1)
    closing_line_end = text.find("\n", closing_line_start)
    if closing_line_end == -1:
        closing_line_end = len(text)
    closing_line = text[closing_line_start:closing_line_end]

    opening_match = re.search(r"(?P<fence>`{3,})(?P<info>[^\r\n]*)$", opening_line)
    closing_match = re.search(r"(?P<fence>`{3,})[ \t]*$", closing_line)
    stored_opening = re.match(r"(?P<fence>`+)[^\r\n]*\n", code_block)
    if not opening_match or not closing_match or not stored_opening:
        return text.replace(placeholder, code_block, 1)

    stored_fence = stored_opening.group("fence")
    stored_opening_end = stored_opening.end()
    if not code_block.endswith(stored_fence):
        return text.replace(placeholder, code_block, 1)

    body = code_block[stored_opening_end : -len(stored_fence)]
    # The closing line contains only markdownify's continuation prefix and
    # the fence, making it the reliable prefix for every restored body line.
    # The placeholder line can also carry list or quote context, but unlike
    # the closing line it may be adjacent to content in malformed HTML.
    continuation_prefix = closing_line[: closing_match.start()]
    container_prefix = opening_line[: opening_match.start()]
    stored_opening_line = code_block[:stored_opening_end].rstrip("\n")
    restored = (
        f"{container_prefix}{stored_opening_line}\n"
        f"{continuation_prefix}{_prefix_code_block(body, continuation_prefix)}"
        f"{stored_fence}"
    )

    suffix_start = closing_line_end
    return text[:opening_line_start] + restored + text[suffix_start:]


def _restore_code_macro_blocks(markdown_text: str, code_blocks: dict[str, str]) -> str:
    """Replace code-macro placeholders with fenced blocks in Markdown context."""
    for placeholder, code_block in sorted(
        code_blocks.items(),
        key=lambda item: markdown_text.rfind(item[0]),
        reverse=True,
    ):
        placeholder_start = markdown_text.rfind(placeholder)
        if placeholder_start == -1:
            continue
        markdown_text = _restore_code_macro_block(
            markdown_text,
            placeholder_start,
            placeholder,
            code_block,
        )

    return markdown_text


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

            # Process user mentions
            self._process_user_mentions_in_soup(soup, confluence_client)
            self._process_user_profile_macros_in_soup(soup, confluence_client)

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
        for macro in soup.find_all(
            "ac:structured-macro", attrs={"ac:name": ["code", "noformat"]}
        ):
            body = macro.find("ac:plain-text-body")
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

            language_param = macro.find("ac:parameter", attrs={"ac:name": "language"})
            language = language_param.get_text(strip=True) if language_param else ""

            placeholder = f"\x00MCPCODEMACRO{len(code_blocks)}\x00"
            collision = 0
            while placeholder in str(soup):
                collision += 1
                placeholder = f"\x00MCPCODEMACRO{len(code_blocks)}{collision}\x00"

            code_blocks[placeholder] = _fenced_code_block(code_text, language)

            pre_tag = soup.new_tag("pre")
            code_tag = soup.new_tag("code")
            if language:
                code_tag["class"] = f"language-{language}"
            code_tag.string = placeholder
            pre_tag.append(code_tag)
            macro.replace_with(pre_tag)

        return code_blocks

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

        for user_element in user_mentions:
            user_ref = user_element.find("ri:user")
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
                macro_element.replace_with("[User Profile Macro (Malformed)]")
                continue

            user_ref = user_param.find("ri:user")
            if not user_ref:
                logger.debug(
                    "User profile macro's 'user' parameter found without 'ri:user' tag. Replacing with placeholder."
                )
                macro_element.replace_with("[User Profile Macro (Malformed)]")
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
                macro_element.replace_with(replacement_text)
            else:
                fallback_identifier = (
                    user_identifier_for_log
                    if user_identifier_for_log
                    else "unknown_user"
                )
                fallback_text = f"[User Profile: {fallback_identifier}]"
                macro_element.replace_with(fallback_text)
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
                    user_element.replace_with(new_text)
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
        user_element.replace_with(new_text)

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
                    user_element.replace_with(f"@{display_name}")
                    return
            user_element.replace_with(f"@user_{userkey}")
        except Exception as e:
            logger.warning(f"Error processing user mention by userkey: {str(e)}")
            user_element.replace_with(f"@user_{userkey}")

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
                    user_element.replace_with(f"@{display_name}")
                    return
            # Fallback: use the username directly
            user_element.replace_with(f"@{username}")
        except Exception as e:
            logger.warning(f"Error processing user mention by username: {str(e)}")
            user_element.replace_with(f"@{username}")

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
        for ac_image in soup.find_all("ac:image"):
            src = ""
            alt = ""

            # Case 1: ri:attachment (file attached to the page)
            ri_att = ac_image.find("ri:attachment")
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
                ri_url = ac_image.find("ri:url")
                if ri_url:
                    src = ri_url.get("ri:value", "")
                    # Extract filename from URL path for alt text
                    path = urllib.parse.urlparse(src).path
                    alt = path.rsplit("/", 1)[-1] if "/" in path else src
                else:
                    # Unknown inner element
                    logger.warning(
                        "ac:image tag with unsupported child: %s",
                        ac_image,
                    )
                    ac_image.replace_with("[unsupported image]")
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

            ac_image.replace_with(img_tag)

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

        if re.search(r"<[^>]+>", text):
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
