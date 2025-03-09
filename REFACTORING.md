# MCP Atlassian Refactoring Plan

## Overview

This document outlines the plan for refactoring the MCP Atlassian codebase, with a focus on modularizing the large `jira.py` and `confluence.py` files. The refactoring will improve maintainability, testability, and readability while maintaining backward compatibility.

## Current Codebase Analysis

### Confluence Module (confluence.py)

Current structure:
- Single `ConfluenceFetcher` class (~400 lines)
- Handles all Confluence API interactions
- Initialized with configuration from environment variables
- Methods for various operations (spaces, pages, comments, search)
- Used by server.py handlers to respond to MCP requests

#### Method Groups and Dependencies

The `ConfluenceFetcher` class contains methods that can be grouped as follows:

1. **Authentication & Configuration**
   - `__init__`: Sets up configuration from environment variables and initializes the Confluence client

2. **Content Processing**
   - `_process_html_content`: Processes HTML content into markdown

3. **Space Operations**
   - `get_spaces`: Gets available Confluence spaces
   - `get_user_contributed_spaces`: Gets spaces the user has contributed to

4. **Page Operations**
   - `get_page_content`: Gets content of a specific page by ID
   - `get_page_by_title`: Gets a page by its title within a space
   - `get_space_pages`: Gets all pages from a specific space
   - `create_page`: Creates a new page in a space
   - `update_page`: Updates an existing page

5. **Comment Operations**
   - `get_page_comments`: Gets comments for a specific page

6. **Search Operations**
   - `search`: Searches content using CQL

### Interaction Points

The Confluence module interacts with:
1. **Environment Variables**: Read during initialization
   - `CONFLUENCE_URL`
   - `CONFLUENCE_USERNAME`
   - `CONFLUENCE_API_TOKEN`

2. **Server Handlers**: Called by functions in server.py
   - `handle_confluence_search`
   - `handle_confluence_get_page`
   - `handle_confluence_get_comments`
   - `handle_confluence_create_page`
   - `handle_confluence_update_page`
   - Resource handlers: `_handle_confluence_resource`, `_handle_confluence_space`, `_handle_confluence_page`

3. **External Atlassian API**: Uses the atlassian.Confluence client

4. **Other Dependencies**:
   - `ConfluenceConfig`: From config.py
   - `Document`: From document_types.py
   - `TextPreprocessor`: From preprocessing.py

### Dependency Chain Analysis

- `ConfluenceFetcher.__init__` → Reads environment variables → Creates `ConfluenceConfig` → Initializes `Confluence` client → Creates `TextPreprocessor`
- Most methods depend on the `self.confluence` client instance
- Content formatting methods depend on `self.preprocessor`
- All methods that return `Document` objects depend on the `Document` class

## Refactoring Goals

1. Split functionality into logical modules
2. Maintain backward compatibility
3. Improve testability with clear separation of concerns
4. Reduce file sizes and improve readability
5. Follow the development guidelines in CLAUDE.md

## Confluence Refactoring Strategy

### 1. New Package Structure

```
src/mcp_atlassian/
├── confluence/
│   ├── __init__.py           # Re-exports ConfluenceFetcher for backward compatibility
│   ├── client.py             # Base client setup and authentication
│   ├── config.py             # Configuration loading and validation
│   ├── spaces.py             # Space-related operations
│   ├── pages.py              # Page CRUD operations
│   ├── comments.py           # Comment-related operations
│   ├── search.py             # Search functionality
│   ├── formatters.py         # Content formatting utilities
│   └── types.py              # Type definitions specific to Confluence
```

### 2. Implementation Approach

#### Step 1: Create Base Configuration Class

First, enhance the `ConfluenceConfig` class to support loading from environment:

