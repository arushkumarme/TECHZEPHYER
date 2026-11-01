import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CAMPUS_FEATURES } from "./features";
import { MapLists } from "./MapLists";
import { placeDevices } from "./placement";

const zones = [
  "ZONE_DATA_CENTRE", "ZONE_DATA_CENTRE", "ZONE_DATA_CENTRE", "ZONE_HOSTEL_A", "ZONE_HOSTEL_B",
  "ZONE_ACADEMIC_BLOCK", "ZONE_LIBRARY", "ZONE_LECTURE_HALLS", "ZONE_DEPT_LAB", "ZONE_ADMIN",
];
const { placed } = placeDevices(
  zones.map((zone, i) => ({
    id: `SW_CAMPUS_${i + 1}`, role: i === 0 ? "core" : i < 3 ? "distribution" : "access", zone,
    position: [0, 0] as [number, number], core: i === 0, provenance: "SIMULATED",
  })),
);

afterEach(cleanup);

describe("MapLists", () => {
  it("lists every placed switch and all 19 buildings as buttons", () => {
    render(<MapLists devices={placed} onDevice={() => {}} onBuilding={() => {}} />);
    const switches = within(screen.getByRole("list", { name: "Switches" })).getAllByRole("button");
    expect(switches.map((b) => b.textContent)).toEqual(
      expect.arrayContaining(placed.map((d) => expect.stringContaining(d.id))),
    );
    expect(switches).toHaveLength(10);
    const buildings = within(screen.getByRole("list", { name: "Buildings" })).getAllByRole("button");
    expect(buildings).toHaveLength(19);
    for (const f of CAMPUS_FEATURES) expect(screen.getByRole("button", { name: f.name })).toBeInTheDocument();
  });

  it("activating an item asks the map to open that switch or building", () => {
    const onDevice = vi.fn();
    const onBuilding = vi.fn();
    render(<MapLists devices={placed} onDevice={onDevice} onBuilding={onBuilding} />);
    fireEvent.click(screen.getByRole("button", { name: /SW_CAMPUS_4/ }));
    expect(onDevice).toHaveBeenCalledWith("SW_CAMPUS_4");
    fireEvent.click(screen.getByRole("button", { name: "Mahanadi Hall of Residence" }));
    expect(onBuilding).toHaveBeenCalledWith("mhr");
  });
});
