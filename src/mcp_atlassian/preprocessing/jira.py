"""Jira-specific text preprocessing module."""

import logging
import re
from typing import Any, Match, Optional, Pattern, cast

from bs4 import BeautifulSoup, element

from ..utils import HTMLProcessor, MarkdownOptimizer, TextChunker
from .base import BasePreprocessor

logger = logging.getLogger("mcp-atlassian")


class JiraPreprocessor(BasePreprocessor):
    """
    Implementation of text preprocessor for Jira.

    Handles Jira-specific markup, user mentions, and links.
    """

    # Regular expressions for Jira text processing
    JIRA_CODE_BLOCK_RE = re.compile(r"\{code(?::([a-z]+))?\}(.*?)\{code\}", re.DOTALL)
    JIRA_PANEL_RE = re.compile(r"\{panel(?::title=([^|]+))?\}(.*?)\{panel\}", re.DOTALL)
    JIRA_SMART_LINK_RE = re.compile(
        r"\[([^|]+)\|(?:https?://)?([a-zA-Z0-9\-._~:/?\#\[\]@!$&'()*+,;=]+)\]"
    )
    JIRA_MENTION_RE = re.compile(r"\[~accountid:([a-zA-Z0-9\-]+)\]")
    
    # Memoização para evitar reprocessamento de padrões frequentes
    _memo_cache = {}
    _memo_max_size = 1000

    def __init__(
        self, base_url: str = "", jira_client: Optional[Any] = None
    ) -> None:
        """
        Initialize Jira text preprocessor.

        Args:
            base_url: Base URL for Jira API server
            jira_client: Optional Jira client for user lookups
        """
        super().__init__(base_url, jira_client)
        self.text_chunker = TextChunker(chunk_size=5000, overlap=200)
        self.large_text_threshold = 10000  # Jira textos costumam ser menores que Confluence

    def clean_jira_text(self, jira_text: str) -> str:
        """
        Process Jira text to standard markdown/HTML.

        Args:
            jira_text: Raw Jira markup text

        Returns:
            Processed text
        """
        # Retorna texto vazio para entrada vazia
        if not jira_text:
            return ""
            
        # Processamento incremental para textos grandes
        if len(jira_text) > self.large_text_threshold:
            return self._process_large_jira_text(jira_text)
        
        # Otimiza o uso de memória verificando se já processamos este texto antes
        cache_key = hash(jira_text)
        if cache_key in self._memo_cache:
            return self._memo_cache[cache_key]
            
        # Processamento normal para textos pequenos
        text = jira_text

        # Code blocks
        text = self._process_code_blocks(text)

        # Panels
        text = self._process_panels(text)

        # Smart links
        text = self._process_smart_links(text)

        # Mentions
        text = self._process_mentions(text)

        # Armazena na cache, limitando o tamanho
        if len(self._memo_cache) > self._memo_max_size:
            # Limpa metade do cache quando chega ao limite
            keys_to_remove = list(self._memo_cache.keys())[:self._memo_max_size // 2]
            for key in keys_to_remove:
                del self._memo_cache[key]
                
        self._memo_cache[cache_key] = text
        return text
        
    def _process_large_jira_text(self, jira_text: str) -> str:
        """
        Processa textos grandes do Jira incrementalmente.
        
        Args:
            jira_text: Texto bruto do Jira
            
        Returns:
            Texto processado
        """
        # Os blocos de código e painéis podem se estender por múltiplas linhas
        # Precisamos identificá-los antes de dividir o texto
        
        # Primeiro, identificamos e protegemos blocos especiais
        code_blocks = []
        panels = []
        
        def protect_code_blocks(match: Match) -> str:
            code_blocks.append((match.group(1) or "", match.group(2)))
            return f"__CODE_BLOCK_{len(code_blocks)-1}__"
            
        def protect_panels(match: Match) -> str:
            panels.append((match.group(1) or "", match.group(2)))
            return f"__PANEL_{len(panels)-1}__"
        
        # Substitui blocos de código e painéis por marcadores
        protected_text = self.JIRA_CODE_BLOCK_RE.sub(protect_code_blocks, jira_text)
        protected_text = self.JIRA_PANEL_RE.sub(protect_panels, protected_text)
        
        # Divide o texto em chunks para processamento
        chunks = self.text_chunker.chunk_text(protected_text, preserve_newlines=True)
        
        # Processa cada chunk
        processed_chunks = []
        for chunk in chunks:
            # Processa links e menções
            processed_chunk = self._process_smart_links(chunk)
            processed_chunk = self._process_mentions(processed_chunk)
            processed_chunks.append(processed_chunk)
            
        # Junta os chunks processados
        result_text = "".join(processed_chunks)
        
        # Restaura os blocos de código
        for i, (lang, code) in enumerate(code_blocks):
            lang_attr = f":{lang}" if lang else ""
            result_text = result_text.replace(
                f"__CODE_BLOCK_{i}__", 
                f"```{lang}\n{code}\n```"
            )
            
        # Restaura os painéis
        for i, (title, content) in enumerate(panels):
            title_attr = f"## {title}\n\n" if title else ""
            result_text = result_text.replace(
                f"__PANEL_{i}__",
                f"{title_attr}{content}\n"
            )
            
        return result_text

    def _process_code_blocks(self, text: str) -> str:
        """
        Process Jira code blocks into markdown format.

        Args:
            text: Input text

        Returns:
            Text with code blocks converted to markdown
        """
        return self.JIRA_CODE_BLOCK_RE.sub(
            lambda m: f"```{m.group(1) or ''}\n{m.group(2)}\n```", text
        )

    def _process_panels(self, text: str) -> str:
        """
        Process Jira panels into markdown format.

        Args:
            text: Input text

        Returns:
            Text with panels converted to markdown
        """
        return self.JIRA_PANEL_RE.sub(
            lambda m: ("## " + m.group(1) + "\n\n" if m.group(1) else "") + m.group(2) + "\n",
            text,
        )

    def _process_smart_links(self, text: str) -> str:
        """
        Process Jira smart links into markdown format.

        Args:
            text: Input text

        Returns:
            Text with smart links converted to markdown
        """
        return self.JIRA_SMART_LINK_RE.sub(r"[\1](https://\2)", text)

    def _process_mentions(self, text: str) -> str:
        """
        Process Jira user mentions with real names if available.

        Args:
            text: Input text

        Returns:
            Text with user mentions processed
        """
        
        def replace_mention(m: Match) -> str:
            account_id = m.group(1)
            try:
                if self.confluence_client:
                    user_details = self.confluence_client.get_user_details_by_accountid(
                        account_id
                    )
                    if user_details and "displayName" in user_details:
                        return f"@{user_details['displayName']}"
            except Exception as e:
                logger.warning(f"Error getting user details: {str(e)}")
            
            # Fallback
            return f"@user_{account_id}"
            
        return self.JIRA_MENTION_RE.sub(replace_mention, text)

    def process_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        """
        Process all relevant text fields in a Jira issue.

        Args:
            fields: Dict of fields from Jira

        Returns:
            Dict with processed text fields
        """
        processed = fields.copy()
        
        # Processa descrição
        if description := processed.get("description"):
            processed["description"] = self.clean_jira_text(description)
            # Gera um snippet/resumo da descrição
            if len(processed["description"]) > 300:
                processed["description_summary"] = HTMLProcessor.generate_excerpt(
                    processed["description"], max_length=300
                )
                
        # Processa comentários
        if comments := processed.get("comment", {}).get("comments", []):
            for comment in comments:
                if body := comment.get("body"):
                    comment["body"] = self.clean_jira_text(body)
                    # Gera um snippet/resumo de cada comentário
                    if len(comment["body"]) > 200:
                        comment["body_summary"] = HTMLProcessor.generate_excerpt(
                            comment["body"], max_length=200
                        )
        
        # Processa mensagens de trabalho (worklog)
        if worklogs := processed.get("worklog", {}).get("worklogs", []):
            for worklog in worklogs:
                if comment := worklog.get("comment"):
                    worklog["comment"] = self.clean_jira_text(comment)
        
        return processed

    def process_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        """
        Process a Jira issue dictionary.

        Args:
            issue: Dict representing a Jira issue

        Returns:
            Issue with processed text fields
        """
        processed_issue = issue.copy()
        
        # Processa campos do issue
        if "fields" in processed_issue:
            processed_issue["fields"] = self.process_fields(processed_issue["fields"])
            
        # Processa changelog se disponível
        if "changelog" in processed_issue:
            changelog = processed_issue["changelog"]
            if "histories" in changelog:
                for history in changelog["histories"]:
                    for item in history.get("items", []):
                        # Processa campos de texto em mudanças
                        for field_name in ["toString", "fromString"]:
                            if field_name in item and isinstance(item[field_name], str):
                                # Só processa texto que parece ser formatado
                                if "{" in item[field_name] or "[" in item[field_name]:
                                    item[field_name] = self.clean_jira_text(item[field_name])
                                    
        return processed_issue

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
            r"^h([0-6])\.(.*)$",
            lambda match: "#" * int(match.group(1)) + match.group(2),
            output,
            flags=re.MULTILINE,
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
        output = re.sub(
            r"\{code(?::([a-z]+))?\}([\s\S]*?)\{code\}",
            r"```\1\n\2\n```",
            output,
            flags=re.MULTILINE,
        )

        # No format
        output = re.sub(r"\{noformat\}([\s\S]*?)\{noformat\}", r"```\n\1\n```", output)

        # Quote blocks
        output = re.sub(
            r"\{quote\}([\s\S]*)\{quote\}",
            lambda match: "\n".join(
                [f"> {line}" for line in match.group(1).split("\n")]
            ),
            output,
            flags=re.MULTILINE,
        )

        # Images with alt text
        output = re.sub(
            r"!([^|\n\s]+)\|([^\n!]*)alt=([^\n!\,]+?)(,([^\n!]*))?!",
            r"![\3](\1)",
            output,
        )

        # Images with other parameters (ignore them)
        output = re.sub(r"!([^|\n\s]+)\|([^\n!]*)!", r"![](\1)", output)

        # Images without parameters
        output = re.sub(r"!([^\n\s!]+)!", r"![](\1)", output)

        # Links
        output = re.sub(r"\[([^|]+)\|(.+?)\]", r"[\1](\2)", output)
        output = re.sub(r"\[(.+?)\]([^\(]+)", r"<\1>\2", output)

        # Colored text
        output = re.sub(
            r"\{color:([^}]+)\}([\s\S]*?)\{color\}",
            r"<span style=\"color:\1\">\2</span>",
            output,
            flags=re.MULTILINE,
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
        def save_code_block(match: re.Match) -> str:
            """
            Process and save a code block.

            Args:
                match: Regex match object containing the code block

            Returns:
                Jira-formatted code block
            """
            syntax = match.group(1) or ""
            content = match.group(2)
            code = "{code"
            if syntax:
                code += ":" + syntax
            code += "}" + content + "{code}"
            code_blocks.append(code)
            return str(code)  # Ensure we return a string

        # Extract inline code
        def save_inline_code(match: re.Match) -> str:
            """
            Process and save inline code.

            Args:
                match: Regex match object containing the inline code

            Returns:
                Jira-formatted inline code
            """
            content = match.group(1)
            code = "{{" + content + "}}"
            inline_codes.append(code)
            return str(code)  # Ensure we return a string

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
            r"^([#]+)(.*?)$",
            lambda match: f"h{len(match.group(1))}." + match.group(2),
            output,
            flags=re.MULTILINE,
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
            lambda match: (
                "* " + match.group(2)
                if not match.group(1)
                else "  " * (len(match.group(1)) // 2) + "* " + match.group(2)
            ),
            output,
            flags=re.MULTILINE,
        )

        # Multi-level numbered list
        output = re.sub(
            r"^(\s+)1\. (.*)$",
            lambda match: "#" * (int(len(match.group(1)) / 4) + 2)
            + " "
            + match.group(2),
            output,
            flags=re.MULTILINE,
        )

        # HTML formatting tags to Jira markup
        tag_map = {"cite": "??", "del": "-", "ins": "+", "sup": "^", "sub": "~"}

        for tag, replacement in tag_map.items():
            output = re.sub(
                rf"<{tag}>(.*?)<\/{tag}>", rf"{replacement}\1{replacement}", output
            )

        # Colored text
        output = re.sub(
            r"<span style=\"color:(#[^\"]+)\">([\s\S]*?)</span>",
            r"{color:\1}\2{color}",
            output,
            flags=re.MULTILINE,
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
