"""Text normalization and tokenization for doctor notes."""

from __future__ import annotations

import re

PUNCTUATION_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")


def tokenize(text: str) -> list[str]:
    """Normalize text and return non-empty tokens."""
    lowered = text.lower()
    no_punctuation = PUNCTUATION_RE.sub(" ", lowered)
    normalized = WHITESPACE_RE.sub(" ", no_punctuation).strip()
    if not normalized:
        return []

    tokens = [token for token in normalized.split(" ") if token]
    return [token for token in tokens if any(char.isalpha() for char in token)]
