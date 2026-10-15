import itertools

from knowledge.api import ParsedDocument, Section, chunk_document
from knowledge.chunking import OVERLAP_CHARS, TARGET_CHARS


def test_short_sections_become_one_chunk_each_with_heading_prefix():
    parsed = ParsedDocument(
        sections=[Section(("Policy", "Scope"), "Applies to all staff.", {"page": 2})],
        parser="text",
    )
    drafts = chunk_document(parsed)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.text.startswith("Policy / Scope\n")
    assert d.heading_path == ["Policy", "Scope"]
    assert d.locator == {"page": 2, "start_char": 0, "end_char": len("Applies to all staff.")}


def test_long_section_splits_with_overlap_and_consistent_offsets():
    sentence = "The committee reviewed the proposal in detail. "
    text = sentence * 200  # ~9,400 chars
    drafts = chunk_document(ParsedDocument([Section((), text, {})], "text"))
    assert len(drafts) >= 3
    assert [d.position for d in drafts] == list(range(len(drafts)))
    for a, b in itertools.pairwise(drafts):
        assert a.locator["end_char"] <= TARGET_CHARS + a.locator["start_char"]
        assert b.locator["start_char"] < a.locator["end_char"]  # overlap
        assert a.locator["end_char"] - b.locator["start_char"] <= OVERLAP_CHARS
        assert text[a.locator["start_char"] : a.locator["end_char"]].strip() == a.text
    assert drafts[-1].locator["end_char"] == len(text)
