"""Community Signal Intelligence pipeline (Extension A, doc 10 §4).

intake -> pseudonymize -> strip personal data -> screen (length, spam, rate limit,
duplicates) -> extract -> resolve zone -> cluster by zone/time window counting DISTINCT
reporters -> candidate incident -> ``community_candidate`` message to the orchestrator.

All complaints in hackathon mode are synthetic test submissions (CD-11). Complaints are
UNVERIFIED: they can trigger and scope an investigation and add a small bounded score
term, but they never change a decision (doc 08 §6, enforced in the scorer).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from netcoop.community.extract import Extraction, extract_llm, extract_rules, lexicon
from netcoop.core.log_store import LogStore
from netcoop.llm.gateway import LLMGateway
from netcoop.orchestrator.workflow import IncidentResult, Orchestrator
from netcoop.tools.topology import load_topology

_SCHEMA = """
CREATE TABLE IF NOT EXISTS community_complaints (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL,
    channel      TEXT NOT NULL,
    reporter     TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    text         TEXT NOT NULL,
    status       TEXT NOT NULL,
    reason       TEXT,
    zone         TEXT,
    location_text TEXT,
    symptoms     TEXT NOT NULL,
    severity     INTEGER NOT NULL,
    method       TEXT NOT NULL,
    flags        TEXT NOT NULL
);
"""
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_NAME = re.compile(r"\b(my name is|i am|this is)\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?", re.I)
_NORMAL = re.compile(r"[^a-z0-9]+")
DEFAULT_SALT = "netcoop-simulation-only-salt"  # real deployments must set a secret salt


class Complaint(BaseModel):
    model_config = ConfigDict(frozen=True)
    complaint_id: str
    channel: str
    reporter: str = Field(description="Pseudonym, never the raw identifier")
    received_at: datetime
    text: str = Field(description="Sanitised text (personal data removed)")
    status: str
    reason: str | None = None
    zone: str | None = None
    location_text: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    severity: int = 1
    extraction_method: str = "rules"
    flags: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate_id: str
    zone: str
    entities: list[str]
    symptom_categories: list[str]
    start: datetime
    end: datetime
    complaint_ids: list[str]
    complaint_count: int
    distinct_reporters: int
    trust_label: str = "reported_unverified"
    provenance: str = "synthetic complaints (test submissions)"

    def as_context(self) -> dict[str, Any]:
        """The form carried in the orchestrator's community input and correlation context."""
        return {
            "candidate_id": self.candidate_id,
            "zone": self.zone,
            "entities": self.entities,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "symptom_categories": self.symptom_categories,
            "complaint_count": self.complaint_count,
            "distinct_reporters": self.distinct_reporters,
        }


@dataclass(frozen=True)
class SubmitResult:
    accepted: bool
    duplicate: bool = False
    complaint_id: str | None = None
    reason: str | None = None
    zone: str | None = None
    symptoms: tuple[str, ...] = ()


