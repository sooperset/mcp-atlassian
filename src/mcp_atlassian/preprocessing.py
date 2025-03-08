import logging
import re
import tempfile
import warnings
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from md2conf.converter import (
    ConfluenceConverterOptions,
    ConfluenceStorageFormatConverter,
    elements_from_string,
    elements_to_string,
    markdown_to_html,
)

logger = logging.getLogger("mcp-atlassian")


class TextPreprocessor:
    """Handles text preprocessing for Confluence and Jira content."""

    def __init__(self, base_url: str, confluence_client=None):
        self.base_url = base_url.rstrip("/")
        self.confluence_client = confluence_client

    def process_html_content(self, html_content: str, space_key: str = "") -> tuple[str, str]:
        """Process HTML content to replace user refs and page links."""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Process user mentions
            user_mentions = soup.find_all("ri:user")
            for user in user_mentions:
                account_id = user.get("ri:account-id")
                if account_id and self.confluence_client:
                    try:
                        # Fetch user info using the Confluence API
                        user_info = self.confluence_client.get_user_details_by_accountid(account_id)
                        display_name = user_info.get("displayName", account_id)

                        # Replace the entire ac:link structure with @mention
                        link_tag = user.find_parent("ac:link")
                        if link_tag:
                            link_tag.replace_with(f"@{display_name}")
                    except Exception as e:
                        logger.warning(f"Could not fetch user info for {account_id}: {e}")
                        # Fallback: just use the account ID
                        link_tag = user.find_parent("ac:link")
                        if link_tag:
                            link_tag.replace_with(f"@user_{account_id}")

            processed_html = str(soup)
            processed_markdown = md(processed_html)

            return processed_html, processed_markdown

        except Exception as e:
            logger.error(f"Error in process_html_content: {str(e)}")
            raise

    def clean_jira_text(self, text: str) -> str:
        """
        Clean Jira text content by:
        1. Processing user mentions and links
        2. Converting Jira markup to markdown
        3. Converting HTML/wiki markup to markdown
        """
        if not text:
            return ""

        # Process user mentions
        mention_pattern = r"\[~accountid:(.*?)\]"
        text = self._process_mentions(text, mention_pattern)

        # Process Jira smart links
        text = self._process_smart_links(text)

        # First convert any Jira markup to Markdown
        text = self.jira_to_markdown(text)

        # Then convert any remaining HTML to markdown
        text = self._convert_html_to_markdown(text)

        return text.strip()

    def _process_mentions(self, text: str, pattern: str) -> str:
        """Process user mentions in text."""
        mentions = re.findall(pattern, text)
        for account_id in mentions:
            try:
                # Note: This is a placeholder - actual user fetching should be injected
                display_name = f"User:{account_id}"
                text = text.replace(f"[~accountid:{account_id}]", display_name)
            except Exception as e:
                logger.error(f"Error getting user info for {account_id}: {str(e)}")
        return text

    def _process_smart_links(self, text: str) -> str:
        """Process Jira/Confluence smart links."""
        # Pattern matches: [text|url|smart-link]
        link_pattern = r"\[(.*?)\|(.*?)\|smart-link\]"
        matches = re.finditer(link_pattern, text)

        for match in matches:
            full_match = match.group(0)
            link_text = match.group(1)
            link_url = match.group(2)

            # Extract issue key if it's a Jira issue link
            issue_key_match = re.search(r"browse/([A-Z]+-\d+)", link_url)
            # Check if it's a Confluence wiki link
            confluence_match = re.search(r"wiki/spaces/.+?/pages/\d+/(.+?)(?:\?|$)", link_url)

            if issue_key_match:
                issue_key = issue_key_match.group(1)
                clean_url = f"{self.base_url}/browse/{issue_key}"
                text = text.replace(full_match, f"[{issue_key}]({clean_url})")
            elif confluence_match:
                url_title = confluence_match.group(1)
                readable_title = url_title.replace("+", " ")
                readable_title = re.sub(r"^[A-Z]+-\d+\s+", "", readable_title)
                text = text.replace(full_match, f"[{readable_title}]({link_url})")
            else:
                clean_url = link_url.split("?")[0]
                text = text.replace(full_match, f"[{link_text}]({clean_url})")

        return text

    def _convert_html_to_markdown(self, text: str) -> str:
        """Convert HTML content to markdown if needed."""
        if re.search(r"<[^>]+>", text):
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    soup = BeautifulSoup(f"<div>{text}</div>", "html.parser")
                    html = str(soup.div.decode_contents()) if soup.div else text
                    text = md(html)
            except Exception as e:
                logger.warning(f"Error converting HTML to markdown: {e}")
        return text

    def jira_to_markdown(self, input_text: str) -> str:
        """
        Convert Jira markup to Markdown format.

        Args:
            input_text: Text in Jira markup format

        Returns:
            Text in Markdown format
        """
        if not input_text:
            return ""

        # Block quotes
        output = re.sub(r"^bq\.(.*?)$", r"> \1\n", input_text, flags=re.MULTILINE)

        # Text formatting (bold, italic)
        output = re.sub(
            r"([*_])(.*?)\1",
            lambda match: ("**" if match.group(1) == "*" else "*")
            + match.group(2)
            + ("**" if match.group(1) == "*" else "*"),
            output,
        )

        # Multi-level numbered list
        output = re.sub(
            r"^((?:#|-|\+|\*)+) (.*)$",
            lambda match: self._convert_jira_list_to_markdown(match),
            output,
            flags=re.MULTILINE,
        )

        # Headers
        output = re.sub(
            r"^h([0-6])\.(.*)$", lambda match: "#" * int(match.group(1)) + match.group(2), output, flags=re.MULTILINE
        )

        # Inline code
        output = re.sub(r"\{\{([^}]+)\}\}", r"`\1`", output)

        # Citation
        output = re.sub(r"\?\?((?:.[^?]|[^?].)+)\?\?", r"<cite>\1</cite>", output)

        # Inserted text
        output = re.sub(r"\+([^+]*)\+", r"<ins>\1</ins>", output)

        # Superscript
        output = re.sub(r"\^([^^]*)\^", r"<sup>\1</sup>", output)

        # Subscript
        output = re.sub(r"~([^~]*)~", r"<sub>\1</sub>", output)

        # Strikethrough
        output = re.sub(r"-([^-]*)-", r"-\1-", output)

        # Code blocks with optional language specification
        output = re.sub(r"\{code(?::([a-z]+))?\}([\s\S]*?)\{code\}", r"```\1\n\2\n```", output, flags=re.MULTILINE)

        # No format
        output = re.sub(r"\{noformat\}([\s\S]*?)\{noformat\}", r"```\n\1\n```", output)

        # Quote blocks
        output = re.sub(
            r"\{quote\}([\s\S]*)\{quote\}",
            lambda match: "\n".join([f"> {line}" for line in match.group(1).split("\n")]),
            output,
            flags=re.MULTILINE,
        )

        # Images with alt text
        output = re.sub(r"!([^|\n\s]+)\|([^\n!]*)alt=([^\n!\,]+?)(,([^\n!]*))?!", r"![\3](\1)", output)

        # Images with other parameters (ignore them)
        output = re.sub(r"!([^|\n\s]+)\|([^\n!]*)!", r"![](\1)", output)

        # Images without parameters
        output = re.sub(r"!([^\n\s!]+)!", r"![](\1)", output)

        # Links
        output = re.sub(r"\[([^|]+)\|(.+?)\]", r"[\1](\2)", output)
        output = re.sub(r"\[(.+?)\]([^\(]+)", r"<\1>\2", output)

        # Colored text
        output = re.sub(
            r"\{color:([^}]+)\}([\s\S]*?)\{color\}", r"<span style=\"color:\1\">\2</span>", output, flags=re.MULTILINE
        )

        # Convert Jira table headers (||) to markdown table format
        lines = output.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            if "||" in line:
                # Replace Jira table headers
                lines[i] = lines[i].replace("||", "|")

                # Add a separator line for markdown tables
                header_cells = lines[i].count("|") - 1
                if header_cells > 0:
                    separator_line = "|" + "---|" * header_cells
                    lines.insert(i + 1, separator_line)
                    i += 1  # Skip the newly inserted line in next iteration

            i += 1

        # Rejoin the lines
        output = "\n".join(lines)

        return output

    def markdown_to_jira(self, input_text: str) -> str:
        """
        Convert Markdown syntax to Jira markup syntax.

        Args:
            input_text: Text in Markdown format

        Returns:
            Text in Jira markup format
        """
        if not input_text:
            return ""

        # Save code blocks to prevent recursive processing
        code_blocks = []
        inline_codes = []

        # Extract code blocks
        def save_code_block(match):
            syntax = match.group(1) or ""
            content = match.group(2)
            code = "{code"
            if syntax:
                code += ":" + syntax
            code += "}" + content + "{code}"
            code_blocks.append(code)
            return code  # Return the actual code block instead of a placeholder

        # Extract inline code
        def save_inline_code(match):
            content = match.group(1)
            code = "{{" + content + "}}"
            inline_codes.append(code)
            return code  # Return the actual inline code instead of a placeholder

        # Save code sections temporarily
        output = re.sub(r"```(\w*)\n([\s\S]+?)```", save_code_block, input_text)
        output = re.sub(r"`([^`]+)`", save_inline_code, output)

        # Headers with = or - underlines
        output = re.sub(
            r"^(.*?)\n([=-])+$",
            lambda match: f"h{1 if match.group(2)[0] == '=' else 2}. {match.group(1)}",
            output,
            flags=re.MULTILINE,
        )

        # Headers with # prefix
        output = re.sub(
            r"^([#]+)(.*?)$", lambda match: f"h{len(match.group(1))}." + match.group(2), output, flags=re.MULTILINE
        )

        # Bold and italic
        output = re.sub(
            r"([*_]+)(.*?)\1",
            lambda match: ("_" if len(match.group(1)) == 1 else "*")
            + match.group(2)
            + ("_" if len(match.group(1)) == 1 else "*"),
            output,
        )

        # Multi-level bulleted list
        output = re.sub(
            r"^(\s*)- (.*)$",
            lambda match: "* " + match.group(2)
            if not match.group(1)
            else "  " * (len(match.group(1)) // 2) + "* " + match.group(2),
            output,
            flags=re.MULTILINE,
        )

        # Multi-level numbered list
        output = re.sub(
            r"^(\s+)1\. (.*)$",
            lambda match: "#" * (int(len(match.group(1)) / 4) + 2) + " " + match.group(2),
            output,
            flags=re.MULTILINE,
        )

        # HTML formatting tags to Jira markup
        tag_map = {"cite": "??", "del": "-", "ins": "+", "sup": "^", "sub": "~"}

        for tag, replacement in tag_map.items():
            output = re.sub(rf"<{tag}>(.*?)<\/{tag}>", rf"{replacement}\1{replacement}", output)

        # Colored text
        output = re.sub(
            r"<span style=\"color:(#[^\"]+)\">([\s\S]*?)</span>", r"{color:\1}\2{color}", output, flags=re.MULTILINE
        )

        # Strikethrough
        output = re.sub(r"~~(.*?)~~", r"-\1-", output)

        # Images without alt text
        output = re.sub(r"!\[\]\(([^)\n\s]+)\)", r"!\1!", output)

        # Images with alt text
        output = re.sub(r"!\[([^\]\n]+)\]\(([^)\n\s]+)\)", r"!\2|alt=\1!", output)

        # Links
        output = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"[\1|\2]", output)
        output = re.sub(r"<([^>]+)>", r"[\1]", output)

        # Convert markdown tables to Jira table format
        lines = output.split("\n")
        i = 0
        while i < len(lines):
            if i < len(lines) - 1 and re.match(r"\|[-\s|]+\|", lines[i + 1]):
                # Convert header row to Jira format
                lines[i] = lines[i].replace("|", "||")
                # Remove the separator line
                lines.pop(i + 1)
            i += 1

        # Rejoin the lines
        output = "\n".join(lines)

        return output

    def _convert_jira_list_to_markdown(self, match) -> str:
        """Helper method to convert Jira lists to Markdown format."""
        jira_bullets = match.group(1)
        content = match.group(2)

        # Calculate indentation level based on number of symbols
        indent_level = len(jira_bullets) - 1
        indent = " " * (indent_level * 2)

        # Determine the marker based on the last character
        last_char = jira_bullets[-1]
        if last_char == "#":
            prefix = "1."
        else:
            prefix = "-"

        return f"{indent}{prefix} {content}"


