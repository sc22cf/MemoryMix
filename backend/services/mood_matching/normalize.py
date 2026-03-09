"""
normalize.py — Shared string normalisation used across all matching modules.
"""

from __future__ import annotations

import re
import unicodedata


_FEAT_RE = re.compile(
    r"\s*[\(\[\-–—]?\s*"
    r"(?:feat\.?|ft\.?|featuring|with|prod\.?|produced by)"
    r"\s.*",
    re.IGNORECASE,
)

_REMASTER_RE = re.compile(
    r"\s*[\(\[\-–—]\s*"
    r"(?:remaster(?:ed)?|deluxe|bonus|anniversary|edition|mix|version|mono|stereo|live|radio edit|single)"
    r"[^)\]]*[\)\]]?",
    re.IGNORECASE,
)

_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(s: str) -> str:
    """Aggressive normalisation for matching: lowercase, strip accents,
    remove feat/remaster suffixes, remove punctuation, collapse whitespace."""
    if not s:
        return ""
    # Unicode normalisation (NFD → strip combining marks)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().strip()
    # Strip "feat." / "ft." and everything after
    s = _FEAT_RE.sub("", s)
    # Strip "(Remastered 2009)" etc.
    s = _REMASTER_RE.sub("", s)
    # Remove punctuation
    s = _PUNCTUATION_RE.sub(" ", s)
    # Collapse whitespace
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s
