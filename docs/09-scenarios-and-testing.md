# 09 — Scenarios and Testing

> Version 0.1 · 2026-10-31 · Draft for review · Scenario data availability depends on the generator (`PENDING`, [doc 06](06-field-dictionary.md)). Expected outcomes are qualitative; numbers are set after data inspection.

## 1. What the tests must prove

1. Every row of the [traceability matrix](01-requirements-traceability.md) has at least one passing test.
2. Agents collaborate through logged, validated messages, and behave like agents (doc 03 §1).
3. Bad or partial input is handled without false health claims.
4. The system abstains when evidence is insufficient.
5. A run is reproducible from committed data and configuration.
6. The core passes with both extensions off, and with the LLM off.

## 2. Scenario catalog

**Origin of scenarios.** S-01..S-06 are the *suggested* scenarios in `SRC-1 p4 §5` (not each individually mandatory — doc 00 §6.3). The deliverable requires "normal operation and multiple network fault scenarios" (`SRC-1 p6 §7.3`). S-07 onward are team-authored variants, labelled as such, built by mutating valid generator output or authoring files in the generator's format.

| ID | Scenario | Data source | Expected outcome (qualitative) |
|---|---|---|---|
| S-01 | Normal operation | Generator | `no_fault_detected`; states what share of the scope was assessed; no false alarm |
| S-02 | Link congestion | Generator (if supported) | `diagnosed`: congestion; evidence from at least two agents; "upstream" listed as an alternative only if topology supports it |
| S-03 | Weak Wi-Fi signal | Generator, **only if wireless signal exists** | `diagnosed`: weak signal if key evidence exists; otherwise `insufficient_evidence` or scenario omitted |
| S-04 | Ethernet / interface fault | Generator | `diagnosed`: interface fault; affected devices identified |
| S-05 | DNS / DHCP failure | Generator service-level evidence, **or** optional probe data (doc 08 §3.3) | If neither exists: scenario not produced; test `T-DNS-02` proves the system never outputs a DNS/DHCP cause |
| S-06 | Interoperability failure (incompatible field names, units, schema versions, missing message information) | Generator variant, or **team-authored incompatibility** (doc 05 §6.4) | Handled per policy: aliases applied with warnings, or affected metrics not assessable; broken data is **not** misdiagnosed as a network fault |
| S-07 | Partially missing metric (some devices) | Team-authored | `READY_WITH_WARNINGS`; missing items listed; confidence ceiling lowered; missing never treated as healthy |
| S-08 | Insufficient evidence (key evidence removed) | Team-authored | `insufficient_evidence`; no single cause asserted; leading candidates named |
| S-09 | Ambiguous (two near-equal explanations) | Team-authored | Clarification attempted; if unresolved, `insufficient_evidence` with both candidates |
| S-10 | Specialist agent fails or times out (fault injection) | Team-authored | Degraded run; missing agent in limitations; ceiling lowered |
| S-11 | Topology missing | Team-authored | Scope `unknown`; no blast radius claim; diagnosis continues on telemetry |
| S-12 | Conflicting or stale measurements | Team-authored | Conflict rules applied and recorded; both explanations kept if unresolved |
| S-13 | Complaints only, telemetry normal (ext A) | Synthetic complaints + S-01 | "Reported, not technically verified"; never `diagnosed` |
| S-14 | Complaints + matching telemetry fault (ext A) | Synthetic complaints + S-02/S-04 | Trust label `corroborated`; reports shown separately from telemetry evidence |
| S-15 | Duplicate, spam and injection-style complaints (ext A) | Synthetic | Duplicates merged, spam ignored, injection text treated as data |
| S-16 | Redundant vs single-path topology failure (ext B) | Simulated topology | Blast radius distinguishes `isolated` from `degraded` |

## 3. Scenario package contract

Each scenario is a folder under `sample_data/scenarios/` containing:

- **input** — generator output, or a labelled variant (frozen and committed so tests never depend on regeneration);
- **metadata** — purpose, provenance label (`synthetic-generator` / `team-authored`), generator parameters and seed if known, mutation description for variants;
- **expected outcome** — status, cause type or none, expected affected entities (if any), minimum evidence, forbidden claims;
- **pass criteria** — assertions derived from the expected outcome.

The expected outcome is *ground truth by construction* unless the generator provides labels (`UNKNOWN`); that is stated in the metadata.

## 4. Test families

