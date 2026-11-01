import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { S02_DETAIL, S02_TRACE } from "./components/__fixtures__/s02";

const SUMMARY = { ...S02_DETAIL, transitions: undefined, report: undefined };
let listed: unknown[] = [];

vi.mock("./api", () => ({
  api: {
    health: vi.fn(async () => ({
      status: "ok", mode: "simulation", banner: "", version: "t",
      features: { community_signals: true, geospatial: false, llm: false },
    })),
    scenarios: vi.fn(async () => [{ id: "S-02", title: "Hostel congestion", provenance: "synthetic" }]),
    incidents: vi.fn(async () => listed),
    runScenario: vi.fn(async () => { listed = [SUMMARY]; return SUMMARY; }),
    incident: vi.fn(async () => S02_DETAIL),
    trace: vi.fn(async () => ({ events: S02_TRACE })),
    review: vi.fn(async () => []),
    candidates: vi.fn(async () => []),
  },
}));

import { api } from "./api";
import App from "./App";

beforeEach(() => { listed = []; });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const faultMenu = () => document.querySelector("details.fault-menu") as HTMLDetailsElement;
const openFaultMenu = async () => {
  fireEvent.click(screen.getByText("Simulate an agent failure"));
  await waitFor(() => expect(faultMenu().open).toBe(true));
};

describe("App", () => {
  it("shows the campus map and the hint before any incident", async () => {
    const { container } = render(<App />);
    expect(await screen.findAllByText("Run a scenario to start one.", { exact: false })).toHaveLength(1);
    expect(screen.getByText(/No incident selected/)).toBeInTheDocument();
    expect(container.querySelector(".incident-hero .leaflet-container")).not.toBeNull();
    // Layers are null here (geospatial off): the network-off notice still applies.
    expect(screen.getByText(/Network layer off/)).toBeInTheDocument();
  });

  it("closes the failure menu on an outside click, on Escape, on a tab change and after a run", async () => {
    render(<App />);
    await screen.findByRole("option", { name: /S-02/ });

    await openFaultMenu();
    expect(screen.getByLabelText("Agent")).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByLabelText("Failure"));
    expect(faultMenu().open).toBe(true); // a click inside keeps it open
    fireEvent.pointerDown(document.body);
    await waitFor(() => expect(faultMenu().open).toBe(false));

    await openFaultMenu();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(faultMenu().open).toBe(false));

    await openFaultMenu();
    fireEvent.click(screen.getByRole("tab", { name: "User reports" }));
    await waitFor(() => expect(faultMenu().open).toBe(false));

    await openFaultMenu();
    fireEvent.click(screen.getByRole("button", { name: "Run diagnosis" }));
    await waitFor(() => expect(faultMenu().open).toBe(false));
    await waitFor(() => expect(api.runScenario).toHaveBeenCalled());
  });

  it("auto-replays a fresh run once, not again on returning to the Incidents tab", async () => {
    render(<App />);
    await screen.findByRole("option", { name: /S-02/ });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Run diagnosis" })); });
    expect(await screen.findByRole("button", { name: "Pause" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "User reports" }));
    fireEvent.click(screen.getByRole("tab", { name: "Incidents" }));
    await screen.findByRole("img", { name: /Message exchange/ });
    expect(screen.getByRole("button", { name: "Replay" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
  });
});
