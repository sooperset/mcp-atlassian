"""Tests for the shared MIME detection and attachment download utilities."""

import base64
import struct

import pytest

from mcp_atlassian.utils.media import (
    ATTACHMENT_MAX_BYTES,
    fetch_and_encode_attachment,
    get_image_dimensions,
    is_image_attachment,
)


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height)


def _gif(width: int, height: int) -> bytes:
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00" * 20


def _bmp(width: int, height: int) -> bytes:
    return b"BM" + b"\x00" * 16 + struct.pack("<ii", width, height)


def _jpeg(width: int, height: int) -> bytes:
    return (
        b"\xff\xd8\xff\xc0\x00\x11\x08"
        + struct.pack(">HH", height, width)
        + b"\x00" * 15
    )


def _webp_vp8x(width: int, height: int) -> bytes:
    return (
        b"RIFF\x00\x00\x00\x00WEBPVP8X"
        b"\x00\x00\x00\x0a"
        + b"\x00" * 4
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )


class TestGetImageDimensions:
    """Tests for stdlib image-dimension parsing."""

    @pytest.mark.parametrize(
        ("builder", "width", "height"),
        [
            (_png, 800, 600),
            (_gif, 16, 32),
            (_bmp, 120, 240),
            (_jpeg, 710, 163),
            (_webp_vp8x, 1024, 768),
        ],
        ids=["png", "gif", "bmp", "jpeg", "webp-vp8x"],
    )
    def test_known_formats(self, builder, width: int, height: int) -> None:
        assert get_image_dimensions(builder(width, height)) == (width, height)

    def test_bmp_negative_height_top_down(self) -> None:
        """BMP stores top-down rows as a negative height; abs() is returned."""
        assert get_image_dimensions(_bmp(120, -240)) == (120, 240)

    def test_empty_or_short_returns_none(self) -> None:
        assert get_image_dimensions(b"") is None
        assert get_image_dimensions(b"\x89PNG\r\n\x1a\n") is None

    def test_unknown_format_returns_none(self) -> None:
        assert get_image_dimensions(b"not an image at all, just text...") is None


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