| Family | Covers |
|---|---|
| `T-SCN-nn` | End-to-end per scenario: input → report matches expected outcome |
| `T-DIAG-*` | Scoring and ranking (`T-DIAG-01`), alternatives (`T-DIAG-ALT`), confidence (`T-DIAG-CONF`), insufficient evidence (`T-DIAG-INSUF`), multi-agent contribution (`T-DIAG-MULTI`), property tests and calibration checks (`T-DIAG-CAL`, doc 08 §9) |
| `T-AGT-CONN-*`, `T-AGT-*` | Each agent stand-alone against recorded task messages |
| `T-AGT-BEHAV-*` | The 8-point agent checklist (doc 03 §1): scope respected; tool budget enforced; investigation path differs by scenario; independent finding identical with other agents absent; abstention; clarification bounded; message-only coordination; output adapts to uncertainty |
| `T-ORCH-*`, `T-ORCH-COLLAB-*` | State transitions, timeouts, retries, clarification round cap, degraded runs, collaboration |
| `T-PROTO-*` | Envelope validation; unknown fields ignored and logged; missing required fields rejected; version rules |
| `T-ING-*`, `T-ING-FIELDS-*` | Normalization, alias use, unit conversion, data-quality note, field coverage |
| `T-ERR-*`, `T-ERR-MISSING-*` | Error catalog (§5); missing ≠ healthy |
| `T-RPT-*` (`T-RPT-EVID`, `T-RPT-ACT`, `T-RPT-SCHEMA`) | Report content; official keys exact (doc 07 §8); evidence traceability |
| `T-MODE-*` | Mode refusal of unknown values; simulation banner and provenance present; no live wording |
| `T-SAFE-*`, `T-HITL-*` | No state-changing tool exists; actions simulated; approval recorded |
| `T-LOG-*` | Message and state log completeness; replay |
| `T-UI-*`, `T-UI-LABEL-*` | Dashboard views and labels (after core) |
| `T-REPRO-*` | Fresh checkout → documented run → expected output |
| `T-LLM-OFF-01` | Diagnosis fields identical with LLM disabled vs a mock provider |
| `T-ISO-01/02` | Core passes with extensions off; extension failure leaves core unchanged |
| `T-DOC-01..03` | Every field-dictionary row cites a source; no invented members or dates; status labels present |
| `T-DNS-*` | DNS/DHCP never diagnosed without evidence |
| `T-CSI-*`, `T-GEO-*` | Extensions (docs 10, 11) |

## 5. Error-handling cases

| ID | Case | Expected behaviour | Test |
|---|---|---|---|
| E-01 | Unparseable input | `REJECTED` with `INPUT_UNPARSEABLE`; failure report | T-ERR-01 |
| E-02 | Unsupported major schema version | `REJECTED` unless adapter exists | T-ERR-02 |
| E-03 | Unknown extra fields | Ignored and logged; accepted | T-ERR-03 |
| E-04 | Renamed field with a listed alias | Mapped; `FIELD_ALIAS_APPLIED` warning | T-ERR-04 |
| E-05 | Renamed field without alias | Metric `not_assessable (UNMAPPED_FIELD)`; run continues | T-ERR-05 |
| E-06 | Unit declared and different | Converted; conversion recorded | T-ERR-06 |
| E-07 | Unit missing or ambiguous | `not_assessable (UNIT_AMBIGUOUS)` | T-ERR-07 |
| E-08 | Metric missing for some entities | `READY_WITH_WARNINGS`; `not_assessable (MISSING)`; never healthy | T-ERR-MISSING-01 |
| E-09 | Timestamps missing for some records | Records flagged; if none usable, `REJECTED` | T-ERR-08 |
| E-10 | Stale data | Caveat or not assessable | T-ERR-09 |
| E-11 | Implausible values | Flagged; caveat or not assessable | T-ERR-10 |
| E-12 | Duplicate records | De-duplicated; recorded | T-ERR-11 |
| E-13 | Entity not in topology | Scope `unknown` for that entity | T-ERR-12 |
| E-14 | Topology missing | Scope `unknown`; ceiling lowered | T-ERR-13 |
| E-15 | Agent timeout / failure | Degraded run per doc 04 §5 | T-ORCH-* |
| E-16 | Invalid agent message | Rejected, logged, treated as missing | T-PROTO-* |
| E-17 | LLM unavailable or output rejected | Template fallback; diagnosis unchanged | T-LLM-OFF-01 |
| E-18 | Malformed complaint (ext A) | Stored as unparseable; excluded from clustering; counted | T-CSI-EXT-* |
| E-19 | Injection-style complaint text (ext A) | Treated as data; validated extraction; flagged | T-CSI-EXT-* |

Numeric limits (freshness, plausibility) come from config after data inspection.

## 6. Evaluation and reproducibility

- Accuracy and confidence evaluation follows the plan and calibration gate in [doc 08 §9](08-diagnosis-and-confidence.md).
- Whether the generator supports fixed seeds is `UNKNOWN`. Regardless, scenario inputs are **frozen and committed**, so a run depends only on committed data and configuration.
- A run's observable output (states, decision, score, report keys) must be identical across runs; free-text wording may differ only where an LLM is explicitly enabled.
- A test report (pass/fail per ID against the traceability matrix) is produced for the submission (doc 14).
