"""In-process message bus (doc 02 C-BUS, doc 05 §8).

Every message — request or reply — is serialized to JSON, validated with
:func:`parse_message`, appended to the :class:`LogStore`, and only then delivered.
Invalid messages are logged (``valid = 0`` with the error code) and raised, never
delivered. Routing is hub-and-spoke: one side of every message must be the
orchestrator (doc 03 §3); agents cannot message each other directly.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from netcoop.core.ids import Clock, IdFactory, SystemClock
from netcoop.core.log_store import LogStore
from netcoop.core.messages import (
    Envelope,
    MessageValidationError,
    ParsedMessage,
    make_message,
    parse_message,
)
from netcoop.core.vocab import AgentId, MessageStatus, MessageType

Handler = Callable[[ParsedMessage], Envelope | str]
Listener = Callable[[ParsedMessage], None]

_HUB: AgentId = "orchestrator"


class BusRoutingError(RuntimeError):
    """A message violates the routing rules or has no destination."""


class MessageBus:
    def __init__(
        self,
        store: LogStore,
        *,
        clock: Clock | None = None,
        ids: IdFactory | None = None,
    ) -> None:
        self.store = store
        self.clock: Clock = clock or SystemClock()
        self.ids = ids or IdFactory()
        self._handlers: dict[str, Handler] = {}
        self._listeners: dict[str, Listener] = {}

    # ------------------------------------------------------------------ registration
    def register(self, agent_id: AgentId, handler: Handler) -> None:
        """Register a request handler (an agent). The handler returns its reply."""
        self._handlers[agent_id] = handler

    def register_listener(self, agent_id: AgentId, listener: Listener) -> None:
        """Register a receiver for one-way notifications (e.g. the orchestrator)."""
        self._listeners[agent_id] = listener

    # ------------------------------------------------------------------ building
    def build(
        self,
        *,
        sender: AgentId,
        recipient: AgentId,
        message_type: MessageType,
        payload: Any,
        incident_id: str | None,
        in_reply_to: str | None = None,
        status: MessageStatus = "ok",
    ) -> Envelope:
        return make_message(
            message_id=self.ids.message(),
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            payload=payload,
            sent_at=self.clock.now(),
            incident_id=incident_id,
            in_reply_to=in_reply_to,
            status=status,
        )

    def reply(
        self,
        request: ParsedMessage,
        *,
        message_type: MessageType,
        payload: Any,
        status: MessageStatus = "ok",
    ) -> Envelope:
        """Build the reply envelope for ``request`` (sender/recipient swapped)."""
        env = request.envelope
        return self.build(
            sender=env.recipient,
            recipient=env.sender,
            message_type=message_type,
            payload=payload,
            incident_id=env.incident_id,
            in_reply_to=env.message_id,
            status=status,
        )

    # ------------------------------------------------------------------ transport
    def transmit(
        self, wire: Envelope | str, *, expect_reply_to: ParsedMessage | None = None
    ) -> ParsedMessage:
        """Serialize, validate and log one message. Raises on any violation."""
        raw = wire.to_json() if isinstance(wire, Envelope) else wire
        header = _best_effort_header(raw)
        try:
            parsed = parse_message(raw)
            _check_route(parsed.envelope.sender, parsed.envelope.recipient)
            if expect_reply_to is not None:
                _check_reply(parsed, expect_reply_to)
        except MessageValidationError as exc:
            self.store.append_message(
                raw_json=raw,
                header=header,
                valid=False,
                error_code=exc.code,
                error_detail=exc.detail[:2000],
            )
            raise
        except BusRoutingError as exc:
            self.store.append_message(
                raw_json=raw,
                header=header,
                valid=False,
                error_code="MESSAGE_ROUTING_INVALID",
                error_detail=str(exc),
            )
            raise
        self.store.append_message(
            raw_json=raw,
            header=parsed.envelope.model_dump(mode="json", exclude={"payload"}),
            valid=True,
            ignored_fields=parsed.ignored_fields,
        )
        return parsed

    def request(
        self,
        *,
        sender: AgentId,
        recipient: AgentId,
        message_type: MessageType,
        payload: Any,
        incident_id: str | None,
        in_reply_to: str | None = None,
    ) -> ParsedMessage:
        """Send a request and return the validated reply from the recipient's handler."""
        _check_route(sender, recipient)
        handler = self._handlers.get(recipient)
        if handler is None:
            raise BusRoutingError(f"no handler registered for {recipient}")
        sent = self.transmit(
            self.build(
                sender=sender,
                recipient=recipient,
                message_type=message_type,
                payload=payload,
                incident_id=incident_id,
                in_reply_to=in_reply_to,
            )
        )
        return self.transmit(handler(sent), expect_reply_to=sent)

    def notify(
        self,
        *,
        sender: AgentId,
        recipient: AgentId,
        message_type: MessageType,
        payload: Any,
        incident_id: str | None,
        in_reply_to: str | None = None,
        status: MessageStatus = "ok",
    ) -> ParsedMessage:
        """Send a one-way message; delivered to a listener if one is registered."""
        parsed = self.transmit(
            self.build(
                sender=sender,
                recipient=recipient,
                message_type=message_type,
                payload=payload,
                incident_id=incident_id,
                in_reply_to=in_reply_to,
                status=status,
            )
        )
        listener = self._listeners.get(recipient)
        if listener is not None:
            listener(parsed)
        return parsed


def _check_route(sender: str, recipient: str) -> None:
    if _HUB not in (sender, recipient):
        raise BusRoutingError(
            f"{sender} -> {recipient}: agents communicate only through the orchestrator"
        )
    if sender == recipient:
        raise BusRoutingError(f"{sender} cannot message itself")


def _check_reply(reply: ParsedMessage, request: ParsedMessage) -> None:
    r, q = reply.envelope, request.envelope
    if r.in_reply_to != q.message_id:
        raise MessageValidationError(
            "MESSAGE_INVALID", f"in_reply_to {r.in_reply_to!r} does not match {q.message_id!r}"
        )
    if (r.sender, r.recipient) != (q.recipient, q.sender):
        raise MessageValidationError(
            "MESSAGE_INVALID", f"reply from {r.sender} to {r.recipient} does not answer request"
        )
    if r.incident_id != q.incident_id:
        raise MessageValidationError("MESSAGE_INVALID", "reply incident_id differs from request")


def _best_effort_header(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return {k: v for k, v in data.items() if k != "payload"} if isinstance(data, dict) else {}
