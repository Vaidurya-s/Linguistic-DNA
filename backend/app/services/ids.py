"""Deterministic internal IDs, so a repeat import of the same input yields the same IDs."""

import base64
import hashlib


def stable_id(prefix: str, *parts: str, length: int = 16) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).digest()
    return prefix + base64.b32encode(digest).decode("ascii").lower()[:length]


def lexeme_id(dataset: str, record_id: str) -> str:
    return stable_id("lx_", dataset, record_id)


def relationship_id(dataset: str, *parts: str) -> str:
    return stable_id("rel_", dataset, *parts)
