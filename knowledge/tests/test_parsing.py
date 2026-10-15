import pytest

from knowledge.api import UnsupportedFormat, parse
from knowledge.parsing import DOCX, PDF, PPTX, XLSX

from .helpers import docx_bytes, pdf_bytes, pptx_bytes, xlsx_bytes


def test_markdown_headings_become_heading_paths():
    text = "# Policy\nIntro line.\n## Scope\nApplies to all staff.\n## Review\nEvery year."
    parsed = parse(text.encode(), "text/markdown", "policy.md")
    paths = [s.heading_path for s in parsed.sections]
    assert paths == [("Policy",), ("Policy", "Scope"), ("Policy", "Review")]
    assert parsed.sections[1].text == "Applies to all staff."


def test_docx_headings_paragraphs_and_tables():
    content = docx_bytes(
        [
            ("Heading 1", "Decision"),
            ("Normal", "We chose provider A."),
            ("Heading 2", "Alternatives"),
            ("Normal", "Provider B was considered."),
        ],
        table=[["Option", "Cost"], ["A", "10"], ["B", "12"]],
    )
    parsed = parse(content, DOCX, "decision.docx")
    assert parsed.parser == "docx"
    assert parsed.sections[0].heading_path == ("Decision",)
    assert "provider A" in parsed.sections[0].text
    assert parsed.sections[1].heading_path == ("Decision", "Alternatives")
    table = [s for s in parsed.sections if s.locator.get("table")]
    assert table and "A | 10" in table[0].text


def test_pptx_slides_carry_slide_numbers():
    parsed = parse(
        pptx_bytes([("Kickoff", "Agenda and goals"), ("Risks", "Budget overrun")]),
        PPTX,
        "deck.pptx",
    )
    assert [s.locator["slide"] for s in parsed.sections] == [1, 2]
    assert parsed.sections[1].heading_path == ("Risks",)
    assert "Budget overrun" in parsed.sections[1].text


def test_xlsx_sheets_carry_sheet_names():
    parsed = parse(
        xlsx_bytes({"Costs": [["Item", "Amount"], ["Hosting", 1200]], "Empty": [[None]]}),
        XLSX,
        "costs.xlsx",
    )
    assert len(parsed.sections) == 1
    assert parsed.sections[0].locator == {"sheet": "Costs"}
    assert "Hosting | 1200" in parsed.sections[0].text


def test_pdf_pages_carry_page_numbers():
    parsed = parse(pdf_bytes(["Page one text", "Page two text"]), PDF, "scan.pdf")
    assert [s.locator["page"] for s in parsed.sections] == [1, 2]
    assert "Page two" in parsed.sections[1].text


def test_unknown_type_is_unsupported():
    with pytest.raises(UnsupportedFormat):
        parse(b"\x00\x01", "application/octet-stream", "blob.bin")
