from dataclasses import dataclass


@dataclass
class Document:
    """Class to represent a document with content and metadata."""

    page_content: str
    metadata: dict[str, any]
