"""Synthetic organizational corpus for evaluation and demos. No real data."""

from pathlib import Path

ROOT = Path(__file__).parent


def documents() -> dict[str, bytes]:
    """{source_id: markdown bytes} for every synthetic document."""
    out = {}
    for path in sorted(ROOT.glob("*.md")):
        out[f"gdrive:{path.stem}"] = path.read_bytes()
    return out
