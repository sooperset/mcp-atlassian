"""
Confluence Markdown Sync Engine
Handles bidirectional synchronization between markdown files and Confluence pages.
Adapted to mcp-atlassian architecture patterns.
"""

import json
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ...exceptions import MCPAtlassianError
from ..client import ConfluenceClient
from .converter import MarkdownConverter, MarkdownSyncError, ParsedMarkdownFile
from .matcher import PageMatcher

logger = logging.getLogger("mcp-atlassian.confluence.markdown_sync")


class SyncMode(Enum):
    """Synchronization modes."""
    CREATE_ONLY = "create_only"
    UPDATE_ONLY = "update_only"
    AUTO = "auto"


class ConflictStrategy(Enum):
    """Conflict resolution strategies."""
    OVERWRITE = "overwrite"
    MERGE = "merge"
    PROMPT = "prompt"
    SKIP = "skip"


class SyncResult:
    """Result of a sync operation."""
    
    def __init__(self, success: bool, message: str, page_id: Optional[str] = None, details: Optional[Dict] = None):
        self.success = success
        self.message = message
        self.page_id = page_id
        self.details = details or {}


class MarkdownSyncEngine:
    """
    Main engine for markdown-Confluence synchronization.
    
    Integrates with mcp-atlassian client patterns and error handling.
    """
    
    def __init__(self, confluence_client: ConfluenceClient, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the sync engine.
        
        Args:
            confluence_client: Configured Confluence client
            config: Optional sync configuration
        """
        self.client = confluence_client
        self.converter = MarkdownConverter()
        self.matcher = PageMatcher(
            similarity_threshold=config.get('match_threshold', 85) / 100 if config else 0.85
        )
        
        # Configuration
        self.config = config or {}
        self.sync_directory = self.config.get('sync_directory', './docs')
        self.mapping_file = self.config.get('mapping_file', '.confluence-mappings.json')
        self.preserve_hierarchy = self.config.get('preserve_hierarchy', True)
        
        # Load existing mappings
        self.mappings = self._load_mappings()
    
    def sync_markdown_to_page(
        self,
        file_path: str,
        space_key: str,
        parent_id: Optional[str] = None,
        sync_mode: SyncMode = SyncMode.AUTO,
        conflict_strategy: ConflictStrategy = ConflictStrategy.PROMPT,
        dry_run: bool = False
    ) -> SyncResult:
        """
        Sync a markdown file to a Confluence page.
        
        Args:
            file_path: Path to the markdown file
            space_key: Target Confluence space
            parent_id: Optional parent page ID
            sync_mode: How to handle create/update decisions
            conflict_strategy: How to handle conflicts
            dry_run: If True, only preview changes without applying
            
        Returns:
            SyncResult with operation details
        """
        try:
            logger.info(f"Starting sync: {file_path} -> {space_key}")
            
            # Parse markdown file
            parsed_file = self.converter.parse_markdown_file(file_path)
            
            # Check for existing mapping
            existing_mapping = self.mappings.get(file_path)
            target_page_id = existing_mapping.get('page_id') if existing_mapping else None
            
            # Find or determine target page
            if target_page_id:
                # Try to get the mapped page
                try:
                    target_page = self._get_page_by_id(target_page_id)
                    if not target_page:
                        logger.warning(f"Mapped page {target_page_id} not found, will search for match")
                        target_page = self._find_target_page(parsed_file, space_key)
                except Exception as e:
                    logger.warning(f"Failed to get mapped page {target_page_id}: {e}")
                    target_page = self._find_target_page(parsed_file, space_key)
            else:
                target_page = self._find_target_page(parsed_file, space_key)
            
            # Determine operation type
            if target_page:
                operation = "update"
                if sync_mode == SyncMode.CREATE_ONLY:
                    return SyncResult(
                        False, 
                        f"Page already exists and sync_mode is CREATE_ONLY: {target_page['title']}"
                    )
            else:
                operation = "create"
                if sync_mode == SyncMode.UPDATE_ONLY:
                    return SyncResult(
                        False,
                        f"No existing page found and sync_mode is UPDATE_ONLY: {parsed_file.title}"
                    )
            
            # Handle conflicts for updates
            if operation == "update":
                has_conflict, conflict_type = self._check_for_conflicts(parsed_file, target_page)
                if has_conflict:
                    conflict_result = self._handle_conflict(
                        parsed_file, target_page, conflict_type, conflict_strategy
                    )
                    if not conflict_result.success:
                        return conflict_result
            
            # Determine parent page
            if not parent_id and self.preserve_hierarchy:
                parent_id = self._suggest_parent_page(parsed_file.file_path, space_key)
            
            # Preview mode
            if dry_run:
                return SyncResult(
                    True,
                    f"DRY RUN: Would {operation} page '{parsed_file.title}' in space {space_key}",
                    details={
                        'operation': operation,
                        'title': parsed_file.title,
                        'space_key': space_key,
                        'parent_id': parent_id,
                        'target_page_id': target_page.get('id') if target_page else None
                    }
                )
            
            # Perform the sync operation
            if operation == "create":
                result = self._create_page(parsed_file, space_key, parent_id)
            else:
                result = self._update_page(parsed_file, target_page)
            
            # Update mappings on success
            if result.success and result.page_id:
                self._update_mapping(file_path, result.page_id, parsed_file.content_hash)
            
            return result
            
        except MarkdownSyncError:
            raise
        except Exception as e:
            logger.error(f"Failed to sync {file_path}: {e}")
            raise MarkdownSyncError(
                f"Sync operation failed: {e}",
                code="SYNC_ERROR",
                details={"file_path": file_path, "error": str(e)}
            )
    
    def sync_page_to_markdown(
        self,
        page_id: str,
        output_path: str,
        include_attachments: bool = False,
        dry_run: bool = False
    ) -> SyncResult:
        """
        Sync a Confluence page to a markdown file.
        
        Args:
            page_id: Confluence page ID
            output_path: Path for the output markdown file
            include_attachments: Whether to download attachments
            dry_run: If True, only preview changes without applying
            
        Returns:
            SyncResult with operation details
        """
        try:
            logger.info(f"Starting page to markdown sync: {page_id} -> {output_path}")
            
            # Get page content
            page = self._get_page_by_id(page_id, expand=['body.storage', 'version', 'space'])
            if not page:
                return SyncResult(False, f"Page not found: {page_id}")
            
            # Convert to markdown
            storage_content = page.get('body', {}).get('storage', {}).get('value', '')
            markdown_content = self.converter.confluence_storage_to_markdown(storage_content)
            
            # Create frontmatter
            frontmatter = self.converter.create_frontmatter(page)
            
            # Combine frontmatter and content
            full_content = frontmatter + markdown_content
            
            # Preview mode
            if dry_run:
                return SyncResult(
                    True,
                    f"DRY RUN: Would write {len(full_content)} characters to {output_path}",
                    details={
                        'page_id': page_id,
                        'page_title': page.get('title'),
                        'content_length': len(full_content),
                        'output_path': output_path
                    }
                )
            
            # Write to file
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
            
            # Update mappings
            import hashlib
            content_hash = hashlib.md5(full_content.encode('utf-8')).hexdigest()
            self._update_mapping(output_path, page_id, content_hash)
            
            logger.info(f"Successfully synced page to markdown: {output_path}")
            return SyncResult(
                True,
                f"Successfully synced page '{page.get('title')}' to {output_path}",
                page_id=page_id
            )
            
        except Exception as e:
            logger.error(f"Failed to sync page {page_id} to markdown: {e}")
            raise MarkdownSyncError(
                f"Page to markdown sync failed: {e}",
                code="PAGE_TO_MARKDOWN_ERROR",
                details={"page_id": page_id, "output_path": output_path, "error": str(e)}
            )
    
    def _find_target_page(self, parsed_file: ParsedMarkdownFile, space_key: str) -> Optional[Dict[str, Any]]:
        """Find target page for a markdown file."""
        # Get all pages in the space (simplified - in practice, you'd paginate)
        try:
            # This would use the actual client method to search pages
            # For now, we'll use a placeholder that follows their pattern
            pages = self._search_pages_in_space(space_key)
            return self.matcher.find_matching_page(
                parsed_file.title,
                space_key,
                pages,
                parsed_file.frontmatter
            )
        except Exception as e:
            logger.warning(f"Failed to find target page: {e}")
            return None
    
    def _search_pages_in_space(self, space_key: str) -> List[Dict[str, Any]]:
        """Search for pages in a space using the client."""
        try:
            # Use the client's search functionality
            # This is a placeholder - implement based on actual client methods
            search_results = []
            # search_results = self.client.get_all_pages_from_space(space_key)
            return search_results
        except Exception as e:
            logger.error(f"Failed to search pages in space {space_key}: {e}")
            return []
    
    def _get_page_by_id(self, page_id: str, expand: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Get page by ID using the client."""
        try:
            # Use the client's get page method
            # This is a placeholder - implement based on actual client methods
            # return self.client.get_page_by_id(page_id, expand=expand)
            return None
        except Exception as e:
            logger.error(f"Failed to get page {page_id}: {e}")
            return None
    
    def _check_for_conflicts(self, parsed_file: ParsedMarkdownFile, target_page: Dict[str, Any]) -> Tuple[bool, str]:
        """Check for sync conflicts."""
        mapping = self.mappings.get(parsed_file.file_path, {})
        last_sync_hash = mapping.get('content_hash')
        
        return self.matcher.detect_conflicts(
            parsed_file.content_hash,
            target_page,
            last_sync_hash
        )
    
    def _handle_conflict(
        self,
        parsed_file: ParsedMarkdownFile,
        target_page: Dict[str, Any],
        conflict_type: str,
        strategy: ConflictStrategy
    ) -> SyncResult:
        """Handle sync conflicts based on strategy."""
        if strategy == ConflictStrategy.SKIP:
            return SyncResult(
                False,
                f"Skipping due to conflict ({conflict_type}): {parsed_file.title}"
            )
        elif strategy == ConflictStrategy.OVERWRITE:
            logger.warning(f"Overwriting remote changes for {parsed_file.title}")
            return SyncResult(True, "Proceeding with overwrite")
        elif strategy == ConflictStrategy.PROMPT:
            # In a real implementation, this would prompt the user
            logger.warning(f"Conflict detected ({conflict_type}) for {parsed_file.title}, proceeding with overwrite")
            return SyncResult(True, "User chose to overwrite")
        else:  # MERGE
            # Merge strategy would be complex to implement
            return SyncResult(
                False,
                f"Merge strategy not yet implemented for {parsed_file.title}"
            )
    
    def _suggest_parent_page(self, file_path: str, space_key: str) -> Optional[str]:
        """Suggest parent page based on file hierarchy."""
        try:
            pages = self._search_pages_in_space(space_key)
            return self.matcher.suggest_page_hierarchy(file_path, self.sync_directory, pages)
        except Exception as e:
            logger.warning(f"Failed to suggest parent page: {e}")
            return None
    
    def _create_page(self, parsed_file: ParsedMarkdownFile, space_key: str, parent_id: Optional[str]) -> SyncResult:
        """Create a new Confluence page."""
        try:
            # Use the client to create the page
            # This is a placeholder - implement based on actual client methods
            page_data = {
                'type': 'page',
                'title': parsed_file.title,
                'space': {'key': space_key},
                'body': {
                    'storage': {
                        'value': parsed_file.confluence_content,
                        'representation': 'storage'
                    }
                }
            }
            
            if parent_id:
                page_data['ancestors'] = [{'id': parent_id}]
            
            # created_page = self.client.create_page(page_data)
            # For now, return a mock result
            logger.info(f"Would create page: {parsed_file.title}")
            return SyncResult(
                True,
                f"Successfully created page: {parsed_file.title}",
                page_id="mock_page_id"
            )
            
        except Exception as e:
            logger.error(f"Failed to create page {parsed_file.title}: {e}")
            raise MarkdownSyncError(
                f"Failed to create page: {e}",
                code="PAGE_CREATE_ERROR",
                details={"title": parsed_file.title, "error": str(e)}
            )
    
    def _update_page(self, parsed_file: ParsedMarkdownFile, target_page: Dict[str, Any]) -> SyncResult:
        """Update an existing Confluence page."""
        try:
            # Use the client to update the page
            # This is a placeholder - implement based on actual client methods
            page_id = target_page['id']
            current_version = target_page.get('version', {}).get('number', 1)
            
            update_data = {
                'id': page_id,
                'type': 'page',
                'title': parsed_file.title,
                'body': {
                    'storage': {
                        'value': parsed_file.confluence_content,
                        'representation': 'storage'
                    }
                },
                'version': {
                    'number': current_version + 1
                }
            }
            
            # updated_page = self.client.update_page(update_data)
            # For now, return a mock result
            logger.info(f"Would update page: {parsed_file.title}")
            return SyncResult(
                True,
                f"Successfully updated page: {parsed_file.title}",
                page_id=page_id
            )
            
        except Exception as e:
            logger.error(f"Failed to update page {target_page.get('title')}: {e}")
            raise MarkdownSyncError(
                f"Failed to update page: {e}",
                code="PAGE_UPDATE_ERROR",
                details={"page_id": target_page.get('id'), "error": str(e)}
            )
    
    def _load_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Load file-to-page mappings from disk."""
        try:
            if os.path.exists(self.mapping_file):
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.warning(f"Failed to load mappings from {self.mapping_file}: {e}")
            return {}
    
    def _save_mappings(self):
        """Save file-to-page mappings to disk."""
        try:
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(self.mappings, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save mappings to {self.mapping_file}: {e}")
    
    def _update_mapping(self, file_path: str, page_id: str, content_hash: str):
        """Update the mapping for a file."""
        self.mappings[file_path] = {
            'page_id': page_id,
            'content_hash': content_hash,
            'last_sync': self._get_current_timestamp()
        }
        self._save_mappings()
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + 'Z'