"""Source-independent representations exchanged between connectors and the
pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SourceDocument:
    """Normalized metadata of one item as the connector saw it."""

    source_type: str
    source_id: str  # canonical: gdrive:<fileId> | sp:<driveId>:<itemId>
    version_label: str
    title: str = ""
    mime_type: str = ""
    source_url: str = ""
    path: str = ""
    drive_id: str = ""
    site_id: str = ""
    author: str = ""
    created_at: datetime | None = None
    modified_at: datetime | None = None
    size: int | None = None
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeEvent:
    kind: str  # upsert | remove
    source_id: str
    seq: int
    observed_at: datetime
    reconcile_generation: int | None = None
    document: SourceDocument | None = None


@dataclass(frozen=True)
class DownloadResult:
    """Bytes whose revision the connector validated before and after download."""

    content: bytes
    version_label: str
    mime_type: str
    filename: str = ""


class RevisionDrift(Exception):
    """The item changed between metadata and download more times than allowed."""


class UnsupportedFormat(Exception):
    """No parser handles this file type; the document is quarantined."""


@dataclass(frozen=True)
class Section:
    heading_path: tuple[str, ...]
    text: str
    locator: dict  # page | slide | sheet | table


@dataclass(frozen=True)
class ParsedDocument:
    sections: list[Section]
    parser: str

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)


@dataclass(frozen=True)
class ChunkDraft:
    position: int
    text: str
    heading_path: list[str]
    locator: dict
    content_hash: str
