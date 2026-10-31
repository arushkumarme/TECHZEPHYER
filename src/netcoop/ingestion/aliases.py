"""Alias map and unit rules (``config/aliases.toml``) — team-authored, cited (doc 05 §6.4)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from netcoop.config.settings import CONFIG_DIR

DEFAULT_ALIASES_PATH = CONFIG_DIR / "aliases.toml"


class MetricAlias(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    canonical: str
    unit: str | None = None


class AliasConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance: str = Field(min_length=1)
    record_aliases: dict[str, str] = Field(default_factory=dict)
    metric_aliases: dict[str, MetricAlias] = Field(default_factory=dict)
    units: dict[str, tuple[str, float]] = Field(default_factory=dict)

    def unit(self, name: str | None) -> tuple[str, float] | None:
        """(dimension, factor-to-canonical) for a unit spelling, or None if unknown."""
        if name is None:
            return None
        return self.units.get(name) or self.units.get(name.lower())


def load_aliases(path: Path = DEFAULT_ALIASES_PATH) -> AliasConfig:
    with path.open("rb") as fh:
        return AliasConfig.model_validate(tomllib.load(fh))
