import { AGENT_LABELS } from "../lib/lanes";
import { STRIP_AGENTS, type agentActivity, type AgentStatus, type useReplay } from "../lib/replay";

const STATUS_WORD: Record<AgentStatus, string> = {
  idle: "no messages yet",
  waiting: "no reply yet",
  replied: "replied",
  error: "error",
};

/**
 * The five agents that work an incident, in the order work flows through them, each with
 * its message count and a status mark taken from the trace. Holds the replay controls and
 * the toggle for the message panel below it.
 */
export function AgentStrip({
  activity,
  replay,
  messagesOpen,
  onToggleMessages,
  active = [],
}: {
  activity: ReturnType<typeof agentActivity>;
  replay: ReturnType<typeof useReplay>;
  messagesOpen: boolean;
  onToggleMessages: () => void;
  /** Agents taking part in the message the replay is on; their chips light up. */
  active?: string[];
}) {
  return (
    <div className="agent-strip" role="group" aria-label="Agents">
      <ol className="agent-chips">
        {STRIP_AGENTS.map((agent) => {
          const a = activity[agent] ?? { messages: 0, status: "idle" as const };
          const label = AGENT_LABELS[agent] ?? agent;
          const name = `${label}: ${STATUS_WORD[a.status]}, ${a.messages} message${a.messages === 1 ? "" : "s"}`;
          return (
            <li
              key={agent}
              className={`agent-chip ${a.status}${active.includes(agent) ? " active" : ""}`}
              aria-label={name}
              title={name}
            >
              <span className="agent-dot" aria-hidden="true" />
              <span className="agent-name">{label}</span>
              <span className="agent-count mono" aria-hidden="true">{a.messages}</span>
            </li>
          );
        })}
      </ol>
      <div className="strip-controls">
        {replay.playing ? (
          <button type="button" className="secondary" onClick={replay.pause}>Pause</button>
        ) : (
          <button type="button" className="secondary" onClick={replay.play}>Replay</button>
        )}
        <button type="button" className="secondary" onClick={replay.step}>Step</button>
        <button type="button" className="secondary" onClick={replay.restart}>Restart</button>
        <button
          type="button"
          className="secondary strip-toggle"
          aria-expanded={messagesOpen}
          aria-controls="message-panel"
          onClick={onToggleMessages}
        >
          Messages
        </button>
      </div>
    </div>
  );
}
