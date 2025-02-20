import logging
import re
import warnings

from bs4 import BeautifulSoup
from markdownify import markdownify as md

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
        2. Converting HTML/wiki markup to markdown
        """
        if not text:
            return ""

        # Process user mentions
        mention_pattern = r"\[~accountid:(.*?)\]"
        text = self._process_mentions(text, mention_pattern)

        # Process Jira smart links
        text = self._process_smart_links(text)

        # Convert HTML to markdown if needed
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
