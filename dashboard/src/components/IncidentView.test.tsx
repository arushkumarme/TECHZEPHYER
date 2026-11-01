import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { S02_DETAIL, S02_TRACE } from "./__fixtures__/s02";

vi.mock("../api", () => ({
  api: {
    incident: vi.fn(async () => S02_DETAIL),
    trace: vi.fn(async () => ({ events: S02_TRACE })),
    review: vi.fn(async () => []),
    overlay: vi.fn(async () => { throw new Error("overlay must not be fetched with the layer off"); }),
  },
}));

import { api } from "../api";
import { IncidentView } from "./IncidentView";

afterEach(cleanup);

describe("IncidentView with the geospatial feature off", () => {
  it("shows the artwork notice, the diagnosis and the message exchange", async () => {
    const { container } = render(<IncidentView id="INC-0014" onChanged={() => {}} layers={null} autoReplay={false} />);
    expect(await screen.findByText(/Network layer off/)).toBeInTheDocument();
    expect(container.querySelector(".cause")).toHaveTextContent(
      "Likely link congestion causing egress queue drops on SW_CAMPUS_4",
    );
    expect(screen.getByRole("img", { name: /Message exchange/ })).toBeInTheDocument();
    expect(container.querySelectorAll(".swim .arrow").length).toBe(S02_TRACE.length);
    expect(container.querySelectorAll(".swim .pending").length).toBe(0);
    expect(api.overlay).not.toHaveBeenCalled();
  });
});
