"""
Confluence Markdown Converter
Handles conversion between markdown and Confluence storage format.
Adapted to mcp-atlassian architecture patterns.
"""

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import yaml

from ...exceptions import MCPAtlassianError

logger = logging.getLogger("mcp-atlassian.confluence.markdown_sync")


class MarkdownSyncError(MCPAtlassianError):
    """Error specific to markdown sync operations."""
    
    def __init__(self, message: str, code: str = "MARKDOWN_SYNC_ERROR", details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass
class ParsedMarkdownFile:
    """Represents a parsed markdown file with all extracted information."""
    file_path: str
    title: str
    frontmatter: Dict[str, Any]
    markdown_content: str
    confluence_content: str
    content_hash: str


class FrontmatterParser:
    """
    Parses YAML frontmatter from markdown files.
    
    Follows mcp-atlassian error handling patterns.
    """
    
    def parse(self, content: str) -> Tuple[Dict[str, Any], str]:
        """Extract frontmatter and return (frontmatter_dict, remaining_content)."""
        
        if not content.startswith('---\n'):
            return {}, content
            
        try:
            # Find the end of frontmatter
            end_marker = content.find('\n---\n', 4)
            if end_marker == -1:
                return {}, content
                
            frontmatter_yaml = content[4:end_marker]
            remaining_content = content[end_marker + 5:]
            
            frontmatter_dict = yaml.safe_load(frontmatter_yaml) or {}
            
            logger.debug(f"Parsed frontmatter: {frontmatter_dict}")
            return frontmatter_dict, remaining_content
            
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse YAML frontmatter: {e}")
            return {}, content
        except Exception as e:
            logger.error(f"Unexpected error parsing frontmatter: {e}")
            raise MarkdownSyncError(
                f"Failed to parse frontmatter: {e}",
                code="FRONTMATTER_PARSE_ERROR",
                details={"error": str(e)}
            )


class MarkdownConverter:
    """
    Converts markdown content to Confluence storage format and vice versa.
    
    Integrates with mcp-atlassian client patterns and error handling.
    """
    
    def __init__(self):
        self.frontmatter_parser = FrontmatterParser()
        
    def parse_markdown_file(self, file_path: str) -> ParsedMarkdownFile:
        """
        Parse a markdown file and extract all relevant information.
        
        Args:
            file_path: Path to the markdown file
            
        Returns:
            ParsedMarkdownFile with all extracted information
            
        Raises:
            MarkdownSyncError: If file cannot be read or parsed
        """
        try:
            if not os.path.exists(file_path):
                raise MarkdownSyncError(
                    f"Markdown file not found: {file_path}",
                    code="FILE_NOT_FOUND"
                )
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Parse frontmatter
            frontmatter, markdown_content = self.frontmatter_parser.parse(content)
            
            # Extract title
            title = self._extract_title(frontmatter, markdown_content, file_path)
            
            # Convert to Confluence storage format
            confluence_content = self._markdown_to_confluence_storage(markdown_content)
            
            # Generate content hash
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            return ParsedMarkdownFile(
                file_path=file_path,
                title=title,
                frontmatter=frontmatter,
                markdown_content=markdown_content,
                confluence_content=confluence_content,
                content_hash=content_hash
            )
            
        except MarkdownSyncError:
            raise
        except Exception as e:
            logger.error(f"Failed to parse markdown file {file_path}: {e}")
            raise MarkdownSyncError(
                f"Failed to parse markdown file: {e}",
                code="FILE_PARSE_ERROR",
                details={"file_path": file_path, "error": str(e)}
            )
    
    def _extract_title(self, frontmatter: Dict[str, Any], content: str, file_path: str) -> str:
        """Extract title from frontmatter or content."""
        # Try frontmatter first
        if 'title' in frontmatter:
            return str(frontmatter['title'])
            
        # Try first H1 heading
        h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if h1_match:
            return h1_match.group(1).strip()
            
        # Fallback to filename
        return os.path.splitext(os.path.basename(file_path))[0]
    
    def _markdown_to_confluence_storage(self, markdown: str) -> str:
        """
        Convert markdown to Confluence storage format.
        
        This is a simplified conversion. For production use, consider using
        a more robust markdown parser like python-markdown or mistune.
        """
        # Basic conversions
        storage = markdown
        
        # Headers
        storage = re.sub(r'^### (.+)$', r'<h3>\1</h3>', storage, flags=re.MULTILINE)
        storage = re.sub(r'^## (.+)$', r'<h2>\1</h2>', storage, flags=re.MULTILINE)
        storage = re.sub(r'^# (.+)$', r'<h1>\1</h1>', storage, flags=re.MULTILINE)
        
        # Bold and italic
        storage = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', storage)
        storage = re.sub(r'\*(.+?)\*', r'<em>\1</em>', storage)
        
        # Code blocks
        storage = re.sub(r'```(\w+)?\n(.*?)\n```', r'<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">\1</ac:parameter><ac:plain-text-body><![CDATA[\2]]></ac:plain-text-body></ac:structured-macro>', storage, flags=re.DOTALL)
        
        # Inline code
        storage = re.sub(r'`(.+?)`', r'<code>\1</code>', storage)
        
        # Links
        storage = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', storage)
        
        # Lists (basic)
        storage = re.sub(r'^- (.+)$', r'<li>\1</li>', storage, flags=re.MULTILINE)
        storage = re.sub(r'(<li>.*</li>)', r'<ul>\1</ul>', storage, flags=re.DOTALL)
        
        # Paragraphs
        paragraphs = storage.split('\n\n')
        storage_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<'):
                para = f'<p>{para}</p>'
            storage_paragraphs.append(para)
        
        storage = '\n\n'.join(storage_paragraphs)
        
        return storage
    
    def confluence_storage_to_markdown(self, storage_content: str) -> str:
        """
        Convert Confluence storage format to markdown.
        
        This is a simplified conversion for basic content.
        """
        markdown = storage_content
        
        # Headers
        markdown = re.sub(r'<h1>(.*?)</h1>', r'# \1', markdown)
        markdown = re.sub(r'<h2>(.*?)</h2>', r'## \1', markdown)
        markdown = re.sub(r'<h3>(.*?)</h3>', r'### \1', markdown)
        
        # Bold and italic
        markdown = re.sub(r'<strong>(.*?)</strong>', r'**\1**', markdown)
        markdown = re.sub(r'<em>(.*?)</em>', r'*\1*', markdown)
        
        # Code blocks
        markdown = re.sub(
            r'<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">(.*?)</ac:parameter><ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body></ac:structured-macro>',
            r'```\1\n\2\n```',
            markdown,
            flags=re.DOTALL
        )
        
        # Inline code
        markdown = re.sub(r'<code>(.*?)</code>', r'`\1`', markdown)
        
        # Links
        markdown = re.sub(r'<a href="(.*?)">(.*?)</a>', r'[\2](\1)', markdown)
        
        # Lists
        markdown = re.sub(r'<li>(.*?)</li>', r'- \1', markdown)
        markdown = re.sub(r'<ul>(.*?)</ul>', r'\1', markdown, flags=re.DOTALL)
        
        # Paragraphs
        markdown = re.sub(r'<p>(.*?)</p>', r'\1', markdown)
        
        # Clean up extra whitespace
        markdown = re.sub(r'\n\s*\n', '\n\n', markdown)
        
        return markdown.strip()
    
    def create_frontmatter(self, page_data: Dict[str, Any]) -> str:
        """Create YAML frontmatter from Confluence page data."""
        frontmatter_data = {
            'confluence_page_id': page_data.get('id'),
            'confluence_space_key': page_data.get('space', {}).get('key'),
            'confluence_title': page_data.get('title'),
            'confluence_version': page_data.get('version', {}).get('number'),
            'last_modified': page_data.get('version', {}).get('when'),
            'last_modified_by': page_data.get('version', {}).get('by', {}).get('displayName'),
        }
        
        # Remove None values
        frontmatter_data = {k: v for k, v in frontmatter_data.items() if v is not None}
        
        frontmatter_yaml = yaml.dump(frontmatter_data, default_flow_style=False)
        return f"---\n{frontmatter_yaml}---\n\n"