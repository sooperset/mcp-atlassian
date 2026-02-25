"""Shared media type detection utilities."""

import mimetypes

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
