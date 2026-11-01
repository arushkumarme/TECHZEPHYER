import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Swimlane } from "./Swimlane";
import { S02_TRACE } from "./__fixtures__/s02";

afterEach(cleanup);

describe("Swimlane cursor", () => {
  it("draws every row, dims rows after the cursor and marks the current one", () => {
    const { container } = render(<Swimlane events={S02_TRACE} cursor={1} />);
    expect(container.querySelectorAll(".swim .arrow")).toHaveLength(4);
    expect(container.querySelectorAll(".swim .row-hit")).toHaveLength(4);
    expect(container.querySelectorAll(".swim g.pending")).toHaveLength(2);
    expect(container.querySelectorAll(".swim g.current")).toHaveLength(1);
    expect(screen.getByRole("img", { name: /^Message exchange: 4 messages/ })).toBeInTheDocument();
  });

  it("without a cursor nothing is dimmed", () => {
    const { container } = render(<Swimlane events={S02_TRACE} />);
    expect(container.querySelectorAll(".swim .pending, .swim .current")).toHaveLength(0);
  });
});
