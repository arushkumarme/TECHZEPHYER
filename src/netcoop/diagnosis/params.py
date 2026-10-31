"""Diagnosis parameters (``config/diagnosis.toml``, doc 08 §10). All heuristic (CD-6)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from netcoop.config.settings import CONFIG_DIR
from netcoop.core.vocab import Severity

DEFAULT_DIAGNOSIS_PATH = CONFIG_DIR / "diagnosis.toml"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Threshold(_M):
    elevated_above: float
    critical_at: float


class Scoring(_M):
    e_mid: float = Field(ge=0, le=1)
    lambda_: float = Field(alias="lambda", ge=0)
    mu: float = Field(ge=0)
    beta: float = Field(ge=0)
    gamma_max: float = Field(ge=0)


class Ceiling(_M):
    bands: list[tuple[float, float]]
    missing_topology_penalty: float
    missing_agent_penalty: float

    def cap(self, q: float) -> float:
        for lower, cap in self.bands:
            if q >= lower:
                return cap
        return self.bands[-1][1]


class Gate(_M):
    tau_diag: float
    n_min: int
    s_min: int
    delta: float
    coverage_min: float
    c_insuff_cap: float


class Categories(_M):
    t_high: float
    t_med: float


class Conflicts(_M):
    freshness_tolerance_s: float


class DiagnosisParams(_M):
    schema_: str = Field(alias="schema")
    severity: dict[str, Threshold]
    status_severity: dict[str, Severity]
    weights: dict[str, float]
    contradiction_weights: dict[str, float]
    scoring: Scoring
    ceiling: Ceiling
    gate: Gate
    categories: Categories
    conflicts: Conflicts


def load_diagnosis_params(path: Path = DEFAULT_DIAGNOSIS_PATH) -> DiagnosisParams:
    with path.open("rb") as fh:
        return DiagnosisParams.model_validate(tomllib.load(fh))
