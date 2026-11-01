"""Runtime settings (``config/netcoop.toml``). Only simulation mode exists (doc 02 §5)."""

from __future__ import annotations

import os
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
    #: How agents read data: "direct" (in-process tool layer) or "mcp" (through the
    #: NetCoop MCP server, component 8). Results are identical; "mcp" proves the interface.
    tool_transport: Literal["direct", "mcp"] = "direct"
    tool_budgets: dict[str, int] = Field(
        default_factory=lambda: {
            "performance_agent": 30,
            "infrastructure_agent": 30,
            "connectivity_agent": 40,
        }
    )


class ProtocolSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    #: PROVISIONAL (D-23): about 20x the largest message of the scenario suite.
    max_message_bytes: int = Field(default=1_048_576, ge=1024)
    #: PROVISIONAL (D-22): incident ids are <prefix>-NNNN; the PDF mandates no format.
    incident_prefix: str = Field(default="INC", pattern=r"^[A-Z]{2,8}$")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    #: Any value other than "simulation" fails validation: there is no live mode.
    mode: Literal["simulation"] = "simulation"
    features: Features = Field(default_factory=Features)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    orchestration: OrchestrationSettings = Field(default_factory=OrchestrationSettings)
    protocol: ProtocolSettings = Field(default_factory=ProtocolSettings)


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> Settings:
    """Load ``config/netcoop.toml``. ``NETCOOP_ENABLE`` (comma-separated feature names,
    e.g. ``community_signals,geospatial``) switches optional features on for a demo
    without editing the file. Unknown names are refused, never ignored."""
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    enable = [f.strip() for f in os.environ.get("NETCOOP_ENABLE", "").split(",") if f.strip()]
    if enable:
        known = set(Features.model_fields)
        unknown = sorted(set(enable) - known)
        if unknown:
            raise ValueError(f"NETCOOP_ENABLE: unknown features {unknown}; known: {sorted(known)}")
        data.setdefault("features", {}).update({f: True for f in enable})
    return Settings.model_validate(data)
