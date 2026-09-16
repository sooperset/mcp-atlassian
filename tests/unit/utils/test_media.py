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
        # JSM customer-portal uploads report multipart/form-data
        (
            "multipart/form-data",
            "WhatsApp Image 2026-08-15 at 23.28.03.jpeg",
            (True, "image/jpeg"),
        ),
        (
            "multipart/form-data",
            "screenshot.png",
            (True, "image/png"),
        ),
        (
            "multipart/form-data",
            "report.pdf",
            (False, "multipart/form-data"),
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
        "jsm-portal-jpeg-ext",
        "jsm-portal-png-ext",
        "jsm-portal-pdf-ext",
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


class TestGetImageDimensions:
    """Tests for the stdlib image-header dimension parser."""

    @staticmethod
    def _png(width: int, height: int) -> bytes:
        return (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", width, height)
            + b"\x08\x06\x00\x00\x00"
        )

    @staticmethod
    def _gif(width: int, height: int) -> bytes:
        return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00" * 20

    @staticmethod
    def _bmp(width: int, height: int) -> bytes:
        return b"BM" + b"\x00" * 16 + struct.pack("<ii", width, height) + b"\x00" * 10

    @staticmethod
    def _jpeg(width: int, height: int) -> bytes:
        # SOI, a skippable APP0 segment, then SOF0 carrying the frame size.
        app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
        sof0 = (
            b"\xff\xc0"
            + struct.pack(">H", 17)
            + b"\x08"
            + struct.pack(">HH", height, width)
            + b"\x03"
            + b"\x00" * 9
        )
        return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"

    def test_png(self) -> None:
        assert get_image_dimensions(self._png(1280, 720)) == (1280, 720)

    def test_gif(self) -> None:
        assert get_image_dimensions(self._gif(64, 48)) == (64, 48)

    def test_bmp_bottom_up(self) -> None:
        assert get_image_dimensions(self._bmp(100, 200)) == (100, 200)

    def test_bmp_top_down_height_is_negative(self) -> None:
        """A top-down BMP stores a negative height; the magnitude is returned."""
        assert get_image_dimensions(self._bmp(100, -200)) == (100, 200)

    def test_jpeg(self) -> None:
        assert get_image_dimensions(self._jpeg(800, 600)) == (800, 600)

    def test_jpeg_with_fill_bytes_before_the_frame_header(self) -> None:
        """Encoders may pad with extra 0xFF bytes ahead of a marker id."""
        data = self._jpeg(800, 600)
        padded = data[:20] + b"\xff\xff" + data[20:]
        assert get_image_dimensions(padded) == (800, 600)

    def test_bmp_with_a_core_header(self) -> None:
        """The legacy BITMAPCOREHEADER stores 16-bit dimensions."""
        data = (
            b"BM"
            + b"\x00" * 12
            + struct.pack("<I", 12)
            + struct.pack("<hh", 120, 90)
            + b"\x00" * 10
        )
        assert get_image_dimensions(data) == (120, 90)

    def test_webp_lossy(self) -> None:
        data = (
            b"RIFF"
            + struct.pack("<I", 30)
            + b"WEBPVP8 "
            + b"\x00" * 10
            + struct.pack("<HH", 320, 240)
            + b"\x00" * 4
        )
        assert get_image_dimensions(data) == (320, 240)

    def test_webp_lossless(self) -> None:
        bits = (640 - 1) | ((480 - 1) << 14)
        data = (
            b"RIFF"
            + struct.pack("<I", 25)
            + b"WEBPVP8L"
            + b"\x00" * 5
            + struct.pack("<I", bits)
            + b"\x00" * 4
        )
        assert get_image_dimensions(data) == (640, 480)

    def test_webp_extended(self) -> None:
        data = (
            b"RIFF"
            + struct.pack("<I", 30)
            + b"WEBPVP8X"
            + b"\x00" * 8
            + (1023).to_bytes(3, "little")
            + (767).to_bytes(3, "little")
            + b"\x00" * 4
        )
        assert get_image_dimensions(data) == (1024, 768)

    def test_empty_input(self) -> None:
        assert get_image_dimensions(b"") is None

    def test_too_short_to_parse(self) -> None:
        assert get_image_dimensions(b"\x89PNG\r\n\x1a\n") is None

    def test_unrecognised_format(self) -> None:
        assert get_image_dimensions(b"%PDF-1.7" + b"\x00" * 40) is None

    def test_truncated_png_header(self) -> None:
        """A PNG signature with a truncated IHDR must not raise."""
        assert get_image_dimensions(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16) == (0, 0)

    def test_jpeg_without_sof_marker(self) -> None:
        """A JPEG carrying no frame header resolves to None, not an exception."""
        data = b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"\x00\x00\xff\xd9"
        assert get_image_dimensions(data) is None
