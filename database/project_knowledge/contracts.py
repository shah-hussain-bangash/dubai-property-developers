"""Source-inventory metadata contracts; these contain no file contents."""

from typing import TypedDict


class SourceFingerprint(TypedDict):
    source_path: str
    sha256: str
    size_bytes: int


class InventoryFile(SourceFingerprint):
    extension: str


class DiscoveredFile(TypedDict):
    source_path: str
    category: str
    size_bytes: int


class CandidateReview(TypedDict):
    source_path: str
    review_status: str
    validation_status: str
    original_size_bytes: str
    current_size_bytes: str | int
    sha256: str
    security_flags: str
