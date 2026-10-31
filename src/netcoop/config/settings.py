"""Runtime settings (``config/netcoop.toml``). Only simulation mode exists (doc 02 §5)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from netcoop.scenarios.generator import REPO_ROOT

CONFIG_DIR = REPO_ROOT / "config"
DEFAULT_SETTINGS_PATH = CONFIG_DIR / "netcoop.toml"


class Features(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    community_signals: bool = False
    geospatial: bool = False
    llm: bool = False


class IngestionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stale_after_s: float = Field(default=900, gt=0)
    supported_bundle_majors: list[int] = Field(default_factory=lambda: [1])
    adapter_bundle_majors: list[int] = Field(default_factory=lambda: [0])


class OrchestrationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    specialist_deadline_s: float = Field(default=10.0, gt=0)
    agent_retries: int = Field(default=1, ge=0, le=3)
    max_clarification_rounds: int = Field(default=2, ge=0, le=5)
    parallel_specialists: bool = True
    tool_budgets: dict[str, int] = Field(
        default_factory=lambda: {
            "performance_agent": 30,
            "infrastructure_agent": 30,
            "connectivity_agent": 40,
        }
    )


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    #: Any value other than "simulation" fails validation: there is no live mode.
    mode: Literal["simulation"] = "simulation"
    features: Features = Field(default_factory=Features)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    orchestration: OrchestrationSettings = Field(default_factory=OrchestrationSettings)


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> Settings:
    with path.open("rb") as fh:
        return Settings.model_validate(tomllib.load(fh))
