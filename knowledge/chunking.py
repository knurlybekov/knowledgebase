"""Heading-aware chunking with character offsets. About 800 tokens per chunk
(3,200 characters at 4 characters per token) with a 400-character overlap,
never across a section boundary."""

from __future__ import annotations

import hashlib
import re

from .types import ChunkDraft, ParsedDocument

TARGET_CHARS = 3200
OVERLAP_CHARS = 400
MIN_TAIL_CHARS = 200

_BREAKS = re.compile(r"(?<=[.!?])\s+|\n\n")


def _split_section(text: str) -> list[tuple[int, int]]:
    """Return (start, end) windows over `text`, cut at sentence or paragraph
    boundaries when one lies in the last quarter of the window."""
    spans: list[tuple[int, int]] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + TARGET_CHARS, n)
        if end < n:
            window = text[start:end]
            cut = None
            for m in _BREAKS.finditer(window):
                if m.end() >= TARGET_CHARS * 0.6:
                    cut = m.end()
            if cut:
                end = start + cut
        if n - end < MIN_TAIL_CHARS and end < n:
            end = n
        spans.append((start, end))
        if end >= n:
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return spans


def chunk_document(parsed: ParsedDocument) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    position = 0
    for section in parsed.sections:
        heading = list(section.heading_path)
        prefix = (" / ".join(heading) + "\n") if heading else ""
        for start, end in _split_section(section.text):
            body = section.text[start:end].strip()
            if not body:
                continue
            text = prefix + body
            drafts.append(
                ChunkDraft(
                    position=position,
                    text=text,
                    heading_path=heading,
                    locator={**section.locator, "start_char": start, "end_char": end},
                    content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                )
            )
            position += 1
    return drafts
