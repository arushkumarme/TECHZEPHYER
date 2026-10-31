"""Loader for the telemetry field dictionary (``config/telemetry_fields.toml``)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from netcoop.scenarios.generator import REPO_ROOT

DEFAULT_FIELDS_PATH = REPO_ROOT / "config" / "telemetry_fields.toml"


class FieldSpec(BaseModel):
    """One generator field, as observed in the organizer's code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location: Literal["record", "metrics"]
    category: str
    type: Literal["string", "enum", "number", "integer"]
    unit: str
    source: str = Field(min_length=1)
    unit_basis: str | None = None
    format: str | None = None
    allowed_values: list[str] | None = None
    plausible_min: float | None = None
    plausible_max: float | None = None
    plausible_basis: str | None = None
    observed_ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)


class FieldDictionary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_: str = Field(alias="schema")
    generator_sha256: str
    fields: dict[str, FieldSpec]

    @property
    def metric_names(self) -> list[str]:
        """Names of the fields found inside a record's ``metrics`` object."""
        return [n for n, s in self.fields.items() if s.location == "metrics"]


def load_field_dictionary(path: Path = DEFAULT_FIELDS_PATH) -> FieldDictionary:
    with path.open("rb") as fh:
        return FieldDictionary.model_validate(tomllib.load(fh))
