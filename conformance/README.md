# NetCoop protocol conformance kit

This kit lets you check in about two minutes that the NetCoop agent protocol is real and enforced. It contains formal schemas, valid examples, invalid examples with the expected rejection reason, and one command that runs every example through the real parser and conversation guard. All values are **illustrative and simulated**; they are not measurements of any network. Full specification: [`docs/05-protocol-spec.md`](../docs/05-protocol-spec.md).

## Run it

```bash
uv run netcoop conformance            # or: uv run python -m netcoop.cli.conformance
uv run netcoop validate FILE.json     # or: uv run python -m netcoop.cli.validate FILE.json
```

`conformance` prints how many valid examples were accepted, how many invalid ones were rejected **with the expected error code**, how many conversations behaved as expected, and the plain-English reason for every rejection. It exits 1 if anything differs from `manifest.json`. `validate` checks one message, or one conversation (a file with `steps`), and explains any rejection.

## What is here

| Path | Content |
|---|---|
| `schemas/` | JSON Schemas generated from the models: `envelope`, one per payload type, and `official_report` (the ten keys). Each schema states its protocol version. |
| `vocabularies.json` | Every controlled vocabulary: terms, definitions, status and units. |
| `examples/valid/` | One valid message per type, plus variants: a not-assessable item, an abstention, an answered and an unanswered clarification, a recommendation, a 1.0 message, a conflict report, a conflict response and a decision with a conflict trail (1.2). |
| `examples/invalid/` | Single-message failures, each with its expected error code in the manifest. |
| `examples/conversations/` | Message sequences that break a conversation rule (expected code and the index of the failing message), plus one fully valid incident, one valid real conflict, and one compatible disagreement that must raise no conflict (1.2). |
| `manifest.json` | For every example: path, description, expected verdict, expected code. |

## Writing an agent against the protocol

1. **Envelope.** Every message is a JSON object with these fields: `protocol_version` (`"1.2"`; 1.x is accepted), `message_id`, `incident_id`, `in_reply_to` (the id of the message you answer), `sender`, `recipient`, `message_type`, `sent_at` (ISO time **with timezone**), `payload_schema_version` (`"1.0"`), `status` (`ok` / `partial` / `error`) and `payload`. Optional fields are `snapshot_id`, `mode` (only `simulation`) and `data_provenance`. Echo these from the task you received. Unknown fields are ignored and reported.
2. **Talk only to the orchestrator.** Hub and spoke: you receive a `task_request` and reply to it (`in_reply_to` = its `message_id`). A specialist (`performance_agent`, `infrastructure_agent`, `connectivity_agent`) replies with one `finding`, or with an `agent_error`. Only `correlation_agent` sends a `decision` or a `clarification_request`, and only `reporting_agent` sends `report_ready`.
3. **A finding** contains `observations`, `hypotheses`, `not_assessable`, `limitations`, `tool_calls`, and `self_assessment` {`assessed_fraction`, `budget_exhausted`}. Echo the task's `task_id`.
4. **Observations** use metric names from the field dictionary (e.g. `latency_ms` with unit `millisecond`), `severity` (`normal` / `elevated` / `critical` / `unknown`) and `assessability`. **Missing data is not healthy data:** a `not_assessable` observation has `value: null`, `severity: "unknown"` and a `not_assessable_reason` (e.g. `MISSING`).
5. **Hypotheses** cite evidence: `supporting` evidence refs (`evidence_type` `observation`, an `OBS-` id, `stance` `supports`) or `missing_expected_evidence`. `local_score` is in 0..1 with `score_method: "agent_local_heuristic"`; `calibrated` is rejected.
6. **Use the vocabulary terms** in `vocabularies.json` for every controlled field (cause types, reasons, units, …). An unknown term is rejected with `UNKNOWN_TERM` and closest-match suggestions.
7. **Recommendations** are always `simulated: true` and `requires_human_approval: true`.

To prove an agent conforms, call `netcoop.conformance.assert_agent_conforms(agent, recorded_task_request)`. It feeds the task to your callable and checks that the reply is valid and accepted by the conversation guard (see `tests/conformance/test_kit.py`).

**Conflicts (1.2).** Only `correlation_agent` sends a `conflict_report`; it must name a real conflict (relation `competes` or `contradicts`, never `compatible`/`refines`) and its `target` must be a party. Only that party answers, with a `conflict_response` whose `stance` is `maintain`, `revise`, `withdraw` or `cannot_assess`. Conflict reports count toward the clarification round limit. Details: doc 05 §19.
