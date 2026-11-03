import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { MapLayers } from "../api";
import { CampusMap, FLOW_NOTE } from "./CampusMap";
import type { DeviceState, Highlight } from "./highlight";

// The simulated campus_v1 topology (sample_data/topology/campus_v1.json): ids, roles and zones.
const DEVICES: [number, string, string][] = [
  [1, "core", "ZONE_DATA_CENTRE"],
  [2, "distribution", "ZONE_DATA_CENTRE"],
  [3, "distribution", "ZONE_DATA_CENTRE"],
  [4, "access", "ZONE_HOSTEL_A"],
  [5, "access", "ZONE_HOSTEL_B"],
  [6, "access", "ZONE_ACADEMIC_BLOCK"],
  [7, "access", "ZONE_LIBRARY"],
  [8, "access", "ZONE_LECTURE_HALLS"],
  [9, "access", "ZONE_DEPT_LAB"],
  [10, "access", "ZONE_ADMIN"],
];
const LINKS: [number, number][] = [[1, 2], [1, 3], [2, 3], [2, 4], [2, 5], [2, 10], [3, 6], [3, 7], [3, 9], [2, 8], [3, 8]];
const pt: [number, number] = [0, 0];
const layers = {
  crs: "x", bounds: [], banner: "", provenance_note: "", zones: [],
  devices: DEVICES.map(([n, role, zone]) => ({ id: `SW_CAMPUS_${n}`, role, zone, position: pt, core: n === 1, provenance: "p" })),
  links: LINKS.map(([a, b]) => ({ id: `L-${a}-${b}`, a: `SW_CAMPUS_${a}`, b: `SW_CAMPUS_${b}`, from: pt, to: pt, provenance: "p" })),
} as unknown as MapLayers;

/** S-02 shape: SW_CAMPUS_4 faulty, SW_CAMPUS_5 degraded, fault path 4 -> 2 -> 1. */
function s02(): Highlight {
  const devices = Object.fromEntries(DEVICES.map(([n]) => [`SW_CAMPUS_${n}`, "neutral"])) as Record<string, DeviceState>;
  devices.SW_CAMPUS_4 = "critical";
  devices.SW_CAMPUS_5 = "warning";
  devices.SW_CAMPUS_6 = "ok";
  return { status: "diagnosed", devices, links: ["L-2-4", "L-1-2"], focus: ["SW_CAMPUS_4"] };
}

const paths = (c: HTMLElement, cls: string) => c.querySelectorAll(`path.${cls}`);
const openLayers = () => fireEvent.click(screen.getByRole("button", { name: /layers/i }));
const toggle = (name: RegExp) => fireEvent.click(screen.getByRole("checkbox", { name }));

