"""Shared media type detection and attachment download utilities."""

import base64
import logging
import mimetypes
import struct
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Maximum attachment size for inline download (50 MB).
# Used by both Jira and Confluence server tools to gate in-memory transfers.
ATTACHMENT_MAX_BYTES: int = 50 * 1024 * 1024

_IMAGE_MIME_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "image/bmp",
    }
)

_AMBIGUOUS_MIME_TYPES = frozenset({"application/octet-stream", "application/binary"})

_IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
)


def is_image_attachment(
    media_type: str | None, filename: str | None
) -> tuple[bool, str]:
    """Detect whether an attachment is an image.

    Uses two-tier detection: explicit MIME type check, then filename
    extension fallback for ambiguous or missing MIME types.

    Args:
        media_type: The MIME type reported by the API.
        filename: The attachment filename.

    Returns:
        Tuple of (is_image, resolved_mime_type).
    """
    if media_type and media_type in _IMAGE_MIME_TYPES:
        return True, media_type

    if (media_type in _AMBIGUOUS_MIME_TYPES or media_type is None) and filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in _IMAGE_EXTENSIONS:
            guessed = mimetypes.guess_type(filename)[0] or "image/png"
            return True, guessed

    return False, media_type or "application/octet-stream"


def get_image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Read the pixel dimensions of an image from its header bytes.

    Pure-stdlib header parsing (no Pillow dependency) for the formats Jira
    renders inline: PNG, GIF, JPEG, BMP, and WebP. Jira Cloud requires
    ``width``/``height`` on inline ``mediaSingle`` nodes for the image to
    render, so these are derived from the raw bytes before upload.

    Args:
        data: The raw image bytes.

    Returns:
        A ``(width, height)`` tuple in pixels, or ``None`` if the format is
        unrecognised or the header is too short/corrupt to parse.
    """
    if not data or len(data) < 24:
        return None

    try:
        # --- PNG: 8-byte signature, then IHDR with width/height as BE uint32.
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack(">II", data[16:24])
            return int(width), int(height)

        # --- GIF: 'GIF87a'/'GIF89a', logical screen size as LE uint16.
        if data[:6] in (b"GIF87a", b"GIF89a"):
            width, height = struct.unpack("<HH", data[6:10])
            return int(width), int(height)

        # --- BMP: 'BM', BITMAPINFOHEADER width/height as LE int32.
        if data[:2] == b"BM":
            width, height = struct.unpack("<ii", data[18:26])
            return int(width), abs(int(height))

        # --- WebP: 'RIFF'....'WEBP' followed by a VP8/VP8L/VP8X chunk.
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            chunk = data[12:16]
            if chunk == b"VP8 " and len(data) >= 30:
                width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
                return int(width), int(height)
            if chunk == b"VP8L" and len(data) >= 25:
                bits = struct.unpack("<I", data[21:25])[0]
                width = (bits & 0x3FFF) + 1
                height = ((bits >> 14) & 0x3FFF) + 1
                return int(width), int(height)
            if chunk == b"VP8X" and len(data) >= 30:
                width = int.from_bytes(data[24:27], "little") + 1
                height = int.from_bytes(data[27:30], "little") + 1
                return int(width), int(height)

        # --- JPEG: scan for a Start-Of-Frame (SOFn) marker.
        if data[:2] == b"\xff\xd8":
            return _jpeg_dimensions(data)
    except (struct.error, IndexError, ValueError):
        return None

    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """Extract dimensions from a JPEG by walking its marker segments."""
    # SOF markers carry the frame size. Skip the standalone/irrelevant ones.
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    pos = 2
    size = len(data)
    while pos + 1 < size:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        pos += 2
        # Padding bytes / markers without a length payload.
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if pos + 2 > size:
            break
        seg_len = struct.unpack(">H", data[pos : pos + 2])[0]
        if marker in sof_markers:
            if pos + 7 > size:
                break
            height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
            return int(width), int(height)
        pos += seg_len
    return None


def fetch_and_encode_attachment(
    fetch_fn: Callable[[str], bytes | None],
    url: str,
    filename: str,
    mime_type: str | None = None,
    max_bytes: int = ATTACHMENT_MAX_BYTES,
) -> tuple[str | None, str | None, int]:
    """Fetch and base64-encode an attachment.

    Handles size-limit checks, fetching, encoding, and MIME type
    resolution in one place.

    Args:
        fetch_fn: Callable that takes a URL and returns raw bytes,
            or None on failure.
        url: The URL to fetch the attachment from.
        filename: The filename for MIME type detection fallback.
        mime_type: Explicit MIME type. When None the type is guessed
            from *filename* with ``application/octet-stream`` as the
            fallback.
        max_bytes: Maximum allowed file size in bytes.

    Returns:
        A 3-tuple ``(base64_data, resolved_mime_type, fetched_bytes)``.

        On success all three fields are populated.  On failure the
        first two are ``None`` and *fetched_bytes* distinguishes
        the failure mode:

        * ``fetched_bytes == 0`` -- fetch returned ``None`` or
          raised an exception.
        * ``fetched_bytes > 0``  -- downloaded data exceeded
          *max_bytes* (the actual size is returned so callers can
          report it).
    """
    try:
        data_bytes = fetch_fn(url)
    except Exception:
        logger.warning(
            "Failed to fetch attachment '%s' from %s",
            filename,
            url,
            exc_info=True,
        )
        return None, None, 0

    if data_bytes is None:
        logger.warning(
            "Fetch returned None for attachment '%s'",
            filename,
        )
        return None, None, 0

    actual_size = len(data_bytes)

    if actual_size > max_bytes:
        logger.warning(
            "Attachment '%s' fetched size %d exceeds limit %d",
            filename,
            actual_size,
            max_bytes,
        )
        return None, None, actual_size

    encoded = base64.b64encode(data_bytes).decode("ascii")

    if mime_type is None:
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    return encoded, mime_type, actual_size
