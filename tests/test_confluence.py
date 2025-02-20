from unittest.mock import patch

import pytest
from mcp_atlassian.confluence import ConfluenceFetcher
from mcp_atlassian.document_types import Document

from tests.fixtures.confluence_mocks import (
    MOCK_COMMENTS_RESPONSE,
    MOCK_CQL_SEARCH_RESPONSE,
    MOCK_PAGE_RESPONSE,
    MOCK_PAGES_FROM_SPACE_RESPONSE,
    MOCK_SPACES_RESPONSE,
)


@pytest.fixture
def mock_env_vars():
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
def mock_confluence():
    with patch("mcp_atlassian.confluence.Confluence") as mock:
        confluence_instance = mock.return_value

        confluence_instance.get_all_spaces.return_value = MOCK_SPACES_RESPONSE
        confluence_instance.get_page_by_id.return_value = MOCK_PAGE_RESPONSE
        confluence_instance.get_page_by_title.return_value = MOCK_PAGE_RESPONSE
        confluence_instance.get_all_pages_from_space.return_value = MOCK_PAGES_FROM_SPACE_RESPONSE
        confluence_instance.get_page_comments.return_value = MOCK_COMMENTS_RESPONSE
        confluence_instance.cql.return_value = MOCK_CQL_SEARCH_RESPONSE

        yield confluence_instance


@pytest.fixture
def fetcher(mock_env_vars, mock_confluence):
    return ConfluenceFetcher()


def test_init_missing_env_vars():
    with patch.dict("os.environ", clear=True):
        with pytest.raises(ValueError, match="Missing required Confluence environment variables"):
            ConfluenceFetcher()


def test_get_spaces(fetcher, mock_confluence):
    spaces = fetcher.get_spaces()
    mock_confluence.get_all_spaces.assert_called_once_with(start=0, limit=10)
    assert spaces == MOCK_SPACES_RESPONSE


def test_get_page_content(fetcher, mock_confluence):
    page_id = "987654321"
    document = fetcher.get_page_content(page_id)

    mock_confluence.get_page_by_id.assert_called_once_with(page_id=page_id, expand="body.storage,version,space")

    assert isinstance(document, Document)
    assert document.metadata["page_id"] == page_id
    assert document.metadata["title"] == "Example Meeting Notes"
    assert document.metadata["space_key"] == "PROJ"
    assert document.metadata["space_name"] == "Project Space"
    assert document.metadata["author_name"] == "Example User (Unlicensed)"
    assert document.metadata["version"] == 1
    assert document.metadata["last_modified"] == "2024-01-01T09:00:00.000Z"
    assert document.metadata["url"] == "https://example.atlassian.net/wiki/spaces/PROJ/pages/987654321"


def test_get_page_comments(fetcher, mock_confluence):
    page_id = "987654321"
    comments = fetcher.get_page_comments(page_id)

    mock_confluence.get_page_by_id.assert_called_once_with(page_id=page_id, expand="space")
    mock_confluence.get_page_comments.assert_called_once_with(
        content_id=page_id, expand="body.view.value,version", depth="all"
    )

    assert len(comments) == 1
    assert isinstance(comments[0], Document)
    assert comments[0].metadata["comment_id"] == "456789123"
    assert comments[0].metadata["author_name"] == "John Doe"


def test_search(fetcher, mock_confluence):
    cql = "space = PROJ"
    documents = fetcher.search(cql, limit=10)

    mock_confluence.cql.assert_called_once_with(cql=cql, limit=10)

    assert len(documents) == 1
    assert isinstance(documents[0], Document)
    assert documents[0].metadata["page_id"] == "123456789"
    assert documents[0].metadata["title"] == "2024-01-01: Team Progress Meeting 01"
    assert documents[0].metadata["space"] == "Team Space"
    assert documents[0].metadata["type"] == "page"
    assert documents[0].metadata["last_modified"] == "2024-01-01T08:00:00.000Z"
    assert (
        documents[0].metadata["url"]
        == "https://example.atlassian.net/wiki/spaces/TEAM/pages/123456789/2024-01-01+Team+Progress+Meeting+01"
    )
    assert (
        documents[0].page_content == "📅 Date\n2024-01-01\n👥 Participants\nJohn Smith\nJane Doe\nBob Wilson\n!-@123456"
    )


def test_get_space_pages(fetcher, mock_confluence):
    space_key = "PROJ"
    documents = fetcher.get_space_pages(space_key)

    mock_confluence.get_all_pages_from_space.assert_called_once_with(
        space=space_key, start=0, limit=10, expand="body.storage"
    )

    assert len(documents) == 1
    assert isinstance(documents[0], Document)
    assert documents[0].metadata["page_id"] == "123456789"
    assert documents[0].metadata["title"] == "Sample Research Paper Title"
    assert documents[0].metadata["space_key"] == space_key


def test_get_page_by_title(fetcher, mock_confluence):
    space_key = "PROJ"
    title = "Example Page"

    document = fetcher.get_page_by_title(space_key, title)

    mock_confluence.get_page_by_title.assert_called_once_with(
        space=space_key, title=title, expand="body.storage,version"
    )

    assert isinstance(document, Document)
    assert document.metadata["page_id"] == "987654321"
    assert document.metadata["title"] == "Example Meeting Notes"
    assert document.metadata["space_key"] == space_key


def test_get_page_by_title_not_found(fetcher, mock_confluence):
    mock_confluence.get_page_by_title.return_value = None
    document = fetcher.get_page_by_title("PROJ", "Nonexistent Page")
    assert document is None


def test_search_with_error(fetcher, mock_confluence):
    mock_confluence.cql.side_effect = Exception("API Error")

    documents = fetcher.search("space = PROJ")

    mock_confluence.cql.assert_called_once_with(cql="space = PROJ", limit=10)
    assert documents == []


def test_get_page_by_title_with_error(fetcher, mock_confluence):
    mock_confluence.get_page_by_title.side_effect = Exception("API Error")

    document = fetcher.get_page_by_title("PROJ", "Example Page")

    mock_confluence.get_page_by_title.assert_called_once_with(
        space="PROJ", title="Example Page", expand="body.storage,version"
    )
    assert document is None