describe("CampusMap interactive network layer", () => {
  afterEach(cleanup);
  it("draws every switch with its status and role, and every topology link", () => {
    const { container } = render(<CampusMap layers={layers} highlight={s02()} variant="full" />);
    expect(paths(container, "device")).toHaveLength(10);
    expect(paths(container, "st-critical")).toHaveLength(1);
    expect(paths(container, "st-warning")).toHaveLength(1);
    expect(paths(container, "role-core")).toHaveLength(1);
    expect(paths(container, "net-link")).toHaveLength(LINKS.length);
    // Fault path: a pulsing casing on exactly the two highlighted links.
    expect(paths(container, "net-link-casing")).toHaveLength(2);
    expect(paths(container, "k-fault").length).toBeGreaterThan(0);
    // SW_CAMPUS_5's link to its distribution switch reads as degraded.
    expect(container.querySelector("path.net-link.k-degraded")).not.toBeNull();
  });

  it("animates links by default, labels the animation as illustrative, and can switch it off", () => {
    const { container } = render(<CampusMap layers={layers} highlight={s02()} variant="full" />);
    expect(paths(container, "net-flow")).toHaveLength(LINKS.length);
    openLayers();
    expect(screen.getByText(FLOW_NOTE)).toBeInTheDocument();
    toggle(/link animation/i);
    expect(paths(container, "net-flow")).toHaveLength(0);
  });

  it("filters devices by status with live counts; missing data is never counted as healthy", () => {
    const { container } = render(<CampusMap layers={layers} highlight={s02()} variant="full" />);
    openLayers();
    const count = (name: RegExp) => screen.getByRole("checkbox", { name }).closest("label")!.querySelector(".chip-n")!.textContent;
    expect(count(/^faulty/i)).toBe("1");
    expect(count(/^degraded/i)).toBe("1");
    expect(count(/^healthy/i)).toBe("1");
    expect(count(/no finding/i)).toBe("7");
    toggle(/^faulty/i);
    expect(paths(container, "st-critical")).toHaveLength(0);
    expect(paths(container, "device")).toHaveLength(9);
    // Links to a filtered-out switch stay (topology is unchanged) but dim and stop animating.
    expect(container.querySelectorAll("path.net-link.dim").length).toBeGreaterThan(0);
    toggle(/no finding/i);
    expect(paths(container, "device")).toHaveLength(2);
  });

  it("toggles switches, links and buildings layers", () => {
    const { container } = render(<CampusMap layers={layers} highlight={s02()} variant="full" />);
    const buildingsBefore = paths(container, "building-hit").length;
    expect(buildingsBefore).toBeGreaterThan(0);
    openLayers();
    toggle(/^switches/i);
    expect(paths(container, "device")).toHaveLength(0);
    toggle(/network links/i);
    expect(paths(container, "net-link")).toHaveLength(0);
    toggle(/^buildings/i);
    expect(paths(container, "building-hit")).toHaveLength(0);
    toggle(/^switches/i);
    toggle(/network links/i);
    toggle(/^buildings/i);
    expect(paths(container, "device")).toHaveLength(10);
    expect(paths(container, "building-hit")).toHaveLength(buildingsBefore);
  });

  it("shows every switch label on demand", () => {
    const { container } = render(<CampusMap layers={layers} highlight={s02()} variant="full" />);
    const labels = () => container.querySelectorAll(".leaflet-tooltip.device-label").length;
    const before = labels();
    openLayers();
    toggle(/all switch labels/i);
    expect(labels()).toBe(10);
    expect(before).toBeLessThan(10);
  });

  it("selecting a switch marks it, rings it and lights its links; clicking reports the device", () => {
    const clicked: string[] = [];
    const { container } = render(<CampusMap layers={layers} highlight={s02()} variant="full" onDeviceClick={(id) => clicked.push(id)} />);
    const sw2 = [...paths(container, "device")].find((p) => p.getAttribute("aria-label")?.startsWith("SW_CAMPUS_2,"))!;
    act(() => {
      fireEvent.click(sw2);
    });
    expect(clicked).toEqual(["SW_CAMPUS_2"]);
    expect(paths(container, "is-sel")).toHaveLength(1);
    expect(paths(container, "sel-ring")).toHaveLength(1);
    // SW_CAMPUS_2 has six links in the simulated topology.
    expect(container.querySelectorAll("path.net-link.sel")).toHaveLength(6);
  });

  it("offers Fit campus and Focus incident; Focus is disabled with no finding to fly to", () => {
    const { rerender } = render(<CampusMap layers={layers} highlight={s02()} variant="hero" />);
    expect(screen.getByRole("button", { name: /fit campus/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /focus incident/i })).toBeEnabled();
    // Clicking in jsdom (no layout) must be a safe no-op, not an error.
    fireEvent.click(screen.getByRole("button", { name: /fit campus/i }));
    fireEvent.click(screen.getByRole("button", { name: /focus incident/i }));
    rerender(<CampusMap layers={layers} highlight={null} variant="hero" />);
    expect(screen.getByRole("button", { name: /focus incident/i })).toBeDisabled();
  });

  it("closes the Layers panel on Escape and on an outside click", () => {
    render(<CampusMap layers={layers} highlight={s02()} variant="full" />);
    openLayers();
    expect(screen.getByRole("group", { name: /layers and filters/i })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("group", { name: /layers and filters/i })).toBeNull();
    openLayers();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("group", { name: /layers and filters/i })).toBeNull();
  });

  it("keeps the simulated-placement disclaimer", () => {
    render(<CampusMap layers={layers} highlight={s02()} variant="full" />);
    expect(screen.getByText(/illustrative placement/i)).toBeInTheDocument();
  });
});
