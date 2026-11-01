import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DiagnosisPanel } from "./DiagnosisPanel";
import { S02_DETAIL } from "./__fixtures__/s02";

afterEach(cleanup);

describe("DiagnosisPanel", () => {
  it("shows the S-02 diagnosis, confidence, evidence and limitations without a click", () => {
    const { container } = render(
      <DiagnosisPanel id="INC-0014" detail={S02_DETAIL} review={[]} onChanged={() => {}} onReload={() => {}} />,
    );
    expect(container.querySelector(".cause")).toHaveTextContent(
      "Likely link congestion causing egress queue drops on SW_CAMPUS_4",
    );
    expect(screen.getByRole("meter", { name: "Heuristic confidence score" })).toBeInTheDocument();
    expect(container.querySelector(".meter")).toHaveTextContent("not a probability");
    expect(screen.getByRole("cell", { name: "link_utilization_pct" })).toBeInTheDocument();
    expect(screen.getByText("Fault diagnosed")).toBeInTheDocument();
    expect(screen.getByText("Root cause requires further verification by an operator.")).toBeVisible();
  });

  it("with no report shows the header and state only, without throwing", () => {
    const detail = { ...S02_DETAIL, status: null, state: "COLLECTING", report: null };
    const { container } = render(
      <DiagnosisPanel id="INC-0015" detail={detail} review={[]} onChanged={() => {}} onReload={() => {}} />,
    );
    expect(screen.getByText("Not reported yet")).toBeInTheDocument();
    expect(screen.getByText(/COLLECTING/)).toBeInTheDocument();
    expect(container.querySelector(".cause")).toBeNull();
    expect(screen.queryByRole("meter")).toBeNull();
    // Neutral wording: a failed, non-resumable run never fills in.
    expect(screen.getByText("No report for this incident yet.")).toBeInTheDocument();
    expect(screen.queryByText(/once the agents finish/)).toBeNull();
  });
});