class CommunityPipeline:
    def __init__(self, store: LogStore, *, llm: LLMGateway | None = None) -> None:
        self.store = store
        self.llm = llm
        self.lex = lexicon()
        self.salt = os.environ.get("NETCOOP_PSEUDONYM_SALT", DEFAULT_SALT).encode()
        store.add_tables(_SCHEMA, ("community_complaints",))

    @property
    def window(self) -> timedelta:
        return timedelta(minutes=int(self.lex.clustering["window_minutes"]))

    # ------------------------------------------------------------------ intake
    def pseudonym(self, reporter: str) -> str:
        digest = hmac.new(self.salt, reporter.encode(), hashlib.sha256).hexdigest()
        return f"anon-{digest[:10]}"

    @staticmethod
    def sanitize(text: str) -> str:
        text = _EMAIL.sub("[email]", text)
        text = _PHONE.sub("[phone]", text)
        return _NAME.sub(lambda m: f"{m.group(1)} [name]", text).strip()

    def submit(
        self, text: str, *, channel: str, reporter: str, received_at: datetime
    ) -> SubmitResult:
        if received_at.tzinfo is None:
            raise ValueError("received_at must be timezone-aware")
        pseudo = self.pseudonym(reporter)
        clean = self.sanitize(text or "")
        scr = self.lex.screening
        existing = self.complaints()
        cid = f"CMP-{len(existing) + 1:04d}"
        recent = [
            c
            for c in existing
            if c.reporter == pseudo
            and c.status in ("accepted", "duplicate")
            and received_at - c.received_at <= self.window
        ]
        status, reason = "accepted", None
        letters = sum(ch.isalpha() for ch in clean)
        if len(clean) < scr["min_chars"] or len(clean) > scr["max_chars"]:
            status, reason = "rejected", f"length must be {scr['min_chars']}-{scr['max_chars']}"
        elif letters < 3:
            status, reason = "rejected", "no readable text (spam or malformed)"
        elif len(recent) >= scr["max_per_reporter_per_window"]:
            status, reason = "rate_limited", "too many reports from this reporter in the window"
        elif any(_norm(c.text) == _norm(clean) for c in recent):
            status, reason = "duplicate", "same reporter, same text within the window"
        extraction = Extraction()
        if status in ("accepted", "duplicate"):
            llm = extract_llm(clean, self.llm) if self.llm is not None else None
            extraction = llm or extract_rules(clean)
        self.store.insert_row(
            "community_complaints",
            {
                "complaint_id": cid,
                "channel": channel,
                "reporter": pseudo,
                "received_at": received_at.isoformat(),
                "text": clean,
                "status": status,
                "reason": reason,
                "zone": extraction.zone,
                "location_text": extraction.location_text,
                "symptoms": json.dumps(extraction.symptoms),
                "severity": extraction.severity,
                "method": extraction.method,
                "flags": json.dumps(extraction.flags),
            },
        )
        return SubmitResult(
            accepted=status in ("accepted", "duplicate"),
            duplicate=status == "duplicate",
            complaint_id=cid,
            reason=reason,
            zone=extraction.zone,
            symptoms=tuple(extraction.symptoms),
        )

    def complaints(self) -> list[Complaint]:
        return [
            Complaint(
                complaint_id=r["complaint_id"],
                channel=r["channel"],
                reporter=r["reporter"],
                received_at=datetime.fromisoformat(r["received_at"]),
                text=r["text"],
                status=r["status"],
                reason=r["reason"],
                zone=r["zone"],
                location_text=r["location_text"],
                symptoms=json.loads(r["symptoms"]),
                severity=r["severity"],
                extraction_method=r["method"],
                flags=json.loads(r["flags"]),
            )
            for r in self.store.rows("community_complaints")
        ]

    def stats(self) -> dict[str, int]:
        cs = self.complaints()
        out = {
            s: sum(1 for c in cs if c.status == s)
            for s in ("accepted", "rejected", "rate_limited", "duplicate")
        }
        out["unlocated"] = sum(1 for c in cs if c.status == "accepted" and c.zone is None)
        out["total"] = len(cs)
        return out

    # ------------------------------------------------------------------ clustering
    def candidates(self) -> list[Candidate]:
        """Deterministic recomputation from the stored complaints."""
        usable = sorted(
            (c for c in self.complaints() if c.status == "accepted" and c.zone is not None),
            key=lambda c: (c.zone or "", c.received_at, c.complaint_id),
        )
        topo = load_topology(str(self.lex.clustering["candidate_topology"]))
        clusters: list[list[Complaint]] = []
        for c in usable:
            last = clusters[-1] if clusters else None
            if (
                last
                and last[0].zone == c.zone
                and c.received_at - last[0].received_at <= self.window
            ):
                last.append(c)
            else:
                clusters.append([c])
        out: list[Candidate] = []
        minimum = int(self.lex.clustering["min_distinct_reporters"])
        for group in clusters:
            reporters = {c.reporter for c in group}
            if len(reporters) < minimum:
                continue
            zone = group[0].zone or ""
            out.append(
                Candidate(
                    candidate_id=f"CAND-{len(out) + 1:04d}",
                    zone=zone,
                    entities=topo.entities_in_zone(zone),
                    symptom_categories=sorted({s for c in group for s in c.symptoms}),
                    start=group[0].received_at - self.window,
                    end=group[-1].received_at,
                    complaint_ids=[c.complaint_id for c in group],
                    complaint_count=len(group),
                    distinct_reporters=len(reporters),
                )
            )
        return out

    # ------------------------------------------------------------------ investigation
    def investigate(
        self, candidate_id: str, orchestrator: Orchestrator, telemetry: bytes | str
    ) -> IncidentResult:
        """Ask the five agents to investigate a candidate against a telemetry bundle."""
        cand = next((c for c in self.candidates() if c.candidate_id == candidate_id), None)
        if cand is None:
            raise KeyError(f"unknown candidate {candidate_id}")
        return orchestrator.run(
            telemetry,
            source="community",
            label=f"{candidate_id} ({cand.zone})",
            community=[cand.as_context()],
        )


def _norm(text: str) -> str:
    return _NORMAL.sub(" ", text.lower()).strip()
