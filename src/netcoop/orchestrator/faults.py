"""Fault injection for degraded-operation scenarios (S-10) and tests.

Faults are explicit and named; they never run unless requested. Each wraps an agent's
real handler:

* ``timeout`` — the agent answers only after ``delay_s`` (beyond its deadline);
* ``error``   — the agent reports ``AGENT_FAILED`` via an ``agent_error`` reply;
* ``invalid`` — the agent replies with a message that violates the protocol.
"""

from __future__ import annotations

import time
from typing import Literal

from netcoop.core.bus import Handler, MessageBus
from netcoop.core.messages import AgentError, Envelope, ParsedMessage

Fault = Literal["timeout", "error", "invalid"]
FAULTS: tuple[str, ...] = ("timeout", "error", "invalid")


def inject(handler: Handler, fault: str, bus: MessageBus, *, delay_s: float) -> Handler:
    if fault not in FAULTS:
        raise ValueError(f"unknown fault {fault!r}; expected one of {FAULTS}")

    def wrapped(msg: ParsedMessage) -> Envelope | str:
        if fault == "timeout":
            time.sleep(delay_s)
            return handler(msg)
        if fault == "error":
            return bus.reply(
                msg,
                message_type="agent_error",
                payload=AgentError(
                    code="AGENT_FAILED", message="injected fault (simulation)", recoverable=True
                ),
                status="error",
            )
        return '{"protocol_version": "1.0", "injected": "malformed message"}'

    return wrapped
