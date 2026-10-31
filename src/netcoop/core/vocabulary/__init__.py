"""Controlled vocabulary registry: metadata (definition, status, source, attributes) over
the term sets the code enforces. See ``registry.py``."""

from netcoop.core.vocabulary.registry import (
    BlockedTermError,
    Term,
    UnknownTermError,
    VocabTerm,
    Vocabulary,
    all_vocabularies,
    get_vocabulary,
    is_valid,
    require,
)

__all__ = [
    "BlockedTermError",
    "Term",
    "UnknownTermError",
    "VocabTerm",
    "Vocabulary",
    "all_vocabularies",
    "get_vocabulary",
    "is_valid",
    "require",
]
