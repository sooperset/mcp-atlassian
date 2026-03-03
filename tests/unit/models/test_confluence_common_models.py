"""
Tests for common Confluence Pydantic models.

Tests for ConfluenceAttachment, ConfluenceUser, ConfluenceSpace,
ConfluenceVersion, ConfluenceComment, and ConfluenceLabel models.
"""

from mcp_atlassian.models import (
    ConfluenceAttachment,
    ConfluenceComment,
    ConfluenceLabel,
    ConfluenceSpace,
    ConfluenceUser,
    ConfluenceVersion,
)
from mcp_atlassian.models.constants import EMPTY_STRING


class TestConfluenceAttachment:
    """Tests for the ConfluenceAttachment model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a ConfluenceAttachment from valid API data."""
        attachment_data = {
            "id": "att105348",
            "type": "attachment",
            "status": "current",
            "title": "random_geometric_image.svg",
            "extensions": {"mediaType": "application/binary", "fileSize": 1098},
        }

        attachment = ConfluenceAttachment.from_api_response(attachment_data)

        assert attachment.id == "att105348"
        assert attachment.title == "random_geometric_image.svg"
        assert attachment.type == "attachment"
        assert attachment.status == "current"
        assert attachment.media_type == "application/binary"
        assert attachment.file_size == 1098

    def test_from_api_response_with_enhanced_fields(self):
        """Test creating a ConfluenceAttachment with version and author data."""
        attachment_data = {
            "id": "att105348",
            "type": "attachment",
            "status": "current",
            "title": "document.pdf",
            "extensions": {"mediaType": "application/pdf", "fileSize": 2048},
            "version": {
                "number": 3,
                "when": "2024-01-15T10:30:00.000Z",
                "by": {"accountId": "user123", "displayName": "John Doe"},
            },
            "_links": {"download": "/download/attachments/123456/document.pdf"},
            "created": "2024-01-01T09:00:00.000Z",
        }

        attachment = ConfluenceAttachment.from_api_response(attachment_data)

        assert attachment.id == "att105348"
        assert attachment.title == "document.pdf"
        assert attachment.media_type == "application/pdf"
        assert attachment.file_size == 2048
        # New fields
        assert attachment.download_url == "/download/attachments/123456/document.pdf"
        assert attachment.version_number == 3
        assert attachment.version_when == "2024-01-15T10:30:00.000Z"
        assert attachment.created == "2024-01-01T09:00:00.000Z"
        assert attachment.author_display_name == "John Doe"
        assert attachment.author_account_id == "user123"

    def test_from_api_response_with_metadata_author(self):
        """Test attachment with author in metadata instead of version."""
        attachment_data = {
            "id": "att105349",
            "title": "image.png",
            "metadata": {
                "mediaType": "image/png",
                "author": {"accountId": "user456", "displayName": "Jane Smith"},
            },
            "extensions": {"fileSize": 512},
        }

        attachment = ConfluenceAttachment.from_api_response(attachment_data)

        assert attachment.author_display_name == "Jane Smith"
        assert attachment.author_account_id == "user456"

    def test_from_api_response_with_empty_data(self):
        """Test creating a ConfluenceAttachment from empty data."""
        attachment = ConfluenceAttachment.from_api_response({})

        # Should use default values
        assert attachment.id is None
        assert attachment.title is None
        assert attachment.type is None
        assert attachment.status is None
        assert attachment.media_type is None
        assert attachment.file_size is None
        # New fields should also be None
        assert attachment.download_url is None
        assert attachment.version_number is None
        assert attachment.version_when is None
        assert attachment.created is None
        assert attachment.author_display_name is None
        assert attachment.author_account_id is None

    def test_from_api_response_with_none_data(self):
        """Test creating a ConfluenceAttachment from None data."""
        attachment = ConfluenceAttachment.from_api_response(None)

        # Should use default values
        assert attachment.id is None
        assert attachment.title is None
        assert attachment.type is None
        assert attachment.status is None
        assert attachment.media_type is None
        assert attachment.file_size is None

    def test_to_simplified_dict_basic(self):
        """Test converting ConfluenceAttachment to a simplified dictionary."""
        attachment = ConfluenceAttachment(
            id="att105348",
            title="random_geometric_image.svg",
            type="attachment",
            status="current",
            media_type="application/binary",
            file_size=1098,
        )

        simplified = attachment.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["id"] == "att105348"
        assert simplified["title"] == "random_geometric_image.svg"
        assert simplified["type"] == "attachment"
        assert simplified["status"] == "current"
        assert simplified["media_type"] == "application/binary"
        assert simplified["file_size"] == 1098
        # New fields should not be present when not set
        assert "download_url" not in simplified
        assert "version_number" not in simplified

    def test_to_simplified_dict_with_enhanced_fields(self):
        """Test simplified dict includes enhanced fields when present."""
        attachment = ConfluenceAttachment(
            id="att105348",
            title="document.pdf",
            type="attachment",
            status="current",
            media_type="application/pdf",
            file_size=2048,
            download_url="/download/attachments/123456/document.pdf",
            version_number=3,
            version_when="2024-01-15T10:30:00.000Z",
            created="2024-01-01T09:00:00.000Z",
            author_display_name="John Doe",
            author_account_id="user123",
        )

        simplified = attachment.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["download_url"] == "/download/attachments/123456/document.pdf"
        assert simplified["version_number"] == 3
        assert simplified["version_when"] == "2024-01-15T10:30:00.000Z"
        assert simplified["created"] == "2024-01-01T09:00:00.000Z"
        assert simplified["author_display_name"] == "John Doe"
        # account_id is intentionally not included in simplified dict

    def test_to_simplified_dict_conditional_fields(self):
        """Test that optional fields are only included when they have values."""
        # Attachment with only some enhanced fields
        attachment = ConfluenceAttachment(
            id="att105348",
            title="document.pdf",
            download_url="/download/attachments/123456/document.pdf",
            version_number=1,
            # Other optional fields are None
        )

        simplified = attachment.to_simplified_dict()

        assert "download_url" in simplified
        assert "version_number" in simplified
        # These should not be present
        assert "version_when" not in simplified
        assert "created" not in simplified
        assert "author_display_name" not in simplified


