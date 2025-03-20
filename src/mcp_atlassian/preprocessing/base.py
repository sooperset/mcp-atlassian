"""Base preprocessing module."""

import logging
import re
import warnings
from typing import Any, Protocol

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

from ..utils import TextChunker, HTMLProcessor, MarkdownOptimizer

logger = logging.getLogger("mcp-atlassian")


class ConfluenceClient(Protocol):
    """Protocol for Confluence client."""

    def get_user_details_by_accountid(self, account_id: str) -> dict[str, Any]:
        """Get user details by account ID."""
        ...


class BasePreprocessor:
    """Base class for text preprocessing operations."""

    def __init__(
        self, base_url: str = "", confluence_client: ConfluenceClient | None = None
    ) -> None:
        """
        Initialize the base text preprocessor.

        Args:
            base_url: Base URL for API server
            confluence_client: Optional Confluence client for user lookups
        """
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.confluence_client = confluence_client
        self.text_chunker = TextChunker(chunk_size=10000, overlap=500)
        self.large_text_threshold = 20000  # Textos maiores que isso usarão processamento incremental

    def process_html_content(
        self, html_content: str, space_key: str = ""
    ) -> tuple[str, str]:
        """
        Process HTML content to replace user refs and page links.

        Args:
            html_content: The HTML content to process
            space_key: Optional space key for context

        Returns:
            Tuple of (processed_html, processed_markdown)
        """
        try:
            # Usa processamento incremental para conteúdo grande
            if len(html_content) > self.large_text_threshold:
                return self._process_large_html_content(html_content, space_key)
                
            # Processamento normal para conteúdos pequenos
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Process user mentions
            self._process_user_mentions_in_soup(soup)
            
            # Convert to string and markdown
            processed_html = str(soup)
            processed_markdown = md(processed_html)
            
            # Otimiza o markdown
            processed_markdown = MarkdownOptimizer.remove_empty_markdown_links(processed_markdown)
            processed_markdown = MarkdownOptimizer.optimize_markdown_tables(processed_markdown)
            
            return processed_html, processed_markdown

        except Exception as e:
            logger.error(f"Error in process_html_content: {str(e)}")
            # Fallback para processamento simples em caso de erro
            plain_text = HTMLProcessor.extract_text_from_html(html_content)
            return html_content, plain_text

    def _process_large_html_content(
        self, html_content: str, space_key: str = ""
    ) -> tuple[str, str]:
        """
        Process large HTML content incrementally.

        Args:
            html_content: The HTML content to process
            space_key: Optional space key for context

        Returns:
            Tuple of (processed_html, processed_markdown)
        """
        # Divide o HTML em blocos baseados em elementos estruturais
        # Tentamos dividir em <div>, <p> ou outros elementos de bloco
        chunks = self._split_html_by_blocks(html_content)
        
        # Processa cada chunk separadamente
        processed_html_chunks = []
        for chunk in chunks:
            try:
                soup = BeautifulSoup(chunk, "html.parser")
                self._process_user_mentions_in_soup(soup)
                processed_html_chunks.append(str(soup))
            except Exception as e:
                logger.warning(f"Error processing HTML chunk: {str(e)}")
                # Em caso de erro, mantém o chunk original
                processed_html_chunks.append(chunk)
        
        # Reconstrói o HTML
        processed_html = ''.join(processed_html_chunks)
        
        # Converte para markdown em chunks
        def convert_to_md(html_chunk):
            return md(html_chunk)
        
        processed_markdown = self.text_chunker.process_text_in_chunks(processed_html, convert_to_md)
        
        # Otimiza o markdown
        processed_markdown = MarkdownOptimizer.remove_empty_markdown_links(processed_markdown)
        
        return processed_html, processed_markdown

    def _split_html_by_blocks(self, html_content: str) -> list[str]:
        """
        Divide o conteúdo HTML em blocos estruturais para processamento incremental.
        
        Args:
            html_content: Conteúdo HTML a ser dividido
            
        Returns:
            Lista de blocos HTML
        """
        # Tenta dividir o HTML em grandes blocos estruturais
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Prioriza divisão pelos principais elementos de bloco
            blocks = []
            for elem in soup.find_all(['div', 'section', 'article', 'header', 'footer', 'main', 'nav']):
                if len(str(elem)) > 100:  # Ignora blocos muito pequenos
                    blocks.append(str(elem))
                    
            # Se encontrou blocos suficientes, retorna
            if blocks and sum(len(b) for b in blocks) > 0.8 * len(html_content):
                return blocks
                
            # Segunda tentativa: divide por parágrafos e outros elementos menores
            blocks = []
            for elem in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'table']):
                blocks.append(str(elem))
                
            # Se encontrou blocos suficientes, retorna
            if blocks and sum(len(b) for b in blocks) > 0.6 * len(html_content):
                return blocks
        except Exception as e:
            logger.warning(f"Error splitting HTML by blocks: {str(e)}")
            
        # Fallback: divide o texto por tamanho
        return self.text_chunker.chunk_text(html_content)

    def _process_user_mentions_in_soup(self, soup: BeautifulSoup) -> None:
        """
        Process user mentions in BeautifulSoup object.

        Args:
            soup: BeautifulSoup object containing HTML
        """
        # Find all ac:link elements that might contain user mentions
        user_mentions = soup.find_all("ac:link")

        for user_element in user_mentions:
            user_ref = user_element.find("ri:user")
            if user_ref and user_ref.get("ri:account-id"):
                # Case 1: Direct user reference without link-body
                account_id = user_ref.get("ri:account-id")
                if isinstance(account_id, str):
                    self._replace_user_mention(user_element, account_id)
                    continue

            # Case 2: User reference with link-body containing @
            link_body = user_element.find("ac:link-body")
            if link_body and "@" in link_body.get_text(strip=True):
                user_ref = user_element.find("ri:user")
                if user_ref and user_ref.get("ri:account-id"):
                    account_id = user_ref.get("ri:account-id")
                    if isinstance(account_id, str):
                        self._replace_user_mention(user_element, account_id)

    def _replace_user_mention(self, user_element: Tag, account_id: str) -> None:
        """
        Replace a user mention with the user's display name.

        Args:
            user_element: The HTML element containing the user mention
            account_id: The user's account ID
        """
        try:
            # Only attempt to get user details if we have a valid confluence client
            if self.confluence_client is not None:
                user_details = self.confluence_client.get_user_details_by_accountid(
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

    def _convert_html_to_markdown(self, text: str) -> str:
        """Convert HTML content to markdown if needed."""
        if not text:
            return ""
            
        # Verifica se o texto contém HTML
        if not re.search(r"<[^>]+>", text):
            return text
            
        # Para textos pequenos, usa o método padrão
        if len(text) <= self.large_text_threshold:
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    soup = BeautifulSoup(f"<div>{text}</div>", "html.parser")
                    html = str(soup.div.decode_contents()) if soup.div else text
                    return md(html)
            except Exception as e:
                logger.warning(f"Error converting HTML to markdown: {str(e)}")
                return text
        
        # Para textos grandes, usa processamento incremental
        return self.text_chunker.process_text_in_chunks(
            text,
            lambda chunk: md(f"<div>{chunk}</div>")
        )
