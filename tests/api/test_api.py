"""FastAPI backend (component 11 server side; T-API-*). Runs the real orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netcoop.api.app import create_app
from netcoop.report.builder import OFFICIAL_KEYS
from netcoop.scenarios.runner import load_scenario


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(db_path=tmp_path / "api.sqlite3"))


def test_health_declares_simulation(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "simulation"
    assert "SIMULATED" in body["banner"]


def test_scenarios(client: TestClient) -> None:
    items = client.get("/api/scenarios").json()
    assert {s["id"] for s in items} >= {"S-01", "S-02", "S-12"}
    one = client.get("/api/scenarios/S-02").json()
    assert one["expected"]["top_cause"] == "link_congestion"
    assert client.get("/api/scenarios/S-99").status_code == 404


def test_run_scenario_then_read_everything(client: TestClient) -> None:
    run = client.post("/api/scenarios/S-02/run", json={})
    assert run.status_code == 201, run.text
    inc = run.json()
    assert inc["incident_id"] == "INC-0001"
    assert inc["state"] == "AWAITING_REVIEW" and inc["status"] == "diagnosed"
    assert inc["top_cause"] == "link_congestion"

    listing = client.get("/api/incidents").json()
    assert [i["incident_id"] for i in listing] == ["INC-0001"]

    detail = client.get("/api/incidents/INC-0001").json()
    assert detail["transitions"][0]["to_state"] == "RECEIVED"
    assert detail["report"]["status"] == "diagnosed"

    strict = client.get("/api/incidents/INC-0001/report", params={"strict": True}).json()
    assert list(strict) == list(OFFICIAL_KEYS)

    md = client.get("/api/incidents/INC-0001/report.md")
    assert md.headers["content-type"].startswith("text/markdown")
    assert "Simulated data" in md.text

    trace = client.get("/api/incidents/INC-0001/trace").json()
    kinds = {e["kind"] for e in trace["events"]}
    assert kinds == {"state", "message"}
    msg = next(e for e in trace["events"] if e["kind"] == "message" and e["type"] == "finding")
    raw = client.get(f"/api/incidents/INC-0001/messages/{msg['message_id']}").json()
    assert raw["message_type"] == "finding" and raw["payload"]["observations"]


def test_post_raw_bundle_and_rejection(client: TestClient) -> None:
    bundle = json.loads(load_scenario("S-01").input_bytes)
    ok = client.post("/api/incidents", json=bundle)
    assert ok.status_code == 201 and ok.json()["status"] == "no_fault_detected"
    bad = client.post("/api/incidents", json={"records": "nope"})
    assert bad.status_code == 201  # accepted for processing; the incident itself is REJECTED
    assert bad.json()["state"] == "REJECTED" and bad.json()["status"] == "failed"


def test_review_flow_over_api(client: TestClient) -> None:
    client.post("/api/scenarios/S-04/run", json={})
    items = client.get("/api/incidents/INC-0001/review").json()
    assert items and all(i["approval_state"] == "pending" for i in items)
    for i in items:
        r = client.post(
            f"/api/incidents/INC-0001/review/{i['index']}",
            json={"decision": "approve", "reviewer": "operator-1", "note": ""},
        )
        assert r.status_code == 200, r.text
        assert r.json()["simulated_outcome"].startswith("SIMULATED")
    again = client.post(
        "/api/incidents/INC-0001/review/0",
        json={"decision": "approve", "reviewer": "operator-1"},
    )
    assert again.status_code == 409
    assert client.get("/api/incidents/INC-0001").json()["state"] == "COMPLETE"
    blank = client.post(
        "/api/incidents/INC-0001/review/0", json={"decision": "approve", "reviewer": ""}
    )
    assert blank.status_code == 422  # validation: reviewer required


def test_pause_and_resume_over_api(client: TestClient) -> None:
    paused = client.post("/api/scenarios/S-02/run", json={"pause_after": "COLLECTING"}).json()
    assert paused["state"] == "COLLECTING" and paused["resumable"] is True
    resumed = client.post("/api/incidents/INC-0001/resume")
    assert resumed.status_code == 200 and resumed.json()["status"] == "diagnosed"


def test_fault_injection_is_validated(client: TestClient) -> None:
    ok = client.post(
        "/api/scenarios/S-02/run", json={"fault_injection": {"performance_agent": "error"}}
    )
    assert ok.status_code == 201
    bad = client.post(
        "/api/scenarios/S-02/run", json={"fault_injection": {"performance_agent": "explode"}}
    )
    assert bad.status_code == 422


def test_topology_and_fields(client: TestClient) -> None:
    topo = client.get("/api/topology/campus_v1").json()
    assert topo["provenance"] == "SIMULATED" and len(topo["nodes"]) == 10
    assert client.get("/api/topology/nope").status_code == 404
    assert "latency_ms" in client.get("/api/field-dictionary").json()["fields"]


def test_unknown_incident_404(client: TestClient) -> None:
    for path in (
        "/api/incidents/INC-9",
        "/api/incidents/INC-9/report",
        "/api/incidents/INC-9/trace",
    ):
        assert client.get(path).status_code == 404, path


def test_cors_for_dashboard_dev_server(client: TestClient) -> None:
    r = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_no_device_changing_endpoint(client: TestClient) -> None:  # T-SAFE-04
    paths = client.get("/openapi.json").json()["paths"]
    for path, ops in paths.items():
        for method in ops:
            if method in ("post", "put", "patch", "delete"):
                assert path in {
                    "/api/scenarios/{scenario_id}/run",
                    "/api/incidents",
                    "/api/incidents/{incident_id}/resume",
                    "/api/incidents/{incident_id}/review/{index}",
                }, (method, path)