class TestConfluenceUser:
    """Tests for the ConfluenceUser model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a ConfluenceUser from valid API data."""
        user_data = {
            "accountId": "user123",
            "displayName": "Test User",
            "email": "test@example.com",
            "profilePicture": {
                "path": "/wiki/aa-avatar/user123",
                "width": 48,
                "height": 48,
            },
            "accountStatus": "active",
            "locale": "en_US",
        }

        user = ConfluenceUser.from_api_response(user_data)

        assert user.account_id == "user123"
        assert user.display_name == "Test User"
        assert user.email == "test@example.com"
        assert user.profile_picture == "/wiki/aa-avatar/user123"
        assert user.is_active is True
        assert user.locale == "en_US"

    def test_from_api_response_with_empty_data(self):
        """Test creating a ConfluenceUser from empty data."""
        user = ConfluenceUser.from_api_response({})

        # Should use default values
        assert user.account_id is None
        assert user.display_name == "Unassigned"
        assert user.email is None
        assert user.profile_picture is None
        assert user.is_active is True
        assert user.locale is None

    def test_from_api_response_with_none_data(self):
        """Test creating a ConfluenceUser from None data."""
        user = ConfluenceUser.from_api_response(None)

        # Should use default values
        assert user.account_id is None
        assert user.display_name == "Unassigned"
        assert user.email is None
        assert user.profile_picture is None
        assert user.is_active is True
        assert user.locale is None

    def test_to_simplified_dict(self):
        """Test converting ConfluenceUser to a simplified dictionary."""
        user = ConfluenceUser(
            account_id="user123",
            display_name="Test User",
            email="test@example.com",
            profile_picture="/wiki/aa-avatar/user123",
            is_active=True,
            locale="en_US",
        )

        simplified = user.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["display_name"] == "Test User"
        assert simplified["email"] == "test@example.com"
        assert simplified["profile_picture"] == "/wiki/aa-avatar/user123"
        assert "account_id" not in simplified  # Not included in simplified dict
        assert "locale" not in simplified  # Not included in simplified dict


class TestConfluenceSpace:
    """Tests for the ConfluenceSpace model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a ConfluenceSpace from valid API data."""
        space_data = {
            "id": "123456",
            "key": "TEST",
            "name": "Test Space",
            "type": "global",
            "status": "current",
        }

        space = ConfluenceSpace.from_api_response(space_data)

        assert space.id == "123456"
        assert space.key == "TEST"
        assert space.name == "Test Space"
        assert space.type == "global"
        assert space.status == "current"

    def test_from_api_response_with_empty_data(self):
        """Test creating a ConfluenceSpace from empty data."""
        space = ConfluenceSpace.from_api_response({})

        # Should use default values
        assert space.id == "0"
        assert space.key == ""
        assert space.name == "Unknown"
        assert space.type == "global"
        assert space.status == "current"

    def test_to_simplified_dict(self):
        """Test converting ConfluenceSpace to a simplified dictionary."""
        space = ConfluenceSpace(
            id="123456", key="TEST", name="Test Space", type="global", status="current"
        )

        simplified = space.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["key"] == "TEST"
        assert simplified["name"] == "Test Space"
        assert simplified["type"] == "global"
        assert simplified["status"] == "current"
        assert "id" not in simplified  # Not included in simplified dict