def markdown_to_confluence_storage(markdown_content):
    """
    Convert Markdown content to Confluence storage format (XHTML)

    This function uses the markdown-to-confluence library to properly convert
    Markdown to Confluence storage format. The library handles proper formatting of:
    - Headings with anchors
    - Text formatting (bold, italic, etc.)
    - Lists (ordered and unordered)
    - Code blocks with syntax highlighting
    - Tables and other Markdown elements

    Args:
        markdown_content: The markdown content to convert

    Returns:
        String in Confluence storage format (XHTML with Confluence macros)
    """
    try:
        # First convert markdown to HTML
        html_content = markdown_to_html(markdown_content)

        # Create a temporary directory for any potential attachments
        temp_dir = tempfile.mkdtemp()

        try:
            # Parse the HTML into an element tree
            root = elements_from_string(html_content)

            # Create converter options
            options = ConfluenceConverterOptions(ignore_invalid_url=True, heading_anchors=True, render_mermaid=False)

            # Create a converter
            converter = ConfluenceStorageFormatConverter(
                options=options, path=Path(temp_dir) / "temp.md", root_dir=Path(temp_dir), page_metadata={}
            )

            # Transform the HTML to Confluence storage format
            converter.visit(root)

            # Convert the element tree back to a string
            storage_format = elements_to_string(root)

            return storage_format
        finally:
            # Clean up the temporary directory
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"Error converting markdown to Confluence storage format: {e}")
        logger.exception(e)

        # Fall back to a simpler method if the conversion fails
        html_content = markdown_to_html(markdown_content)

        # Use a different approach that doesn't rely on the HTML macro
        # This creates a proper Confluence storage format document
        storage_format = f"""<p>{html_content}</p>"""

        return storage_format
