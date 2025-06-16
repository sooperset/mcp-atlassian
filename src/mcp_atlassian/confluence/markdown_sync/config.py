"""Configuration module for Confluence Markdown Sync."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MarkdownSyncConfig:
    """Configuration for markdown synchronization features."""
    
    # Core settings
    enabled: bool = False
    sync_directory: str = "./docs"
    mapping_file: str = ".confluence-mappings.json"
    
    # Sync behavior
    preserve_hierarchy: bool = True
    auto_create_pages: bool = True
    include_metadata: bool = True
    
    # Matching settings
    match_threshold: float = 85.0  # Percentage for fuzzy matching
    
    # Frontmatter schema
    required_frontmatter: List[str] = None
    optional_frontmatter: List[str] = None
    
    # Sync options
    preserve_formatting: bool = True
    convert_links: bool = True
    handle_attachments: bool = False
    
    def __post_init__(self):
        """Initialize default values after dataclass creation."""
        if self.required_frontmatter is None:
            self.required_frontmatter = []
        if self.optional_frontmatter is None:
            self.optional_frontmatter = [
                "confluence_page_id",
                "confluence_space_key", 
                "confluence_parent_id",
                "tags",
                "labels"
            ]
    
    @classmethod
    def from_env(cls) -> "MarkdownSyncConfig":
        """Create configuration from environment variables."""
        return cls(
            enabled=os.getenv("ATLASSIAN_MARKDOWN_SYNC_ENABLED", "false").lower() == "true",
            sync_directory=os.getenv("ATLASSIAN_MARKDOWN_SYNC_DIR", "./docs"),
            mapping_file=os.getenv("ATLASSIAN_MARKDOWN_MAPPING_FILE", ".confluence-mappings.json"),
            preserve_hierarchy=os.getenv("ATLASSIAN_MARKDOWN_PRESERVE_HIERARCHY", "true").lower() == "true",
            auto_create_pages=os.getenv("ATLASSIAN_MARKDOWN_AUTO_CREATE", "true").lower() == "true",
            include_metadata=os.getenv("ATLASSIAN_MARKDOWN_INCLUDE_METADATA", "true").lower() == "true",
            match_threshold=float(os.getenv("ATLASSIAN_MARKDOWN_MATCH_THRESHOLD", "85.0")),
            preserve_formatting=os.getenv("ATLASSIAN_MARKDOWN_PRESERVE_FORMAT", "true").lower() == "true",
            convert_links=os.getenv("ATLASSIAN_MARKDOWN_CONVERT_LINKS", "true").lower() == "true",
            handle_attachments=os.getenv("ATLASSIAN_MARKDOWN_HANDLE_ATTACHMENTS", "false").lower() == "true",
        )
    
    def to_dict(self) -> Dict[str, any]:
        """Convert configuration to dictionary."""
        return {
            "enabled": self.enabled,
            "sync_directory": self.sync_directory,
            "mapping_file": self.mapping_file,
            "preserve_hierarchy": self.preserve_hierarchy,
            "auto_create_pages": self.auto_create_pages,
            "include_metadata": self.include_metadata,
            "match_threshold": self.match_threshold,
            "required_frontmatter": self.required_frontmatter,
            "optional_frontmatter": self.optional_frontmatter,
            "preserve_formatting": self.preserve_formatting,
            "convert_links": self.convert_links,
            "handle_attachments": self.handle_attachments,
        }
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of issues."""
        issues = []
        
        if self.match_threshold < 0 or self.match_threshold > 100:
            issues.append("match_threshold must be between 0 and 100")
        
        if not self.sync_directory:
            issues.append("sync_directory cannot be empty")
        
        if not self.mapping_file:
            issues.append("mapping_file cannot be empty")
        
        return issues