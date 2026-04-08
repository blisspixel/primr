"""Helper types used by resource handlers."""

from dataclasses import dataclass


@dataclass
class ReadResourceContents:
    content: str
    mime_type: str = "text/plain"
