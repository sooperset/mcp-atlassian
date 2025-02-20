import pytest
from mcp_atlassian.preprocessing import TextPreprocessor

from tests.fixtures.confluence_mocks import MOCK_COMMENTS_RESPONSE, MOCK_PAGE_RESPONSE
from tests.fixtures.jira_mocks import MOCK_JIRA_ISSUE_RESPONSE


class MockConfluenceClient:
    def get_user_details_by_accountid(self, account_id):
        # Mock user details response based on the format in MOCK_PAGE_RESPONSE
        return {
            "displayName": f"Test User {account_id}",
            "accountType": "atlassian",
            "accountStatus": "active",
        }


@pytest.fixture
def preprocessor():
    return TextPreprocessor("https://example.atlassian.net", None)


@pytest.fixture
def preprocessor_with_confluence():
    return TextPreprocessor("https://example.atlassian.net", MockConfluenceClient())


def test_init():
    """Test TextPreprocessor initialization."""
    processor = TextPreprocessor("https://example.atlassian.net/")
    assert processor.base_url == "https://example.atlassian.net"
    assert processor.confluence_client is None


def test_process_confluence_page_content(preprocessor_with_confluence):
    """Test processing Confluence page content using mock data."""
    html_content = MOCK_PAGE_RESPONSE["body"]["storage"]["value"]
    processed_html, processed_markdown = preprocessor_with_confluence.process_html_content(html_content)

    # Verify user mention is processed
    assert "@Test User user123" in processed_markdown

    # Verify basic HTML elements are converted
    assert "Date" in processed_markdown
    assert "Goals" in processed_markdown
    assert "Example goal" in processed_markdown


def test_process_confluence_comment_content(preprocessor):
    """Test processing Confluence comment content using mock data."""
    html_content = MOCK_COMMENTS_RESPONSE["results"][0]["body"]["view"]["value"]
    processed_html, processed_markdown = preprocessor.process_html_content(html_content)

    assert "Comment content here" in processed_markdown


def test_clean_jira_issue_content(preprocessor):
    """Test cleaning Jira issue content using mock data."""
    description = MOCK_JIRA_ISSUE_RESPONSE["fields"]["description"]
    cleaned_text = preprocessor.clean_jira_text(description)

    assert "test issue description" in cleaned_text.lower()

    # Test comment cleaning
    comment = MOCK_JIRA_ISSUE_RESPONSE["fields"]["comment"]["comments"][0]["body"]
    cleaned_comment = preprocessor.clean_jira_text(comment)

    assert "test comment" in cleaned_comment.lower()


def test_process_html_content_basic(preprocessor):
    """Test basic HTML content processing."""
    html = "<p>Simple text</p>"
    processed_html, processed_markdown = preprocessor.process_html_content(html)

    assert processed_html == "<p>Simple text</p>"
    assert processed_markdown.strip() == "Simple text"


def test_process_html_content_with_user_mentions(preprocessor_with_confluence):
    """Test HTML content processing with user mentions."""
    html = """
    <ac:link>
        <ri:user ri:account-id="123456"/>
    </ac:link>
    <p>Some text</p>
    """
    processed_html, processed_markdown = preprocessor_with_confluence.process_html_content(html)

    assert "@Test User 123456" in processed_html
    assert "@Test User 123456" in processed_markdown


def test_clean_jira_text_empty(preprocessor):
    """Test cleaning empty Jira text."""
    assert preprocessor.clean_jira_text("") == ""
    assert preprocessor.clean_jira_text(None) == ""


def test_clean_jira_text_user_mentions(preprocessor):
    """Test cleaning Jira text with user mentions."""
    text = "Hello [~accountid:123456]!"
    cleaned = preprocessor.clean_jira_text(text)
    assert cleaned == "Hello User:123456!"


def test_clean_jira_text_smart_links(preprocessor):
    """Test cleaning Jira text with smart links."""
    base_url = "https://example.atlassian.net"

    # Test Jira issue link
    text = f"[Issue|{base_url}/browse/PROJ-123|smart-link]"
    cleaned = preprocessor.clean_jira_text(text)
    assert cleaned == f"[PROJ-123]({base_url}/browse/PROJ-123)"

    # Test Confluence page link from mock data
    confluence_url = f"{base_url}/wiki/spaces/PROJ/pages/987654321/Example+Meeting+Notes"
    text = f"[Meeting Notes|{confluence_url}|smart-link]"
    cleaned = preprocessor.clean_jira_text(text)
    assert cleaned == f"[Example Meeting Notes]({confluence_url})"


def test_clean_jira_text_html_content(preprocessor):
    """Test cleaning Jira text with HTML content."""
    text = "<p>This is <b>bold</b> text</p>"
    cleaned = preprocessor.clean_jira_text(text)
    assert cleaned.strip() == "This is **bold** text"


def test_clean_jira_text_combined(preprocessor):
    """Test cleaning Jira text with multiple elements."""
    base_url = "https://example.atlassian.net"
    text = f"""
    <p>Hello [~accountid:123456]!</p>
    <p>Check out [PROJ-123|{base_url}/browse/PROJ-123|smart-link]</p>
    """
    cleaned = preprocessor.clean_jira_text(text)
    assert "Hello User:123456!" in cleaned
    assert f"[PROJ-123]({base_url}/browse/PROJ-123)" in cleaned


def test_process_html_content_error_handling(preprocessor):
    """Test error handling in process_html_content."""
    with pytest.raises(Exception):
        preprocessor.process_html_content(None)


def test_clean_jira_text_with_invalid_html(preprocessor):
    """Test cleaning Jira text with invalid HTML."""
    text = "<p>Unclosed paragraph with <b>bold</b"
    cleaned = preprocessor.clean_jira_text(text)
    assert "Unclosed paragraph with **bold**" in cleaned


def test_process_mentions_error_handling(preprocessor):
    """Test error handling in _process_mentions."""
    text = "[~accountid:invalid]"
    processed = preprocessor._process_mentions(text, r"\[~accountid:(.*?)\]")
    assert "User:invalid" in processed
