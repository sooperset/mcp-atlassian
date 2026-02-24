"""Base preprocessing module."""

import logging
import re
import urllib.parse
import warnings
from typing import Any, Protocol

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

logger = logging.getLogger("mcp-atlassian")


class ConfluenceClient(Protocol):
    """Protocol for Confluence client."""

    def get_user_details_by_accountid(self, account_id: str) -> dict[str, Any]:
        """Get user details by account ID."""
        ...

    def get_user_details_by_username(self, username: str) -> dict[str, Any]:
        """Get user details by username (for Server/DC compatibility)."""
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

            # Process Confluence image tags
            self._process_images_in_soup(soup, content_id, attachments)

            # Convert to string and markdown
            processed_html = str(soup)
            processed_markdown = md(processed_html)

            return processed_html, processed_markdown

        except Exception as e:
            logger.error(f"Error in process_html_content: {str(e)}")
            raise

    def _process_user_mentions_in_soup(
        self, soup: BeautifulSoup, confluence_client: ConfluenceClient | None = None
    ) -> None:
        """
        Process user mentions in BeautifulSoup object.

        Args:
            soup: BeautifulSoup object containing HTML
            confluence_client: Optional Confluence client for user lookups
        """
        # Find all ac:link elements that might contain user mentions
        user_mentions = soup.find_all("ac:link")

        for user_element in user_mentions:
            user_ref = user_element.find("ri:user")
            if user_ref and user_ref.get("ri:account-id"):
                # Case 1: Direct user reference without link-body
                account_id = user_ref.get("ri:account-id")
                if isinstance(account_id, str):
                    self._replace_user_mention(
                        user_element, account_id, confluence_client
                    )
                    continue

            # Case 2: User reference with link-body containing @
            link_body = user_element.find("ac:link-body")
            if link_body and "@" in link_body.get_text(strip=True):
                user_ref = user_element.find("ri:user")
                if user_ref and user_ref.get("ri:account-id"):
                    account_id = user_ref.get("ri:account-id")
                    if isinstance(account_id, str):
                        self._replace_user_mention(
                            user_element, account_id, confluence_client
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

            user_identifier_for_log = account_id or userkey
            display_name = None

            if confluence_client and user_identifier_for_log:
                try:
                    if account_id and isinstance(account_id, str):
                        user_details = confluence_client.get_user_details_by_accountid(
                            account_id
                        )
                        display_name = user_details.get("displayName")
                    elif userkey and isinstance(userkey, str):
                        # For Confluence Server/DC, userkey might be the username
                        user_details = confluence_client.get_user_details_by_username(
                            userkey
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

                # Try attachment list lookup first
                url = self._find_attachment_url(filename, attachments)
                if url:
                    # Prepend base_url if relative path
                    if url.startswith("/") and self.base_url:
                        src = f"{self.base_url}{url}"
                    else:
                        src = url
                elif content_id:
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
        """Convert HTML content to markdown if needed."""
        if re.search(r"<[^>]+>", text):
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    soup = BeautifulSoup(f"<div>{text}</div>", "html.parser")
                    html = str(soup.div.decode_contents()) if soup.div else text
                    text = md(html)
            except Exception as e:
                logger.warning(f"Error converting HTML to markdown: {str(e)}")
        return text
