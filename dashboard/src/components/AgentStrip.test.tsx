import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { agentActivity, useReplay } from "../lib/replay";
import { AgentStrip } from "./AgentStrip";

afterEach(cleanup);

const activity: ReturnType<typeof agentActivity> = {
  performance_agent: { messages: 2, status: "error" },
  infrastructure_agent: { messages: 2, status: "replied" },
  connectivity_agent: { messages: 2, status: "replied" },
  correlation_agent: { messages: 2, status: "replied" },
  reporting_agent: { messages: 2, status: "replied" },
};
const replay = (over: Partial<ReturnType<typeof useReplay>> = {}): ReturnType<typeof useReplay> => ({
  cursor: 9, playing: false, play: vi.fn(), pause: vi.fn(), step: vi.fn(), restart: vi.fn(), ...over,
});

describe("AgentStrip", () => {
  it("renders five chips in strip order with status in the label", () => {
    render(<AgentStrip activity={activity} replay={replay()} messagesOpen onToggleMessages={() => {}} />);
    const chips = screen.getAllByRole("listitem");
    expect(chips).toHaveLength(5);
    expect(chips[0]).toHaveAccessibleName(/^Performance: error/);
    expect(screen.getByLabelText(/^Performance: error/)).toBeInTheDocument();
    expect(screen.getByLabelText("Infrastructure: replied, 2 messages")).toBeInTheDocument();
    expect(chips[4]).toHaveAccessibleName(/^Reporting/);
  });

  it("toggles the message panel and drives the replay", () => {
    const onToggle = vi.fn();
    const r = replay();
    render(<AgentStrip activity={activity} replay={r} messagesOpen onToggleMessages={onToggle} />);
    const messages = screen.getByRole("button", { name: /Messages/ });
    expect(messages).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(messages);
    expect(onToggle).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Replay" }));
    expect(r.play).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Step" }));
    expect(r.step).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Restart" }));
    expect(r.restart).toHaveBeenCalled();
  });

  it("shows Pause while playing", () => {
    const r = replay({ playing: true });
    render(<AgentStrip activity={activity} replay={r} messagesOpen={false} onToggleMessages={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(r.pause).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Messages/ })).toHaveAttribute("aria-expanded", "false");
  });
});
