from dataclasses import dataclass
from typing import Dict


@dataclass
class Document:
    """Class to represent a document with content and metadata."""

    page_content: str
    metadata: Dict[str, any]
