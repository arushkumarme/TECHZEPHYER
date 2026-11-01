"""LLM gateway: optional, provider-independent, grounded, never decides (CD-1; T-LLM-*)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from netcoop.config.settings import load_settings
from netcoop.core.log_store import LogStore
from netcoop.llm.gateway import (
    LLMGateway,
    NullProvider,
    StaticProvider,
    grounding_violations,
)
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.report.builder import OFFICIAL_KEYS
from netcoop.scenarios.runner import load_scenario

ALLOWED = {"SW_CAMPUS_4", "latency_ms", "link_utilization_pct", "0.66", "312.4"}


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("Link congestion on SW_CAMPUS_9 is likely.", "SW_CAMPUS_9"),
        ("Latency reached 999 ms on SW_CAMPUS_4.", "999"),
        ("The root cause is certainly fixed now.", "fixed"),
        ("Confidence is calibrated at 0.66.", "calibrated"),
        ("queue_drops rose sharply on SW_CAMPUS_4.", "queue_drops"),
        ("Live monitoring shows congestion.", "live"),
    ],
)
def test_grounding_rejects_unsupported_claims(text: str, problem: str) -> None:  # T-LLM-GROUND
    problems = grounding_violations(text, allowed_terms=ALLOWED)
    assert any(problem.lower() in p.lower() for p in problems), problems


def test_grounding_accepts_faithful_rephrase() -> None:
    text = "SW_CAMPUS_4 probably suffers link congestion: latency_ms peaked at 312.4 (score 0.66)."
    assert grounding_violations(text, allowed_terms=ALLOWED) == []


def test_disabled_gateway_never_calls_provider() -> None:
    calls: list[str] = []
    gw = LLMGateway(StaticProvider(lambda s, p: calls.append(p) or "x"), enabled=False)
    out = gw.reword("template text", allowed_terms=set())
    assert (out.text, out.used_llm, out.status) == ("template text", False, "disabled")
    assert calls == []


def test_unavailable_provider_falls_back() -> None:
    out = LLMGateway(NullProvider(), enabled=True).reword("template", allowed_terms=set())
    assert (out.text, out.status) == ("template", "LLM_UNAVAILABLE")


def test_provider_exception_details_are_not_exposed() -> None:
    secret = "mock-private-value-do-not-log"

    def fail(_system: str, _prompt: str) -> str:
        raise RuntimeError(f"request failed with credential {secret}")

    out = LLMGateway(StaticProvider(fail), enabled=True).reword("template", allowed_terms=set())

    assert (out.text, out.status) == ("template", "LLM_UNAVAILABLE")
    assert out.reason == "RuntimeError: provider request failed"
    assert secret not in (out.reason or "")


def test_rejected_output_falls_back() -> None:
    gw = LLMGateway(StaticProvider(lambda s, p: "Device SW_CAMPUS_99 exploded."), enabled=True)
    out = gw.reword("template", allowed_terms={"SW_CAMPUS_4"})
    assert out.text == "template" and out.status == "LLM_OUTPUT_REJECTED"
    assert out.reason and "SW_CAMPUS_99" in out.reason


def test_accepted_output_is_used() -> None:
    gw = LLMGateway(StaticProvider(lambda s, p: "A clearer summary."), enabled=True)
    out = gw.reword("template", allowed_terms=set())
    assert (out.text, out.used_llm, out.status) == ("A clearer summary.", True, "accepted")


def _run(tmp_path: Path, gateway: LLMGateway | None) -> dict[str, object]:
    o = Orchestrator(LogStore(tmp_path / "log.sqlite3"), llm=gateway)
    return o.run(load_scenario("S-02").input_bytes).report


def test_provider_exception_details_are_not_persisted_in_report(tmp_path: Path) -> None:
    secret = "mock-private-value-do-not-log"

    def fail(_system: str, _prompt: str) -> str:
        raise RuntimeError(f"request failed with credential {secret}")

    report = _run(tmp_path, LLMGateway(StaticProvider(fail), enabled=True))

    assert secret not in json.dumps(report)
    extension = report["netcoop_extensions"]
    assistance = extension["llm_assistance"]  # type: ignore[index]
    assert assistance[0]["reason"] == "RuntimeError: provider request failed"


def test_llm_never_changes_diagnosis(tmp_path: Path) -> None:  # T-LLM-OFF-01
    off = _run(tmp_path / "off", None)
    faithful = LLMGateway(
        StaticProvider(lambda s, p: "In short: likely link congestion on SW_CAMPUS_4."),
        enabled=True,
    )
    on = _run(tmp_path / "on", faithful)
    for key in OFFICIAL_KEYS:
        if key != "incident_id":
            assert on[key] == off[key], key
    ext_on, ext_off = on["netcoop_extensions"], off["netcoop_extensions"]  # type: ignore[index]
    assert ext_off["llm_assistance"] == []  # type: ignore[index]
    assert ext_on["llm_assistance"] == [  # type: ignore[index]
        {"field": "netcoop_extensions.narrative", "status": "accepted", "provider": "static"}
    ]
    assert ext_on["narrative"] == "In short: likely link congestion on SW_CAMPUS_4."  # type: ignore[index]
    assert ext_off["narrative"]  # deterministic template always present  # type: ignore[index]


def test_hallucinating_llm_is_rejected_in_a_real_run(tmp_path: Path) -> None:
    liar = LLMGateway(StaticProvider(lambda s, p: "SW_CAMPUS_7 failed at 2 am."), enabled=True)
    report = _run(tmp_path, liar)
    ext = report["netcoop_extensions"]  # type: ignore[index]
    assert ext["llm_assistance"][0]["status"] == "LLM_OUTPUT_REJECTED"  # type: ignore[index]
    assert "SW_CAMPUS_7" not in ext["narrative"]  # type: ignore[index]


def test_llm_is_off_by_default() -> None:
    assert load_settings().features.llm is False


@pytest.mark.parametrize("sid", ["S-01", "S-02", "S-04", "S-05", "S-06", "S-08", "S-09", "S-12"])
def test_echoing_the_template_is_always_grounded(tmp_path: Path, sid: str) -> None:
    """An LLM that returns the template unchanged must pass the grounding check; otherwise
    the allowed-term set built from the report is wrong."""

    def echo(_system: str, prompt: str) -> str:
        return prompt.removeprefix("<summary>").removesuffix("</summary>")

    o = Orchestrator(
        LogStore(tmp_path / "log.sqlite3"), llm=LLMGateway(StaticProvider(echo), enabled=True)
    )
    ext = o.run(load_scenario(sid).input_bytes).report["netcoop_extensions"]
    assert ext["llm_assistance"][0]["status"] == "accepted", ext["llm_assistance"]
