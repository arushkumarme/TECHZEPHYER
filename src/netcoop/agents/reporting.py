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

from netcoop.core.blocks import Recommendation
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
    community: list[dict[str, Any]] | None = None,
    community_errors: list[str] | None = None,
    data_snapshot: dict[str, Any] | None = None,
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
        "community": community or [],
        "community_errors": community_errors or [],
        "data_snapshot": data_snapshot,
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
                payload=ReportReady(
                    report=report,
                    markdown=render_markdown(report),
                    recommendations=recommendations_for(report),
                ),
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
            community=ctx.get("community", []),
            community_errors=ctx.get("community_errors", []),
            data_snapshot=ctx.get("data_snapshot"),
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


#: PROVISIONAL (D-24): priority follows the order of the official recommended_actions.
_PRIORITY_BY_ORDER = ("high", "medium")


def recommendations_for(report: dict[str, Any]) -> list[Recommendation]:
    """The official report's recommended_actions as structured, always-simulated,
    approval-gated recommendations (same order as ``recommendation_status``)."""
    ext = report.get("netcoop_extensions", {})
    kind = ext.get("recommendation_mode") or "diagnostic_next_steps"
    return [
        Recommendation(
            recommendation_id=f"RCM-{i:04d}",
            action_text=action,
            kind=kind,
            target_entities=list(report["affected_devices"]),
            reason=report["suspected_root_cause"],
            priority=_PRIORITY_BY_ORDER[i - 1] if i <= len(_PRIORITY_BY_ORDER) else "low",
            precautions=[
                "Simulated only: nothing is executed on a network.",
                "Requires human approval before any real-world use.",
            ],
            verification_step="Re-run the diagnosis on fresh simulated data and check that "
            "the suspected cause no longer passes the decision gate.",
        )
        for i, action in enumerate(report["recommended_actions"], start=1)
    ]
