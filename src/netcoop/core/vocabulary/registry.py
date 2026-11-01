"""Controlled-vocabulary registry (protocol upgrade, Prompt 1).

Every vocabulary is one TOML file in ``config/vocabulary/`` holding, for each term, a
definition, status (active / deprecated / blocked), source and attributes. Where the code
already enforces a term set (a ``Literal`` or a set constant), the file names it in
``code_literal`` and a test keeps the two identical - so the metadata is the single
source of truth without rewriting the code's types.

Rules:
* closed vocabulary - unknown ids are rejected, with closest-match suggestions;
* extensible vocabulary - only ``x-``-prefixed ids are accepted beyond the listed terms,
  and they are flagged as unrecognised;
* ``blocked`` terms (e.g. ``calibrated``, ``deployment``) are always rejected.
"""

from __future__ import annotations

import difflib
import importlib
import tomllib
import typing
from functools import cache, partial
from pathlib import Path
from typing import Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from netcoop.config.settings import CONFIG_DIR

VOCABULARY_DIR = CONFIG_DIR / "vocabulary"
EXTENSION_PREFIX = "x-"

Status = Literal["active", "deprecated", "blocked"]
IdStyle = Literal["snake", "upper", "free"]


class UnknownTermError(ValueError):
    def __init__(self, vocabulary: str, term: str, suggestions: list[str]) -> None:
        hint = f"; did you mean {', '.join(repr(s) for s in suggestions)}?" if suggestions else ""
        super().__init__(f"{term!r} is not a term of vocabulary {vocabulary!r}{hint}")
        self.vocabulary = vocabulary
        self.term = term
        self.suggestions = suggestions


class BlockedTermError(ValueError):
    def __init__(self, vocabulary: str, term: str, reason: str) -> None:
        super().__init__(f"{term!r} in vocabulary {vocabulary!r} is blocked: {reason}")
        self.vocabulary = vocabulary
        self.term = term


class Term(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    definition: str = Field(min_length=1)
    status: Status
    source: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)
    #: True only for accepted ``x-`` extension ids of an extensible vocabulary.
    unrecognised: bool = False


class Vocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: str
    extensible: bool
    id_style: IdStyle
    description: str
    code_literal: str | None = None
    terms: list[Term]

    def term(self, term_id: str) -> Term:
        for t in self.terms:
            if t.id == term_id:
                return t
        raise UnknownTermError(self.name, term_id, self.suggest(term_id))

    def suggest(self, term_id: str) -> list[str]:
        candidates = [t.id for t in self.terms if t.status != "blocked"]
        return difflib.get_close_matches(term_id, candidates, n=3, cutoff=0.6)

    def code_values(self) -> list[str]:
        """The term set the code enforces (resolved from ``code_literal``)."""
        if not self.code_literal:
            return []
        module_name, _, attr = self.code_literal.partition(":")
        obj: Any = importlib.import_module(module_name)
        cls_name, _, field = attr.partition(".")
        obj = getattr(obj, cls_name)
        if field:  # pydantic model field annotated with a Literal
            obj = obj.model_fields[field].annotation
        if isinstance(obj, set | frozenset | tuple | list):
            return sorted(str(v) for v in obj)
        return [str(v) for v in typing.get_args(obj)]


@cache
def all_vocabularies(directory: Path = VOCABULARY_DIR) -> dict[str, Vocabulary]:
    out: dict[str, Vocabulary] = {}
    for path in sorted(directory.glob("*.toml")):
        with path.open("rb") as fh:
            v = Vocabulary.model_validate(tomllib.load(fh))
        if v.name != path.stem:
            raise ValueError(f"{path.name} declares name {v.name!r}")
        out[v.name] = v
    return out


def get_vocabulary(name: str) -> Vocabulary:
    vocabs = all_vocabularies()
    if name not in vocabs:
        raise KeyError(f"unknown vocabulary {name!r}; known: {sorted(vocabs)}")
    return vocabs[name]


def require(name: str, term_id: str) -> Term:
    """Return the term, or raise UnknownTermError / BlockedTermError."""
    v = get_vocabulary(name)
    for t in v.terms:
        if t.id == term_id:
            if t.status == "blocked":
                raise BlockedTermError(name, term_id, t.definition)
            return t
    if v.extensible and term_id.startswith(EXTENSION_PREFIX) and len(term_id) > 2:
        return Term(
            id=term_id,
            label=term_id,
            definition="Unrecognised extension term (the vocabulary is extensible).",
            status="active",
            source="extension",
            unrecognised=True,
        )
    raise UnknownTermError(name, term_id, v.suggest(term_id))


def is_valid(name: str, term_id: str) -> bool:
    try:
        require(name, term_id)
    except (UnknownTermError, BlockedTermError):
        return False
    return True


def _check_term(name: str, value: str) -> str:
    require(name, value)  # raises a ValueError subclass -> pydantic ValidationError
    return value


class VocabTerm(AfterValidator):
    """Pydantic marker: ``Annotated[str, VocabTerm("cause_type")]`` accepts only terms of
    that vocabulary (blocked terms rejected, suggestions in the error message)."""

    def __init__(self, vocabulary: str) -> None:
        get_vocabulary(vocabulary)  # fail fast on a typo in the vocabulary name
        super().__init__(func=partial(_check_term, vocabulary))
