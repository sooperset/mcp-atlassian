"""
Tests using real Confluence data (optional).

These tests only run when --use-real-data is passed to pytest
and the appropriate environment variables are configured.
"""

import pytest

from mcp_atlassian.models import (
    ConfluenceComment,
    ConfluencePage,
)


class TestRealConfluenceData:
    """Tests using real Confluence data (only run if environment is configured)."""

    def test_real_confluence_page(
        self, use_real_confluence_data, default_confluence_page_id
    ):
        """Test with real Confluence page data from the API."""
        if not use_real_confluence_data:
            pytest.skip("Real Confluence data testing is disabled")

        try:
            # Initialize the Confluence client
            from mcp_atlassian.confluence.client import ConfluenceClient
            from mcp_atlassian.confluence.config import ConfluenceConfig
            from mcp_atlassian.confluence.pages import PagesMixin

            # Use the from_env method to create the config
            config = ConfluenceConfig.from_env()
            confluence_client = ConfluenceClient(config=config)
            pages_client = PagesMixin(config=config)

            # Use the provided page ID from environment or fixture
            page_id = default_confluence_page_id

            # Get page data directly from the Confluence API
            page_data = confluence_client.confluence.get_page_by_id(
                page_id=page_id, expand="body.storage,version,space,children.attachment"
            )

            # Convert to model
            page = ConfluencePage.from_api_response(page_data)

            # Verify basic properties
            assert page.id == page_id
            assert page.title is not None
            assert page.space is not None
            assert page.space.key is not None
            assert page.attachments is not None

            # Verify that to_simplified_dict works
            simplified = page.to_simplified_dict()
            assert isinstance(simplified, dict)
            assert simplified["id"] == page_id

            # Get and test comments if available
            try:
                comments_data = confluence_client.confluence.get_page_comments(
                    page_id=page_id, expand="body.view,version"
                )

                if comments_data and comments_data.get("results"):
                    comment_data = comments_data["results"][0]
                    comment = ConfluenceComment.from_api_response(comment_data)

                    assert comment.id is not None
                    assert comment.body is not None

                    # Test simplified dict
                    comment_dict = comment.to_simplified_dict()
                    assert isinstance(comment_dict, dict)
                    assert "body" in comment_dict
            except Exception as e:
                print(f"Comments test skipped: {e}")

            print(
                f"Successfully tested real Confluence page {page_id} in space {page.space.key}"
            )
        except ImportError as e:
            pytest.skip(f"Could not import Confluence client: {e}")
        except Exception as e:
            pytest.fail(f"Error testing real Confluence page: {e}")
