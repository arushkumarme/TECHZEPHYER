"""Markdown rendering of a JSON report (doc 07 §7). Always rendered *from* the JSON."""

from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    ext = report.get("netcoop_extensions", {})
    lines = [
        f"# NetCoop AI diagnostic report — {report['incident_id']}",
        "",
        f"> **Simulated data — scenario playback.** Mode: `{ext.get('mode', 'simulation')}`; "
        f"data provenance: `{ext.get('data_provenance', 'unspecified')}`; topology: "
        f"`{ext.get('topology_provenance', 'unavailable')}`.",
        "",
        f"**Status:** `{report['status']}`  ",
        f"**Probable cause:** {report['suspected_root_cause']}  ",
        f"**Confidence:** {report['confidence']:.2f} ({ext.get('confidence_category', 'n/a')}, "
        f"{ext.get('confidence_method', 'heuristic')} score)  ",
        f"**Affected devices:** {', '.join(report['affected_devices']) or 'none identified'}",
        "",
        "## Supporting evidence",
        "",
    ]
    if report["supporting_evidence"]:
        lines += ["| Metric | Value | Interpretation |", "|---|---|---|"]
        lines += [
            f"| `{e['metric']}` | {e['value']} | {e['interpretation']} |"
            for e in report["supporting_evidence"]
        ]
    else:
        lines.append("_None._")
    lines += ["", f"Evidence sources: {', '.join(report['evidence_sources']) or 'none'}", ""]
    lines += ["## Alternative explanations", ""]
    lines += [f"- {a}" for a in report["alternative_causes"]] or ["- None scored."]
    na = ext.get("not_assessable", [])
    lines += ["", "## Not assessable", ""]
    if na:
        by_metric: dict[str, list[str]] = {}
        for n in na:
            by_metric.setdefault(f"{n['metric']} ({n['reason']})", []).append(n["entity"])
        lines += [f"- `{k}`: {', '.join(sorted(v))}" for k, v in sorted(by_metric.items())]
    else:
        lines.append("- Everything in scope was assessed.")
    lines += [
        "",
        "## Recommended actions — simulated, require human approval",
        "",
    ]
    status = {r["action"]: r for r in ext.get("recommendation_status", [])}
    for a in report["recommended_actions"]:
        state = status.get(a, {}).get("approval_state", "pending")
        lines.append(f"- [{state}] {a}")
    trace = ext.get("agent_contributions", {})
    if trace:
        lines += [
            "",
            "## Agent contributions",
            "",
            "| Agent | Status | Observations | Tool calls |",
        ]
        lines.append("|---|---|---|---|")
        for agent, c in trace.items():
            lines.append(
                f"| {agent} | {c.get('status')} | {c.get('observations', '-')} | "
                f"{c.get('tool_calls', '-')} |"
            )
    if ext.get("clarifications"):
        lines += ["", "## Clarifications", ""]
        lines += [
            f"- Round {c['round']}: {c['question_type']} → {c['target']} "
            f"({'answered' if c['answered'] else 'not answered'}): {c['summary']}"
            for c in ext["clarifications"]
        ]
    lines += ["", "## Limitations", ""]
    lines += [f"- {lim}" for lim in report["limitations"]]
    return "\n".join(lines) + "\n"
