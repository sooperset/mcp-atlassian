"""Shared media type detection and attachment download utilities."""

import base64
import logging
import mimetypes
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Maximum attachment size for inline download (50 MB).
# Used by both Jira and Confluence server tools to gate in-memory transfers.
ATTACHMENT_MAX_BYTES: int = 50 * 1024 * 1024

# Total attachment bytes one tool call may hold in memory across all the
# attachments it returns inline (see AttachmentBudget).
ATTACHMENT_CALL_MAX_BYTES: int = ATTACHMENT_MAX_BYTES

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

# MIME types that carry no reliable information about the actual file type,
# so detection falls back to the filename extension. "multipart/form-data" is
# what Jira Service Management reports for attachments uploaded through the
# customer portal, which is the usual source of screenshots on support tickets.
_AMBIGUOUS_MIME_TYPES = frozenset(
    {
        "application/octet-stream",
        "application/binary",
        "multipart/form-data",
    }
)

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


class AttachmentTooLargeError(Exception):
    """A streamed attachment body passed the size limit before it ended."""

    def __init__(self, bytes_read: int, max_bytes: int) -> None:
        super().__init__(
            f"Attachment body passed the {max_bytes} byte limit "
            f"after {bytes_read} bytes; stopped reading"
        )
        self.bytes_read = bytes_read
        self.max_bytes = max_bytes


class AttachmentBudget:
    """The attachment bytes one tool call may still hold in memory.

    A tool that returns several attachments inline creates one budget, checks
    each attachment with :meth:`refusal` before and after fetching it, and
    :meth:`spend` s the bytes it keeps. Attachments past the budget are
    reported instead of fetched, so one call holds at most
    ``ATTACHMENT_CALL_MAX_BYTES`` however many attachments there are.
    """

    def __init__(self) -> None:
        self.total = ATTACHMENT_CALL_MAX_BYTES
        self.remaining = self.total

    def refusal(self, size: int | None) -> str | None:
        """Return why *size* bytes cannot be kept, or None if they can."""
        if size is None or size <= self.remaining:
            return None
        limit = f"the {self.total // (1024 * 1024)} MB inline limit"
        if self.remaining < self.total:
            limit = f"the {self.remaining} bytes left of {limit} for one call"
        return f"{size} bytes which exceeds {limit}."

    def spend(self, size: int) -> None:
        """Record that *size* bytes are kept."""
        self.remaining -= size


def read_capped(response: Any, max_bytes: int) -> bytes:
    """Read a streamed response body, giving up once it passes ``max_bytes``.

    Attachment metadata is checked before a download, but the body can be
    larger than the metadata says. Stopping here bounds memory use by the
    limit instead of by what the upstream sends.

    Raises:
        AttachmentTooLargeError: The body is larger than ``max_bytes``.
    """
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        total += len(chunk)
        if total > max_bytes:
            raise AttachmentTooLargeError(total, max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


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

        * ``fetched_bytes == 0`` -- fetch returned ``None`` or raised
          an exception other than ``AttachmentTooLargeError``.
        * ``fetched_bytes > 0``  -- the attachment is too large: the
          whole body was received and is larger than *max_bytes*, or
          ``fetch_fn`` stopped at its own limit and raised
          ``AttachmentTooLargeError``. The value is the number of
          bytes received.
    """
    try:
        data_bytes = fetch_fn(url)
    except AttachmentTooLargeError as exc:
        logger.warning(
            "Attachment '%s' passed the %d byte limit while downloading",
            filename,
            exc.max_bytes,
        )
        return None, None, exc.bytes_read
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
