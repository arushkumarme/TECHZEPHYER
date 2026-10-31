"""Dashboard end-to-end in a real browser (component 11; T-UI-*, T-UI-LABEL-*).

Starts the real backend serving the built dashboard (``dashboard/dist``) with both
extensions enabled, then drives it with Playwright/Chromium. Requires
``npm --prefix dashboard run build`` and ``uv run playwright install chromium``.
Marked ``ui``; run with ``uv run pytest -m ui``.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui
REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "dashboard" / "dist"
SHOTS = Path(os.environ.get("NETCOOP_SCREENSHOTS", REPO / "var" / "screenshots"))

playwright_api = pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    if not (DIST / "index.html").is_file():
        pytest.fail("dashboard not built: run `npm --prefix dashboard run build` first")
    port = _free_port()
    env = {
        **os.environ,
        "NETCOOP_DB": str(tmp_path_factory.mktemp("ui") / "ui.sqlite3"),
        "NETCOOP_ENABLE": "community_signals,geospatial",
        "NETCOOP_DASHBOARD_DIST": str(DIST),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "netcoop.api.app:app", "--port", str(port)],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("backend did not start")
        yield url
    finally:
        proc.terminate()  # only the server this test started
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def page(base_url: str) -> Iterator[object]:
    SHOTS.mkdir(parents=True, exist_ok=True)
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base_url)
        pg.wait_for_load_state("networkidle")
        yield pg
        browser.close()
        assert errors == [], errors


def test_banner_and_empty_state(page) -> None:  # type: ignore[no-untyped-def]  # T-UI-LABEL-01
    banner = page.get_by_role("note")
    assert "Simulated data" in banner.inner_text()
    assert "no access to any real campus network" in banner.inner_text()
    assert page.get_by_text("Run a scenario to start one.").is_visible()
    for tab in ("Incidents", "Campus map", "User reports"):
        assert page.get_by_role("tab", name=tab).is_visible()


def test_run_scenario_shows_report_and_exchange(page) -> None:  # type: ignore[no-untyped-def]
    page.get_by_label("Scenario", exact=True).select_option("S-02")
    page.get_by_role("button", name="Run diagnosis").click()
    page.locator(
        ".cause", has_text="Likely link congestion causing egress queue drops on SW_CAMPUS_4"
    ).wait_for()
    assert page.get_by_role("meter", name="Heuristic confidence score").is_visible()
    assert "not a probability" in page.locator(".meter").inner_text()
    svg = page.get_by_role("img", name="Message exchange")
    assert svg.is_visible()
    # 3 specialist tasks + correlation + reporting at minimum
    assert page.locator(".swim .arrow").count() >= 10
    page.locator(".swim .row-hit").nth(5).click()
    assert page.locator(".swim-detail").inner_text() != "Select a row to read the message."
    assert page.get_by_role("cell", name="link_utilization_pct").first.is_visible()
    page.screenshot(path=str(SHOTS / "incident.png"), full_page=True)


def test_review_requires_name_and_shows_simulation(page) -> None:  # type: ignore[no-untyped-def]
    approve = page.get_by_role("button", name="Approve").first
    assert approve.is_disabled()  # who decides must be recorded
    page.get_by_label("Your name (recorded with each decision)").fill("operator-1")
    approve.click()
    outcome = page.locator(".outcome").first
    outcome.wait_for()
    assert outcome.inner_text().startswith("SIMULATED")


def test_fault_injection_degrades_visibly(page) -> None:  # type: ignore[no-untyped-def]  # S-10
    page.get_by_text("Simulate an agent failure").click()
    page.get_by_label("Failure", exact=True).select_option("invalid")
    page.get_by_role("button", name="Run diagnosis").click()
    # A horizontal SVG line has a zero-height box, so Playwright never deems it
    # "visible"; the arrow is drawn, so wait for it to be attached instead.
    page.locator(".swim .arrow.error").first.wait_for(state="attached")
    assert page.get_by_text("No finding from performance_agent").first.is_visible()


def test_community_flow(page) -> None:  # type: ignore[no-untyped-def]  # Demo-7
    page.get_by_role("tab", name="User reports").click()
    for who, text in (
        ("test-1", "Hostel A Wi-Fi is disconnecting."),
        ("test-2", "wifi in hostel a keeps dropping"),
    ):
        page.get_by_label("What is happening, and where?").fill(text)
        page.get_by_label("Reporter (test account; stored only as a pseudonym)").fill(who)
        page.get_by_role("button", name="Send report").click()
        page.get_by_role("status").wait_for()
    page.get_by_role("cell", name="ZONE_HOSTEL_A").wait_for()
    page.screenshot(path=str(SHOTS / "community.png"), full_page=True)
    page.get_by_role("button", name="Investigate").click()
    page.get_by_text("User reports (unverified").wait_for()
    assert "corroborated" in page.locator(".notice").first.inner_text()


def test_map_layers(page) -> None:  # type: ignore[no-untyped-def]  # Demo-8, T-UI-*, X-GEO-01
    page.get_by_role("tab", name="Campus map").click()
    page.locator(".leaflet-container").wait_for()
    assert "SCHEMATIC" in page.get_by_text("Team-authored SCHEMATIC layout").inner_text()
    options = page.get_by_label("Show incident").locator("option").all_inner_texts()
    corroborated = next(o for o in options if "CAND" in o)
    page.get_by_label("Show incident").select_option(label=corroborated)
    page.wait_for_load_state("networkidle")
    assert page.locator("path.leaflet-interactive").count() >= 20  # zones + links + devices
    legend = page.get_by_label("Map legend").inner_text()
    for item in ("Reported by users (unverified)", "Detected fault", "Would be isolated"):
        assert item in legend
    page.screenshot(path=str(SHOTS / "map.png"), full_page=True)


def test_keyboard_reaches_controls(page) -> None:  # type: ignore[no-untyped-def]  # a11y floor
    page.get_by_role("tab", name="Incidents").focus()
    page.keyboard.press("Tab")
    focused = page.evaluate("document.activeElement.tagName")
    assert focused in {"BUTTON", "SELECT", "INPUT", "SUMMARY", "TEXTAREA"}
