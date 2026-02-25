"""Tests for the shared MIME detection utility."""

import pytest

from mcp_atlassian.utils.media import is_image_attachment


@pytest.mark.parametrize(
    ("media_type", "filename", "expected"),
    [
        ("image/png", "x.png", (True, "image/png")),
        ("image/jpeg", "photo.jpg", (True, "image/jpeg")),
        (
            "application/octet-stream",
            "shot.jpg",
            (True, "image/jpeg"),
        ),
        (
            "application/binary",
            "img.png",
            (True, "image/png"),
        ),
        (
            "application/octet-stream",
            "doc.pdf",
            (False, "application/octet-stream"),
        ),
        # None MIME + image extension → detected as image
        (None, "photo.png", (True, "image/png")),
        # None MIME + non-image extension → not an image
        (None, "doc.pdf", (False, "application/octet-stream")),
        # Both None → not an image
        (None, None, (False, "application/octet-stream")),
        # Explicit non-image MIME
        ("text/plain", "file.txt", (False, "text/plain")),
    ],
    ids=[
        "explicit-png",
        "explicit-jpeg",
        "octet-stream-jpg-ext",
        "binary-png-ext",
        "octet-stream-pdf-ext",
        "none-mime-image-ext",
        "none-mime-pdf-ext",
        "both-none",
        "text-plain",
    ],
)
def test_is_image_attachment(
    media_type: str | None,
    filename: str | None,
    expected: tuple[bool, str],
) -> None:
    """Parametrized test for two-tier MIME detection."""
    assert is_image_attachment(media_type, filename) == expected
