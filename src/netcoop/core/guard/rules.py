"""Load the authority matrix from config/protocol/authority.toml."""

from __future__ import annotations

import tomllib
from functools import cache
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from netcoop.config.settings import CONFIG_DIR
from netcoop.core.vocab import AgentId, MessageType

AUTHORITY_PATH = CONFIG_DIR / "protocol" / "authority.toml"

Reply = Literal["none", "task_request", "question", "relayed_question", "optional"]


class AuthorityRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_type: str
    senders: tuple[str, ...]
    recipients: tuple[str, ...]
    states: tuple[str, ...]
    reply: Reply
    task_kind: str | None = None
    once: bool = False
    requires_decision: bool = False
    counts_round: bool = False
    extension: str | None = None
    note: str = ""

    def any_state(self) -> bool:
        return self.states == ("*",)


class AuthorityRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    hub: str
    closed_states: tuple[str, ...]
    groups: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    rows: tuple[AuthorityRow, ...]

    @model_validator(mode="before")
    @classmethod
    def _expand_groups(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        groups = data.get("groups", {})

        def expand(names: list[str]) -> list[str]:
            out: list[str] = []
            for n in names:
                out += list(groups[n[1:]]) if n.startswith("@") else [n]
            return out

        rows = [
            {**r, "senders": expand(r["senders"]), "recipients": expand(r["recipients"])}
            for r in data.get("rows", [])
        ]
        return {**data, "rows": rows}

    @model_validator(mode="after")
    def _known_terms(self) -> AuthorityRules:
        from netcoop.orchestrator.states import ALLOWED

        states = {s for s in ALLOWED if s is not None}
        participants, types = set(get_args(AgentId)), set(get_args(MessageType))
        for r in self.rows:
            unknown = (
                ({r.message_type} - types)
                | ({*r.senders, *r.recipients} - participants)
                | ({*r.states} - states - {"*"})
            )
            if unknown:
                raise ValueError(f"authority row {r.message_type}: unknown {sorted(unknown)}")
        return self

    def rows_for(self, message_type: str) -> list[AuthorityRow]:
        return [r for r in self.rows if r.message_type == message_type]


@cache
def load_rules(path: Path = AUTHORITY_PATH) -> AuthorityRules:
    with path.open("rb") as f:
        return AuthorityRules.model_validate(tomllib.load(f))