class TestConfluenceVersion:
    """Tests for the ConfluenceVersion model."""

    def test_from_api_response_with_valid_data(self):
        """Test creating a ConfluenceVersion from valid API data."""
        version_data = {
            "number": 5,
            "when": "2024-01-01T09:00:00.000Z",
            "message": "Updated content",
            "by": {
                "accountId": "user123",
                "displayName": "Test User",
                "email": "test@example.com",
            },
        }

        version = ConfluenceVersion.from_api_response(version_data)

        assert version.number == 5
        assert version.when == "2024-01-01T09:00:00.000Z"
        assert version.message == "Updated content"
        assert version.by is not None
        assert version.by.display_name == "Test User"

    def test_from_api_response_with_empty_data(self):
        """Test creating a ConfluenceVersion from empty data."""
        version = ConfluenceVersion.from_api_response({})

        # Should use default values
        assert version.number == 0
        assert version.when == ""
        assert version.message is None
        assert version.by is None

    def test_to_simplified_dict(self):
        """Test converting ConfluenceVersion to a simplified dictionary."""
        version = ConfluenceVersion(
            number=5,
            when="2024-01-01T09:00:00.000Z",
            message="Updated content",
            by=ConfluenceUser(account_id="user123", display_name="Test User"),
        )

        simplified = version.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["number"] == 5
        assert simplified["when"] == "2024-01-01 09:00:00"  # Formatted timestamp
        assert simplified["message"] == "Updated content"
        assert simplified["by"] == "Test User"


class TestConfluenceComment:
    """Tests for the ConfluenceComment model."""

    def test_from_api_response_with_valid_data(self, confluence_comments_data):
        """Test creating a ConfluenceComment from valid API data."""
        comment_data = confluence_comments_data["results"][0]

        comment = ConfluenceComment.from_api_response(comment_data)

        assert comment.id == "456789123"
        assert comment.title == "Re: Technical Design Document"
        assert comment.body != ""  # Body should be populated from "value" field
        assert comment.author is not None
        assert comment.author.display_name == "John Doe"
        assert comment.type == "comment"

    def test_from_api_response_with_empty_data(self):
        """Test creating a ConfluenceComment from empty data."""
        comment = ConfluenceComment.from_api_response({})

        # Should use default values
        assert comment.id == "0"
        assert comment.title is None
        assert comment.body == ""
        assert comment.created == ""
        assert comment.updated == ""
        assert comment.author is None
        assert comment.type == "comment"

    def test_to_simplified_dict(self):
        """Test converting ConfluenceComment to a simplified dictionary."""
        comment = ConfluenceComment(
            id="456789123",
            title="Test Comment",
            body="This is a test comment",
            created="2024-01-01T10:00:00.000Z",
            updated="2024-01-01T10:00:00.000Z",
            author=ConfluenceUser(account_id="user123", display_name="Comment Author"),
            type="comment",
        )

        simplified = comment.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["id"] == "456789123"
        assert simplified["title"] == "Test Comment"
        assert simplified["body"] == "This is a test comment"
        assert simplified["created"] == "2024-01-01 10:00:00"  # Formatted timestamp
        assert simplified["updated"] == "2024-01-01 10:00:00"  # Formatted timestamp
        assert simplified["author"] == "Comment Author"


class TestConfluenceLabel:
    """Tests for the ConfluenceLabel model."""

    def test_from_api_response_with_valid_data(self, confluence_labels_data):
        """Test creating a ConfluenceLabel from valid API data."""
        label_data = confluence_labels_data["results"][0]

        label = ConfluenceLabel.from_api_response(label_data)

        assert label.id == "456789123"
        assert label.name == "meeting-notes"
        assert label.prefix == "global"
        assert label.label == "meeting-notes"
        assert label.type == "label"

    def test_from_api_response_with_empty_data(self):
        """Test creating a ConfluenceLabel from empty data."""
        label = ConfluenceLabel.from_api_response({})

        # Should use default values
        assert label.id == "0"
        assert label.name == EMPTY_STRING
        assert label.prefix == "global"
        assert label.label == EMPTY_STRING
        assert label.type == "label"

    def test_to_simplified_dict(self):
        """Test converting ConfluenceLabel to a simplified dictionary."""
        label = ConfluenceLabel(
            id="456789123",
            name="test",
            prefix="my",
            label="test",
            type="label",
        )

        simplified = label.to_simplified_dict()

        assert isinstance(simplified, dict)
        assert simplified["id"] == "456789123"
        assert simplified["name"] == "test"
        assert simplified["prefix"] == "my"
        assert simplified["label"] == "test"
