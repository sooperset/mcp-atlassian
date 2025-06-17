"""
Shared fixtures for Confluence unit tests.

This module provides specialized fixtures for testing Confluence-related functionality.
It builds upon the root conftest.py fixtures and integrates with the new test utilities
framework to provide efficient, reusable test fixtures with session-scoped caching.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the root tests directory to PYTHONPATH
sys.path.append(str(Path(__file__).parent.parent.parent))

from fixtures.confluence_mocks import (
    MOCK_COMMENTS_RESPONSE,
    MOCK_CQL_SEARCH_RESPONSE,
    MOCK_LABELS_RESPONSE,
    MOCK_PAGE_RESPONSE,
    MOCK_PAGES_FROM_SPACE_RESPONSE,
    MOCK_SPACES_RESPONSE,
)

from mcp_atlassian.confluence.client import ConfluenceClient
from mcp_atlassian.confluence.config import ConfluenceConfig
from tests.utils.factories import AuthConfigFactory, ConfluencePageFactory
from tests.utils.mocks import MockAtlassianClient, MockPreprocessor

# ============================================================================
# Session-Scoped Confluence Data Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def session_confluence_spaces():
    """
    Session-scoped fixture providing Confluence space definitions.

    This expensive-to-create data is cached for the entire test session
    to improve test performance.

    Returns:
        List[Dict[str, Any]]: Complete Confluence space definitions
    """
    return [
        {
            "id": 12345,
            "key": "TEST",
            "name": "Test Space",
            "type": "global",
            "status": "current",
            "description": {"plain": {"value": "Test space for unit tests"}},
            "_links": {
                "webui": "/spaces/TEST",
                "self": "https://test.atlassian.net/wiki/rest/api/space/TEST",
            },
        },
        {
            "id": 12346,
            "key": "DEMO",
            "name": "Demo Space",
            "type": "global",
            "status": "current",
            "description": {"plain": {"value": "Demo space for testing"}},
            "_links": {
                "webui": "/spaces/DEMO",
                "self": "https://test.atlassian.net/wiki/rest/api/space/DEMO",
            },
        },
        {
            "id": 12347,
            "key": "SAMPLE",
            "name": "Sample Space",
            "type": "personal",
            "status": "current",
            "description": {"plain": {"value": "Sample personal space"}},
            "_links": {
                "webui": "/spaces/SAMPLE",
                "self": "https://test.atlassian.net/wiki/rest/api/space/SAMPLE",
            },
        },
    ]


@pytest.fixture(scope="session")
def session_confluence_content_types():
    """
    Session-scoped fixture providing Confluence content type definitions.

    Returns:
        List[Dict[str, Any]]: Mock Confluence content type data
    """
    return [
        {"name": "page", "type": "content"},
        {"name": "blogpost", "type": "content"},
        {"name": "comment", "type": "content"},
        {"name": "attachment", "type": "content"},
        {"name": "space", "type": "space"},
        {"name": "user", "type": "user"},
    ]


@pytest.fixture(scope="session")
def session_confluence_macros():
    """
    Session-scoped fixture providing Confluence macro definitions.

    Returns:
        List[Dict[str, Any]]: Mock Confluence macro data
    """
    return [
        {"name": "info", "hasBody": True, "bodyType": "rich-text"},
        {"name": "warning", "hasBody": True, "bodyType": "rich-text"},
        {"name": "note", "hasBody": True, "bodyType": "rich-text"},
        {"name": "tip", "hasBody": True, "bodyType": "rich-text"},
        {"name": "code", "hasBody": True, "bodyType": "plain-text"},
        {"name": "toc", "hasBody": False},
        {"name": "children", "hasBody": False},
        {"name": "excerpt", "hasBody": True, "bodyType": "rich-text"},
        {"name": "include", "hasBody": False},
        {"name": "panel", "hasBody": True, "bodyType": "rich-text"},
    ]


# ============================================================================
# Configuration Fixtures
# ============================================================================


@pytest.fixture
def confluence_config_factory():
    """
    Factory for creating ConfluenceConfig instances with customizable options.

    Returns:
        Callable: Function that creates ConfluenceConfig instances

    Example:
        def test_config(confluence_config_factory):
            config = confluence_config_factory(url="https://custom.atlassian.net/wiki")
            assert "custom" in config.url
    """

    def _create_config(**overrides):
        defaults = {
            "url": "https://example.atlassian.net/wiki",
            "auth_type": "basic",
            "username": "test_user",
            "api_token": "test_token",
        }
        config_data = {**defaults, **overrides}
        return ConfluenceConfig(**config_data)

    return _create_config


@pytest.fixture
def mock_config(confluence_config_factory):
    """
    Create a standard mock ConfluenceConfig instance.

    This fixture provides a consistent ConfluenceConfig for tests that don't
    need custom configuration.

    Returns:
        ConfluenceConfig: Standard test configuration
    """
    return confluence_config_factory()


# ============================================================================
# Environment Fixtures
# ============================================================================


@pytest.fixture
def mock_env_vars():
    """
    Mock environment variables for testing.

    Note: This fixture is maintained for backward compatibility.
    Consider using the environment fixtures from root conftest.py.
    """
    with patch.dict(
        "os.environ",
        {
            "CONFLUENCE_URL": "https://example.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "test_user",
            "CONFLUENCE_API_TOKEN": "test_token",
        },
    ):
        yield


@pytest.fixture
def confluence_auth_environment():
    """
    Fixture providing Confluence-specific authentication environment.

    This sets up environment variables specifically for Confluence authentication
    and can be customized per test.
    """
    auth_config = AuthConfigFactory.create_basic_auth_config()
    confluence_env = {
        "CONFLUENCE_URL": f"{auth_config['url']}/wiki",
        "CONFLUENCE_USERNAME": auth_config["username"],
        "CONFLUENCE_API_TOKEN": auth_config["api_token"],
    }

    with patch.dict(os.environ, confluence_env, clear=False):
        yield confluence_env


# ============================================================================
# Mock Atlassian Client Fixtures
# ============================================================================


@pytest.fixture
def mock_atlassian_confluence(
    session_confluence_spaces, session_confluence_content_types
):
    """
    Enhanced mock of the Atlassian Confluence client.

    This fixture provides a comprehensive mock that uses session-scoped
    data for improved performance and consistency.

    Args:
        session_confluence_spaces: Session-scoped space definitions
        session_confluence_content_types: Session-scoped content type data

    Returns:
        MagicMock: Fully configured mock Confluence client
    """
    with patch("mcp_atlassian.confluence.client.Confluence") as mock:
        confluence_instance = mock.return_value

        # Use original mock data to maintain backward compatibility for existing tests
        confluence_instance.get_all_spaces.return_value = MOCK_SPACES_RESPONSE

        # Set up common return values using both legacy mocks and new factories
        confluence_instance.get_page_by_id.return_value = MOCK_PAGE_RESPONSE
        confluence_instance.get_page_by_title.return_value = MOCK_PAGE_RESPONSE
        confluence_instance.get_all_pages_from_space.return_value = (
            MOCK_PAGES_FROM_SPACE_RESPONSE
        )
        confluence_instance.get_page_comments.return_value = MOCK_COMMENTS_RESPONSE
        confluence_instance.get_page_labels.return_value = MOCK_LABELS_RESPONSE
        confluence_instance.cql.return_value = MOCK_CQL_SEARCH_RESPONSE

        # Enhanced responses using factories
        confluence_instance.create_page.return_value = ConfluencePageFactory.create(
            page_id="123456789", title="New Test Page"
        )

        # Mock update_page to return None (as the actual method does)
        confluence_instance.update_page.return_value = None

        # Mock delete_page to return None
        confluence_instance.delete_page.return_value = None

        # Mock page history
        confluence_instance.get_page_history.return_value = {
            "results": [
                {
                    "version": {"number": 1},
                    "when": "2023-01-01T12:00:00.000Z",
                    "by": {"displayName": "Test User"},
                    "message": "Initial version",
                }
            ]
        }

        # Mock page ancestors
        confluence_instance.get_page_ancestors.return_value = [
            ConfluencePageFactory.create(page_id="parent123", title="Parent Page")
        ]

        # Mock page children
        confluence_instance.get_page_child_by_type.return_value = {
            "results": [
                ConfluencePageFactory.create(page_id="child123", title="Child Page")
            ]
        }

        yield confluence_instance


@pytest.fixture
def enhanced_mock_confluence_client():
    """
    Enhanced mock Confluence client using the new factory system.

    This provides a more flexible mock that can be easily customized
    and integrates with the factory system.

    Returns:
        MagicMock: Enhanced mock Confluence client with factory integration
    """
    return MockAtlassianClient.create_confluence_client()


@pytest.fixture
def mock_atlassian_confluence_with_session_data(
    session_confluence_spaces, session_confluence_content_types
):
    """
    Alternative mock using session-scoped data for new tests.

    This fixture is recommended for new tests as it uses the efficient
    session-scoped data. Existing tests should continue using
    mock_atlassian_confluence for compatibility.

    Args:
        session_confluence_spaces: Session-scoped space definitions
        session_confluence_content_types: Session-scoped content type data

    Returns:
        MagicMock: Mock Confluence client with session-scoped data
    """
    with patch("mcp_atlassian.confluence.client.Confluence") as mock:
        confluence_instance = mock.return_value

        # Use session-scoped data for improved performance
        confluence_instance.get_all_spaces.return_value = {
            "results": session_confluence_spaces,
            "size": len(session_confluence_spaces),
        }

        # Enhanced responses using factories
        confluence_instance.get_page_by_id.return_value = ConfluencePageFactory.create()
        confluence_instance.get_page_by_title.return_value = (
            ConfluencePageFactory.create()
        )
        confluence_instance.create_page.return_value = ConfluencePageFactory.create(
            page_id="123456789", title="New Test Page"
        )

        # Use session data for content types
        confluence_instance.get_content_types.return_value = (
            session_confluence_content_types
        )

        yield confluence_instance


# ============================================================================
# Preprocessor Fixtures
# ============================================================================


@pytest.fixture
def mock_preprocessor():
    """
    Mock the TextPreprocessor with enhanced functionality.

    This fixture provides a preprocessor mock that can be customized
    for testing different content processing scenarios.

    Returns:
        MagicMock: Mock preprocessor with common methods
    """
    preprocessor_instance = MagicMock()

    # Default processing behavior
    preprocessor_instance.process_html_content.return_value = (
        "<p>Processed HTML</p>",
        "Processed Markdown",
    )

    # Additional processing methods
    preprocessor_instance.clean_html.return_value = "<p>Clean HTML</p>"
    preprocessor_instance.html_to_markdown.return_value = "# Markdown Content"
    preprocessor_instance.markdown_to_html.return_value = "<h1>HTML Content</h1>"

    yield preprocessor_instance


@pytest.fixture
def preprocessor_factory():
    """
    Factory for creating preprocessor mocks with different behaviors.

    Returns:
        Dict[str, Callable]: Factory functions for different preprocessor types

    Example:
        def test_preprocessing(preprocessor_factory):
            html_processor = preprocessor_factory["html_to_markdown"]()
            markdown_processor = preprocessor_factory["markdown_to_html"]()
    """
    return {
        "html_to_markdown": MockPreprocessor.create_html_to_markdown,
        "markdown_to_html": MockPreprocessor.create_markdown_to_html,
    }


# ============================================================================
# Client Instance Fixtures
# ============================================================================


@pytest.fixture
def confluence_client(mock_config, mock_atlassian_confluence, mock_preprocessor):
    """
    Create a ConfluenceClient instance with mocked dependencies.

    This fixture provides a fully functional ConfluenceClient with mocked
    Atlassian API calls and content preprocessing for testing.

    Args:
        mock_config: Mock configuration
        mock_atlassian_confluence: Mock Atlassian client
        mock_preprocessor: Mock text preprocessor

    Returns:
        ConfluenceClient: Configured client instance
    """
    # Create a client with a mocked configuration
    with patch(
        "mcp_atlassian.preprocessing.TextPreprocessor"
    ) as mock_text_preprocessor:
        mock_text_preprocessor.return_value = mock_preprocessor

        client = ConfluenceClient(config=mock_config)
        # Replace the actual Confluence instance with our mock
        client.confluence = mock_atlassian_confluence
        # Replace the actual preprocessor with our mock
        client.preprocessor = mock_preprocessor
        yield client


# ============================================================================
# Specialized Test Data Fixtures
# ============================================================================


@pytest.fixture
def make_confluence_page_with_content():
    """
    Factory fixture for creating Confluence pages with rich content.

    Returns:
        Callable: Function that creates page data with content

    Example:
        def test_page_content(make_confluence_page_with_content):
            page = make_confluence_page_with_content(
                title="Rich Page",
                content="<h1>Header</h1><p>Content</p>",
                labels=["test", "content"]
            )
    """

    def _create_page_with_content(
        title: str = "Test Page",
        content: str = "<p>Test content</p>",
        labels: list[str] = None,
        **overrides,
    ):
        labels = labels or ["test"]
        page = ConfluencePageFactory.create(title=title, **overrides)

        # Add rich content
        page["body"]["storage"]["value"] = content

        # Add labels
        page["metadata"] = {
            "labels": {"results": [{"name": label} for label in labels]}
        }

        # Add version info
        page["version"]["message"] = f"Updated {title}"

        return page

    return _create_page_with_content


@pytest.fixture
def make_confluence_search_results():
    """
    Factory fixture for creating Confluence search results.

    Returns:
        Callable: Function that creates CQL search results

    Example:
        def test_search(make_confluence_search_results):
            results = make_confluence_search_results(
                pages=["Page 1", "Page 2"],
                total=2
            )
    """

    def _create_search_results(pages: list[str] = None, total: int = None, **overrides):
        if pages is None:
            pages = ["Test Page 1", "Test Page 2", "Test Page 3"]
        if total is None:
            total = len(pages)

        page_objects = [
            ConfluencePageFactory.create(page_id=str(i), title=title)
            for i, title in enumerate(pages, 1)
        ]

        defaults = {
            "results": page_objects,
            "totalSize": total,
            "start": 0,
            "limit": 25,
        }

        return {**defaults, **overrides}

    return _create_search_results


@pytest.fixture
def make_confluence_space():
    """
    Factory fixture for creating Confluence spaces.

    Returns:
        Callable: Function that creates space data

    Example:
        def test_space(make_confluence_space):
            space = make_confluence_space(
                key="CUSTOM",
                name="Custom Space",
                type="personal"
            )
    """

    def _create_space(
        key: str = "TEST",
        name: str = "Test Space",
        space_type: str = "global",
        **overrides,
    ):
        defaults = {
            "id": 12345,
            "key": key,
            "name": name,
            "type": space_type,
            "status": "current",
            "description": {"plain": {"value": f"{name} for testing"}},
            "_links": {
                "webui": f"/spaces/{key}",
                "self": f"https://test.atlassian.net/wiki/rest/api/space/{key}",
            },
        }

        return {**defaults, **overrides}

    return _create_space


# ============================================================================
# Integration Test Fixtures
# ============================================================================


@pytest.fixture
def confluence_integration_client(session_auth_configs):
    """
    Create a ConfluenceClient for integration testing.

    This fixture creates a client that can be used for integration tests
    when real API credentials are available.

    Args:
        session_auth_configs: Session-scoped auth configurations

    Returns:
        Optional[ConfluenceClient]: Real client if credentials available, None otherwise
    """
    # Check if integration test environment variables are set
    required_vars = ["CONFLUENCE_URL", "CONFLUENCE_USERNAME", "CONFLUENCE_API_TOKEN"]
    if not all(os.environ.get(var) for var in required_vars):
        pytest.skip("Integration test environment variables not set")

    config = ConfluenceConfig(
        url=os.environ["CONFLUENCE_URL"],
        auth_type="basic",
        username=os.environ["CONFLUENCE_USERNAME"],
        api_token=os.environ["CONFLUENCE_API_TOKEN"],
    )

    return ConfluenceClient(config=config)


# ============================================================================
# Parameterized Fixtures
# ============================================================================


@pytest.fixture
def parametrized_confluence_content_type(request):
    """
    Parametrized fixture for testing with different Confluence content types.

    Use with pytest.mark.parametrize to test functionality across
    different content types.

    Example:
        @pytest.mark.parametrize("parametrized_confluence_content_type",
                               ["page", "blogpost"], indirect=True)
        def test_content_types(parametrized_confluence_content_type):
            # Test runs once for each content type
            pass
    """
    content_type = request.param
    return ConfluencePageFactory.create(type=content_type)


@pytest.fixture
def parametrized_confluence_space_type(request):
    """
    Parametrized fixture for testing with different Confluence space types.

    Use with pytest.mark.parametrize to test functionality across
    different space types.
    """
    space_type = request.param
    return {
        "key": "TEST",
        "name": "Test Space",
        "type": space_type,
        "status": "current",
    }
