"""Deterministic routing hint between Quick Search and Deep Investigation.
The user always chooses; this only suggests."""

import re

_DEEP = re.compile(
    r"\b(why|alternatives?|considered|changed?|changes|over the last|over time|history|"
    r"inconsisten\w*|contradict\w*|compare|trace|rationale|who approved|what if|lost if|leaves?)\b",
    re.IGNORECASE,
)


def suggest_mode(question: str) -> str:
    return "deep" if _DEEP.search(question or "") else "quick"
