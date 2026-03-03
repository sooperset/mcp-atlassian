"""Shared media type detection and attachment download utilities."""

import base64
import logging
import mimetypes
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
