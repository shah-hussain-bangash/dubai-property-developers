"""Embedding provider contract + an offline hashing embedder.

``HashingEmbeddingProvider`` is a deterministic bag-of-words feature hasher. It
gives *lexical* similarity only (no semantics) and exists so the RAG pipeline is
testable offline. Replace with a real embedding model for production quality.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9؀-ۿ]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "do",
        "does",
        "can",
        "i",
        "you",
        "your",
        "we",
        "our",
    ]
)


class EmbeddingProvider(Protocol):
    name: str
    dimension: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


def tokenize_unicode(text: str) -> list[str]:
    """Whole Unicode words for supplied sources; legacy hashing tokens stay stable."""
    normalized = unicodedata.normalize("NFC", text.casefold())
    characters: list[str] = []
    in_word = False
    for char in normalized:
        category = unicodedata.category(char)[0]
        if category in {"L", "N"} or (category == "M" and in_word):
            characters.append(char)
            in_word = True
        else:
            characters.append(" ")
            in_word = False
    return [token for token in "".join(characters).split() if token not in _STOPWORDS]


class HashingEmbeddingProvider:
    def __init__(self, dimension: int = 1536) -> None:
        self.dimension = dimension
        self.name = f"hashing-bow-{dimension}"

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    """Compare finite vectors without squaring their original magnitudes."""
    if len(a) != len(b):
        raise ValueError("vectors must have the same dimension")
    if any(not math.isfinite(value) for vector in (a, b) for value in vector):
        raise ValueError("vector coordinates must be finite")
    scale_a = max((abs(value) for value in a), default=0.0)
    scale_b = max((abs(value) for value in b), default=0.0)
    if not scale_a or not scale_b:
        return 0.0
    scaled_a = [value / scale_a for value in a]
    scaled_b = [value / scale_b for value in b]
    dot = math.fsum(x * y for x, y in zip(scaled_a, scaled_b, strict=True))
    norm_a = math.sqrt(math.fsum(value * value for value in scaled_a))
    norm_b = math.sqrt(math.fsum(value * value for value in scaled_b))
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))
