"""Recommendation & Reporting Agent — ``reporting_agent`` (A-REPT, doc 03 §2.5).

Builds the official report + extension block and its Markdown rendering. It chooses the
recommendation *mode* from the decision (corrective / monitoring / diagnostic next steps),
marks every recommendation as simulated and requiring human approval, and validates the
report before releasing it. It never changes the status, cause or confidence set by the
correlation agent. If the decision is missing or invalid it still emits a schema-valid
failure report.
"""

from __future__ import annotations

from typing import Any

from netcoop.core.bus import MessageBus
from netcoop.core.messages import (
    AgentError,
    Decision,
    Envelope,
    Finding,
    ParsedMessage,
    ReportReady,
    TaskRequest,
)
from netcoop.core.vocab import AgentId
from netcoop.ingestion.models import NormalizedBundle
from netcoop.llm.gateway import LLMGateway, report_terms
from netcoop.report.builder import build_failure_report, build_report
from netcoop.report.markdown import render_markdown
from netcoop.report.validate import validate_report


def reporting_context(
    incident_id: str,
    bundle: NormalizedBundle,
    decision: Decision,
    findings: dict[str, Finding],
    *,
    mode: str,
    missing_agents: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    dq = bundle.data_quality
    return {
        "incident_id": incident_id,
        "decision": decision.model_dump(mode="json"),
        "findings": {a: f.model_dump(mode="json") for a, f in sorted(findings.items())},
        "data_quality": {
            "completeness": round(dq.completeness, 4),
            "freshness": round(dq.freshness, 4),
            "consistency": round(dq.consistency, 4),
            "q": round(dq.q, 4),
            "acceptance": dq.acceptance,
            "warnings": dq.warnings,
        },
        "provenance": bundle.provenance,
        "mode": mode,
        "missing_agents": missing_agents or [],
        "generated_at": generated_at,
    }


class ReportingAgent:
    agent_id: AgentId = "reporting_agent"

    def __init__(self, bus: MessageBus, llm: LLMGateway | None = None) -> None:
        self.bus = bus
        self.llm = llm

    def handle(self, msg: ParsedMessage) -> Envelope:
        try:
            if not isinstance(msg.payload, TaskRequest):
                raise ValueError(f"reporting_agent cannot handle {msg.envelope.message_type}")
            report = self.compose(msg.payload.context)
            return self.bus.reply(
                msg,
                message_type="report_ready",
                payload=ReportReady(report=report, markdown=render_markdown(report)),
            )
        except Exception as exc:
            return self.bus.reply(
                msg,
                message_type="agent_error",
                payload=AgentError(
                    code="AGENT_FAILED", message=f"{type(exc).__name__}: {exc}", recoverable=True
                ),
                status="error",
            )

    def compose(self, ctx: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime

        incident_id = str(ctx["incident_id"])
        generated = ctx.get("generated_at")
        at = datetime.fromisoformat(generated) if generated else None
        try:
            decision = Decision.model_validate(ctx["decision"])
            findings = {a: Finding.model_validate(f) for a, f in ctx["findings"].items()}
        except Exception as exc:  # decision missing/invalid -> failure report (doc 03 §2.5)
            return build_failure_report(
                incident_id,
                [f"AGENT_FAILED: correlation result unusable ({type(exc).__name__})"],
                mode=ctx.get("mode", "simulation"),
                provenance=ctx.get("provenance", "unspecified"),
                generated_at=at,
            )
        report = build_report(
            incident_id,
            decision,
            findings,
            data_quality=ctx.get("data_quality", {}),
            provenance=ctx.get("provenance", "unspecified"),
            mode=ctx.get("mode", "simulation"),
            missing_agents=ctx.get("missing_agents", []),
            generated_at=at,
        )
        problems = validate_report(
            report,
            observation_ids={o.observation_id for f in findings.values() for o in f.observations},
            finding_agents=set(findings),
        )
        if problems:
            raise ValueError("report failed validation: " + "; ".join(problems))
        if self.llm is not None and self.llm.enabled:
            self._reword(report)
        return report

    def _reword(self, report: dict[str, Any]) -> None:
        """Optional LLM wording of the narrative only (CD-1). Official keys untouched."""
        assert self.llm is not None
        ext = report["netcoop_extensions"]
        template = ext["narrative"]
        result = self.llm.reword(template, allowed_terms=report_terms(report, template))
        ext["narrative"] = result.text
        entry: dict[str, Any] = {
            "field": "netcoop_extensions.narrative",
            "status": result.status,
            "provider": result.provider,
        }
        if result.reason:
            entry["reason"] = result.reason
        ext["llm_assistance"] = [entry]
