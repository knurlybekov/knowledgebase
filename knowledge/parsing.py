"""Document parsers. Each returns sections with heading paths and locators so
a chunk traces back to a page, slide, sheet or heading."""

from __future__ import annotations

import io
import re

from .types import ParsedDocument, Section, UnsupportedFormat

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
TEXT_TYPES = {"text/plain", "text/markdown", "text/csv", "text/x-markdown"}
MAX_SHEET_ROWS = 2000
MAX_TEXT_BYTES = 20 * 1024 * 1024

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def parse(content: bytes, mime_type: str, filename: str = "") -> ParsedDocument:
    mime = (mime_type or "").split(";")[0].strip().lower()
    name = (filename or "").lower()
    if mime == DOCX or name.endswith(".docx"):
        return _parse_docx(content)
    if mime == PPTX or name.endswith(".pptx"):
        return _parse_pptx(content)
    if mime == XLSX or name.endswith(".xlsx"):
        return _parse_xlsx(content)
    if mime == PDF or name.endswith(".pdf"):
        return _parse_pdf(content)
    if (
        mime in TEXT_TYPES
        or mime.startswith("text/")
        or name.endswith((".md", ".txt", ".markdown"))
    ):
        return _parse_text(content)
    raise UnsupportedFormat(mime or name or "unknown")


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _parse_text(content: bytes) -> ParsedDocument:
    if len(content) > MAX_TEXT_BYTES:
        raise UnsupportedFormat("text file too large")
    text = content.decode("utf-8", errors="replace")
    sections: list[Section] = []
    heading_path: list[str] = []
    buffer: list[str] = []

    def flush():
        body = _clean("\n".join(buffer))
        if body:
            sections.append(Section(tuple(heading_path), body, {}))
        buffer.clear()

    for line in text.splitlines():
        m = _MD_HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            heading_path = [*heading_path[:level - 1], m.group(2).strip()]
            continue
        buffer.append(line)
    flush()
    if not sections and text.strip():
        sections.append(Section((), _clean(text), {}))
    return ParsedDocument(sections, "text")


def _parse_docx(content: bytes) -> ParsedDocument:
    import docx

    document = docx.Document(io.BytesIO(content))
    sections: list[Section] = []
    heading_path: list[str] = []
    buffer: list[str] = []

    def flush():
        body = _clean("\n".join(buffer))
        if body:
            sections.append(Section(tuple(heading_path), body, {}))
        buffer.clear()

    for paragraph in document.paragraphs:
        style = (paragraph.style.name or "") if paragraph.style is not None else ""
        text = paragraph.text.strip()
        if style.lower().startswith("heading") and text:
            flush()
            try:
                level = int(style.split()[-1])
            except ValueError:
                level = 1
            heading_path = [*heading_path[:level - 1], text]
            continue
        if text:
            buffer.append(text)
    flush()
    for index, table in enumerate(document.tables, start=1):
        rows = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            sections.append(Section(tuple(heading_path), "\n".join(rows), {"table": index}))
    return ParsedDocument(sections, "docx")


def _parse_pptx(content: bytes) -> ParsedDocument:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(content))
    sections: list[Section] = []
    for number, slide in enumerate(presentation.slides, start=1):
        title = ""
        parts: list[str] = []
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            if shape == getattr(slide.shapes, "title", None):
                title = text
            else:
                parts.append(text)
        body = _clean("\n".join(parts))
        if title or body:
            sections.append(Section((title,) if title else (), body or title, {"slide": number}))
    return ParsedDocument(sections, "pptx")


def _parse_xlsx(content: bytes) -> ParsedDocument:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sections: list[Section] = []
    for sheet in workbook.worksheets:
        rows = []
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= MAX_SHEET_ROWS:
                break
            cells = ["" if v is None else str(v) for v in row]
            if any(c.strip() for c in cells):
                rows.append(" | ".join(cells).rstrip(" |"))
        if rows:
            sections.append(Section((sheet.title,), "\n".join(rows), {"sheet": sheet.title}))
    return ParsedDocument(sections, "xlsx")


def _parse_pdf(content: bytes) -> ParsedDocument:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    sections: list[Section] = []
    for number, page in enumerate(reader.pages, start=1):
        text = _clean(page.extract_text() or "")
        if text:
            sections.append(Section((), text, {"page": number}))
    return ParsedDocument(sections, "pdf")