```python
# confluence/config.py
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class ConfluenceConfig:
    """Confluence API configuration."""

    url: str  # Base URL for Confluence
    username: str  # Email or username
    api_token: str  # API token used as password

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud instance."""
        return "atlassian.net" in self.url

    @classmethod
    def from_env(cls) -> "ConfluenceConfig":
        """Create configuration from environment variables."""
        url = os.getenv("CONFLUENCE_URL")
        username = os.getenv("CONFLUENCE_USERNAME")
        token = os.getenv("CONFLUENCE_API_TOKEN")

        if not all([url, username, token]):
            error_msg = "Missing required Confluence environment variables"
            raise ValueError(error_msg)

        # These variables are guaranteed to be non-None after the check above
        url = url if url is not None else ""
        username = username if username is not None else ""
        token = token if token is not None else ""

        return cls(url=url, username=username, api_token=token)
```

#### Step 2: Create Base Client Class

Create a base `ConfluenceClient` class in `client.py` responsible for:
- Initializing configuration
- Setting up the Atlassian Confluence client
- Providing common utilities

```python
# confluence/client.py
import logging
from typing import Optional, Protocol, Any

from atlassian import Confluence

from ..document_types import Document
from .config import ConfluenceConfig

logger = logging.getLogger("mcp-atlassian")

class ConfluenceClient:
    """Base client for Confluence API interactions."""

    def __init__(self, config: Optional[ConfluenceConfig] = None) -> None:
        """Initialize the Confluence client with given or environment config."""
        self.config = config or ConfluenceConfig.from_env()
        self.confluence = Confluence(
            url=self.config.url,
            username=self.config.username,
            password=self.config.api_token,  # API token is used as password
            cloud=True,
        )
        from ..preprocessing import TextPreprocessor
        self.preprocessor = TextPreprocessor(
            base_url=self.config.url, confluence_client=self.confluence
        )

    def _process_html_content(
        self, html_content: str, space_key: str
    ) -> tuple[str, str]:
        """Process HTML content into both HTML and markdown formats."""
        return self.preprocessor.process_html_content(html_content, space_key)
```

#### Step 3: Create Functional Mixins

Create mixins for different functional areas:

```python
# confluence/spaces.py
from typing import Dict, Any, cast

from .client import ConfluenceClient

class SpacesMixin(ConfluenceClient):
    """Mixin for Confluence space operations."""

    def get_spaces(self, start: int = 0, limit: int = 10) -> Dict[str, object]:
        """
        Get all available spaces.

        Args:
            start: The starting index for pagination
            limit: Maximum number of spaces to return

        Returns:
            Dictionary containing space information with results and metadata
        """
        spaces = self.confluence.get_all_spaces(start=start, limit=limit)
        # Cast the return value to the expected type
        return cast(Dict[str, object], spaces)

    def get_user_contributed_spaces(self, limit: int = 250) -> dict:
        """
        Get spaces the current user has contributed to.

        Args:
            limit: Maximum number of results to return

        Returns:
            Dictionary of space keys to space information
        """
        # Implementation...
```

Similar mixins for pages, comments, search, etc.

#### Step 4: Create Main Interface

Implement the main `ConfluenceFetcher` class in `__init__.py`:

```python
# confluence/__init__.py
from .client import ConfluenceClient
from .spaces import SpacesMixin
from .pages import PagesMixin
from .comments import CommentsMixin
from .search import SearchMixin

class ConfluenceFetcher(SpacesMixin, PagesMixin, CommentsMixin, SearchMixin):
    """Main entry point for Confluence operations, providing backward compatibility."""
    pass

__all__ = ["ConfluenceFetcher"]
```

### 3. Testing Strategy

1. **Unit Tests**:
   - Create unit tests for each mixin: `test_spaces.py`, `test_pages.py`, etc.
   - Mock the Confluence client for isolated testing
   - Test error handling and edge cases

2. **Integration Tests**:
   - Test the composed `ConfluenceFetcher` class
   - Verify it works with real-world data (using test fixtures)
   - Focus on API compatibility with the previous version

3. **Backward Compatibility Tests**:
   - Test server handlers remain functional
   - Test resource handling

### 4. Migration Path

1. **Create Infrastructure**:
   - Create the new directory structure
   - Move `ConfluenceConfig` from config.py to confluence/config.py
   - Create base files with proper imports

2. **Implement Core Components**:
   - Implement `ConfluenceClient` base class
   - Create mixin classes for each functional area

