"""
Confluence Page Matcher
Handles intelligent matching between markdown files and Confluence pages.
Adapted to mcp-atlassian architecture patterns.
"""

import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from ...exceptions import MCPAtlassianError
from .converter import MarkdownSyncError

logger = logging.getLogger("mcp-atlassian.confluence.markdown_sync")


class PageMatcher:
    """
    Intelligent matching between markdown files and Confluence pages.
    
    Integrates with mcp-atlassian client patterns and error handling.
    """
    
    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize the page matcher.
        
        Args:
            similarity_threshold: Minimum similarity score for fuzzy matching (0.0-1.0)
        """
        self.similarity_threshold = similarity_threshold
    
    def find_matching_page(
        self,
        title: str,
        space_key: str,
        existing_pages: List[Dict[str, Any]],
        frontmatter: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best matching Confluence page for a markdown file.
        
        Args:
            title: Title from markdown file
            space_key: Target Confluence space
            existing_pages: List of existing pages in the space
            frontmatter: Optional frontmatter data with page hints
            
        Returns:
            Best matching page dict or None if no good match found
            
        Raises:
            MarkdownSyncError: If matching process fails
        """
        try:
            # First, check for exact page ID match in frontmatter
            if frontmatter and 'confluence_page_id' in frontmatter:
                page_id = frontmatter['confluence_page_id']
                exact_match = self._find_page_by_id(page_id, existing_pages)
                if exact_match:
                    logger.debug(f"Found exact page ID match: {page_id}")
                    return exact_match
                else:
                    logger.warning(f"Page ID {page_id} from frontmatter not found in space")
            
            # Filter pages by space
            space_pages = [p for p in existing_pages if p.get('space', {}).get('key') == space_key]
            
            if not space_pages:
                logger.debug(f"No pages found in space {space_key}")
                return None
            
            # Try exact title match first
            exact_match = self._find_exact_title_match(title, space_pages)
            if exact_match:
                logger.debug(f"Found exact title match: {title}")
                return exact_match
            
            # Try fuzzy title matching
            fuzzy_match = self._find_fuzzy_title_match(title, space_pages)
            if fuzzy_match:
                logger.debug(f"Found fuzzy title match: {title} -> {fuzzy_match['title']}")
                return fuzzy_match
            
            logger.debug(f"No matching page found for title: {title}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to find matching page for {title}: {e}")
            raise MarkdownSyncError(
                f"Failed to find matching page: {e}",
                code="PAGE_MATCHING_ERROR",
                details={"title": title, "space_key": space_key, "error": str(e)}
            )
    
    def _find_page_by_id(self, page_id: str, pages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find page by exact ID match."""
        for page in pages:
            if page.get('id') == page_id:
                return page
        return None
    
    def _find_exact_title_match(self, title: str, pages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find page by exact title match."""
        for page in pages:
            if page.get('title') == title:
                return page
        return None
    
    def _find_fuzzy_title_match(self, title: str, pages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find page by fuzzy title matching."""
        best_match = None
        best_score = 0.0
        
        for page in pages:
            page_title = page.get('title', '')
            similarity = self._calculate_similarity(title, page_title)
            
            if similarity > best_score and similarity >= self.similarity_threshold:
                best_score = similarity
                best_match = page
        
        return best_match
    
    def _calculate_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity score between two titles."""
        # Normalize titles for comparison
        norm_title1 = self._normalize_title(title1)
        norm_title2 = self._normalize_title(title2)
        
        # Use SequenceMatcher for similarity calculation
        matcher = SequenceMatcher(None, norm_title1, norm_title2)
        return matcher.ratio()
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        # Convert to lowercase and remove extra whitespace
        normalized = title.lower().strip()
        
        # Remove common punctuation and special characters
        import re
        normalized = re.sub(r'[^\w\s]', '', normalized)
        
        # Collapse multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized
    
    def detect_conflicts(
        self,
        local_content_hash: str,
        remote_page: Dict[str, Any],
        last_sync_hash: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Detect sync conflicts between local and remote content.
        
        Args:
            local_content_hash: Hash of local markdown content
            remote_page: Remote Confluence page data
            last_sync_hash: Hash from last successful sync
            
        Returns:
            Tuple of (has_conflict, conflict_type)
            conflict_type can be: 'none', 'local_modified', 'remote_modified', 'both_modified'
        """
        try:
            # Get remote content hash (simplified - in practice, you'd hash the actual content)
            remote_version = remote_page.get('version', {}).get('number', 0)
            remote_modified = remote_page.get('version', {}).get('when')
            
            # If we don't have a last sync hash, assume no conflict for first sync
            if not last_sync_hash:
                return False, 'none'
            
            # Check if local content changed since last sync
            local_modified = local_content_hash != last_sync_hash
            
            # For remote modification detection, we'd need to store the last synced version
            # This is a simplified check - in practice, you'd compare with stored metadata
            remote_modified_check = True  # Placeholder - implement based on your sync metadata
            
            if local_modified and remote_modified_check:
                return True, 'both_modified'
            elif local_modified:
                return True, 'local_modified'
            elif remote_modified_check:
                return True, 'remote_modified'
            else:
                return False, 'none'
                
        except Exception as e:
            logger.error(f"Failed to detect conflicts: {e}")
            raise MarkdownSyncError(
                f"Failed to detect conflicts: {e}",
                code="CONFLICT_DETECTION_ERROR",
                details={"error": str(e)}
            )
    
    def suggest_page_hierarchy(
        self,
        file_path: str,
        base_directory: str,
        existing_pages: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Suggest parent page ID based on file directory structure.
        
        Args:
            file_path: Path to the markdown file
            base_directory: Base directory for markdown files
            existing_pages: List of existing pages to search for parents
            
        Returns:
            Parent page ID or None if no suitable parent found
        """
        try:
            import os
            
            # Get relative path from base directory
            rel_path = os.path.relpath(file_path, base_directory)
            path_parts = os.path.dirname(rel_path).split(os.sep)
            
            # Remove empty parts and current directory markers
            path_parts = [part for part in path_parts if part and part != '.']
            
            if not path_parts:
                return None
            
            # Look for parent directory as page title
            parent_dir = path_parts[-1]
            
            # Try to find a page with title matching the parent directory
            for page in existing_pages:
                page_title = page.get('title', '').lower()
                if parent_dir.lower() in page_title or page_title in parent_dir.lower():
                    logger.debug(f"Found potential parent page: {page['title']} for {file_path}")
                    return page.get('id')
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to suggest page hierarchy for {file_path}: {e}")
            return None
    
    def validate_sync_compatibility(
        self,
        markdown_file: Dict[str, Any],
        confluence_page: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that a markdown file and Confluence page are compatible for sync.
        
        Args:
            markdown_file: Parsed markdown file data
            confluence_page: Confluence page data
            
        Returns:
            Tuple of (is_compatible, list_of_issues)
        """
        issues = []
        
        try:
            # Check if page is locked
            if confluence_page.get('restrictions', {}).get('read', {}).get('restrictions', {}).get('user', {}).get('results'):
                issues.append("Page has read restrictions")
            
            # Check if page has unsupported macros (simplified check)
            page_content = confluence_page.get('body', {}).get('storage', {}).get('value', '')
            if 'ac:structured-macro' in page_content:
                # Count macros - too many might indicate complex content
                macro_count = page_content.count('ac:structured-macro')
                if macro_count > 10:  # Arbitrary threshold
                    issues.append(f"Page contains many macros ({macro_count}) that may not convert well")
            
            # Check content size
            content_size = len(page_content)
            if content_size > 100000:  # 100KB threshold
                issues.append(f"Page content is very large ({content_size} chars) and may have sync issues")
            
            # Check for special page types
            page_type = confluence_page.get('type')
            if page_type != 'page':
                issues.append(f"Unsupported page type: {page_type}")
            
            is_compatible = len(issues) == 0
            return is_compatible, issues
            
        except Exception as e:
            logger.error(f"Failed to validate sync compatibility: {e}")
            return False, [f"Validation error: {e}"]