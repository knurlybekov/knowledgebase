"""Provider client protocol consumed by the sync engine."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from knowledge.api import DownloadResult, SourceDocument

MAX_DOWNLOAD_RETRIES = 3


@dataclass(frozen=True)
class Item:
    kind: str  # upsert | remove | drive_removed
    source_id: str
    document: SourceDocument | None = None
    drive_id: str = ""


@dataclass(frozen=True)
class Page:
    items: list[Item]
    observed_at: datetime
    next_cursor: str | None = None  # more pages in this listing
    done_cursor: str | None = None  # listing complete; store this cursor
    extra: dict = field(default_factory=dict)


class ProviderClient(Protocol):
    def bootstrap_cursor(self, scope) -> str | None: ...

    def list_all(self, scope) -> Iterator[Page]: ...

    def list_changes(self, scope, cursor: str) -> Iterator[Page]: ...

    def fetch(self, sd: SourceDocument) -> DownloadResult: ...