3. **Move Methods in Stages**:
   - Create each mixin with its methods:
     1. Implement `SpacesMixin` with space-related methods
     2. Implement `PagesMixin` with page-related methods
     3. Implement `CommentsMixin` with comment methods
     4. Implement `SearchMixin` with search functionality

4. **Integration and Testing**:
   - Test each mixin individually
   - Create and test the composite `ConfluenceFetcher` class
   - Update imports in server.py
   - Run integration tests

5. **Cleanup**:
   - Once verified, remove old confluence.py
   - Update documentation

## Detailed Implementation Plan for Confluence

### Phase 1: Setup (1 day)

1. **Create Directory Structure**:
   - Create the `src/mcp_atlassian/confluence` directory
   - Create empty module files: `__init__.py`, `client.py`, etc.

2. **Create Base Config**:
   - Implement enhanced `ConfluenceConfig` class with `from_env()` method

3. **Create Base Client**:
   - Implement `ConfluenceClient` class
   - Move common utilities like `_process_html_content`

### Phase 2: Implementation (2-3 days)

1. **Implement Space Functionality** (0.5 day):
   - Create `SpacesMixin` class
   - Implement `get_spaces` and `get_user_contributed_spaces` methods

2. **Implement Page Functionality** (1 day):
   - Create `PagesMixin` class
   - Implement `get_page_content`, `get_page_by_title`, `get_space_pages`, `create_page`, and `update_page` methods

3. **Implement Comment Functionality** (0.5 day):
   - Create `CommentsMixin` class
   - Implement `get_page_comments` method

4. **Implement Search Functionality** (0.5 day):
   - Create `SearchMixin` class
   - Implement `search` method

5. **Create Main Interface** (0.5 day):
   - Implement the composite `ConfluenceFetcher` class in `__init__.py`
   - Test backward compatibility

### Phase 3: Integration and Testing (1-2 days)

1. **Create Tests**:
   - Create unit tests for each mixin
   - Create integration tests for the composite class

2. **Update Imports**:
   - Update imports in server.py

3. **Run Tests**:
   - Run tests to ensure functionality
   - Fix any issues

### Phase 4: Cleanup and Documentation (0.5 day)

1. **Remove Old Code**:
   - Remove the old confluence.py once everything is verified

2. **Update Documentation**:
   - Update docstrings
   - Add module-level documentation

## Progress Report

### Completed Tasks for Confluence Refactoring ✅

- ✅ Created the Confluence module directory structure
- ✅ Implemented `ConfluenceConfig` in `config.py` with `from_env()` method
- ✅ Implemented base `ConfluenceClient` class in `client.py`
- ✅ Implemented `SpacesMixin` for space operations
- ✅ Implemented `SearchMixin` for search operations
- ✅ Implemented `PagesMixin` for page operations
- ✅ Implemented `CommentsMixin` for comment operations
- ✅ Created composite `ConfluenceFetcher` class in `__init__.py`
- ✅ Modified tests to work with the refactored code
- ✅ Verified backward compatibility with existing tests
- ✅ Checked server.py compatibility with the new module
- ✅ Created backup of original confluence.py file
- ✅ Removed the original confluence.py file
- ✅ Verified tests still pass after refactoring

### Confluence Refactoring Complete!

The Confluence module has been successfully refactored into a modular, maintainable, and testable structure. The refactoring maintains backward compatibility with the existing API, so other parts of the codebase do not need to be changed.

### Next Steps: Jira Refactoring

The next phase is to apply a similar refactoring approach to the Jira module:

1. Analyze Jira module dependencies and interactions
2. Create a similar directory structure
3. Implement base client and mixins
4. Ensure backward compatibility
5. Test thoroughly

## Timeline

- ✅ Confluence refactoring: Completed
- ⬜ Jira refactoring: 7-9 days (due to higher complexity)

## Success Criteria

1. ✅ All tests pass after refactoring
2. ✅ Code coverage remains the same or improves
3. ✅ File sizes are manageable (< 300 lines per file)
4. ✅ Clear separation of concerns between modules
5. ✅ No regression in functionality
