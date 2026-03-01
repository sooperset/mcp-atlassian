"""Tests for the shared MIME detection and attachment download utilities."""

import base64

import pytest

from mcp_atlassian.utils.media import (
    ATTACHMENT_MAX_BYTES,
    fetch_and_encode_attachment,
    is_image_attachment,
)


def test_attachment_max_bytes_type() -> None:
    """ATTACHMENT_MAX_BYTES must be an integer."""
    assert isinstance(ATTACHMENT_MAX_BYTES, int)


def test_attachment_max_bytes_value() -> None:
    """ATTACHMENT_MAX_BYTES must equal 50 MB (50 * 1024 * 1024)."""
    assert ATTACHMENT_MAX_BYTES == 50 * 1024 * 1024


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
        # None MIME + image extension -> detected as image
        (None, "photo.png", (True, "image/png")),
        # None MIME + non-image extension -> not an image
        (None, "doc.pdf", (False, "application/octet-stream")),
        # Both None -> not an image
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


# -- fetch_and_encode_attachment tests --------------------------------


class TestFetchAndEncodeAttachment:
    """Tests for fetch_and_encode_attachment helper."""

    def test_success(self) -> None:
        """Successful fetch returns (base64_data, mime, size)."""
        raw = b"fake-png-bytes"

        def fetch_fn(url: str) -> bytes | None:
            return raw

        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=fetch_fn,
            url="https://example.com/img.png",
            filename="img.png",
        )
        assert encoded == base64.b64encode(raw).decode("ascii")
        assert mime == "image/png"
        assert size == len(raw)

    def test_explicit_mime_type(self) -> None:
        """Explicit mime_type overrides filename detection."""
        raw = b"data"

        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=lambda _url: raw,
            url="https://example.com/file.bin",
            filename="file.bin",
            mime_type="image/webp",
        )
        assert encoded is not None
        assert mime == "image/webp"
        assert size == len(raw)

    def test_fetched_size_exceeds_limit(self) -> None:
        """Return (None, None, actual_size) when oversized."""
        big_data = b"x" * (ATTACHMENT_MAX_BYTES + 1)

        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=lambda _url: big_data,
            url="https://example.com/big.png",
            filename="big.png",
        )
        assert encoded is None
        assert mime is None
        assert size == len(big_data)

    def test_custom_max_bytes(self) -> None:
        """Custom max_bytes is respected."""
        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=lambda _url: b"x" * 200,
            url="https://example.com/img.png",
            filename="img.png",
            max_bytes=100,
        )
        assert encoded is None
        assert mime is None
        assert size == 200

    def test_fetch_returns_none(self) -> None:
        """Return (None, None, 0) when fetch_fn returns None."""
        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=lambda _url: None,
            url="https://example.com/img.png",
            filename="img.png",
        )
        assert encoded is None
        assert mime is None
        assert size == 0

    def test_fetch_raises_exception(self) -> None:
        """Return (None, None, 0) when fetch_fn raises."""

        def boom(_url: str) -> bytes | None:
            raise ConnectionError("network down")

        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=boom,
            url="https://example.com/img.png",
            filename="img.png",
        )
        assert encoded is None
        assert mime is None
        assert size == 0

    @pytest.mark.parametrize(
        ("filename", "expected_mime"),
        [
            ("photo.png", "image/png"),
            ("photo.jpg", "image/jpeg"),
            ("photo.jpeg", "image/jpeg"),
            ("photo.gif", "image/gif"),
            ("doc.pdf", "application/pdf"),
            ("archive.zip", "application/zip"),
            ("unknown", "application/octet-stream"),
        ],
        ids=[
            "png",
            "jpg",
            "jpeg",
            "gif",
            "pdf",
            "zip",
            "no-extension",
        ],
    )
    def test_mime_type_detection(
        self,
        filename: str,
        expected_mime: str,
    ) -> None:
        """MIME type is guessed from filename when not provided."""
        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=lambda _url: b"data",
            url="https://example.com/file",
            filename=filename,
        )
        assert encoded is not None
        assert mime == expected_mime
        assert size == 4

    def test_fetched_size_at_limit_passes(self) -> None:
        """Fetched size exactly at the limit is allowed."""
        raw = b"x" * 100

        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=lambda _url: raw,
            url="https://example.com/img.png",
            filename="img.png",
            max_bytes=100,
        )
        assert encoded is not None
        assert size == 100

    def test_oversized_returns_actual_size(self) -> None:
        """Oversized failure returns actual byte count for error."""
        oversized = b"x" * 150

        encoded, mime, size = fetch_and_encode_attachment(
            fetch_fn=lambda _url: oversized,
            url="https://example.com/img.png",
            filename="img.png",
            max_bytes=100,
        )
        assert encoded is None
        assert mime is None
        assert size == 150
