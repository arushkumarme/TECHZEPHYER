# 08 — Diagnosis and Confidence Scoring

> Version 0.1 · 2026-10-31 · Draft for review
> **The confidence number is a transparent heuristic score, not a calibrated probability** (`CD-6`). It may only be called calibrated after the validation gate in §9 is met and recorded. All parameter *values* are pending; this document fixes the structure.

`SRC-1 p5 §6`: confidence "should be based on a documented scoring method or calibrated model"; teams "should be able to report insufficient evidence when a reliable diagnosis cannot be made". `SRC-1 p2`: the system "must not claim an exact root cause when the available evidence is insufficient". `CONFIRMED`

## 1. Principles

1. Deterministic first: same evidence and parameters → same ranking, score and decision. An LLM never sets any of them (`P-15`).
2. Every score component is inspectable and traceable to observation IDs.
3. Missing is not healthy; absence of evidence lowers support but is not counted as contradiction (§7).
4. Poor data lowers the ceiling on confidence.
5. A close call is reported as a close call.
6. The output is a *probable* cause. The system never says "exact".

## 2. Pipeline

1. Ingestion produces assessed / not-assessable evidence and a data-quality note (doc 05 §6).
2. Specialist agents grade observations against baselines (severity) and attach agent-local hypotheses (doc 03).
3. A-CORR builds the hypothesis list from the catalog (§3), scores each (§4), applies conflict rules (§5), considers community evidence (§6), may ask clarifications, and applies the decision gate (§4.5).
4. A-REPT reports. Nothing after A-CORR may change the cause, score or status.

Baselines and severity thresholds are configuration, set from the actual data once it is inspected. **No numeric thresholds are proposed here.**

## 3. Hypothesis catalog

### 3.1 Catalog

Signature items are evidence *categories*; whether each exists in the data is in §3.2. "PDF" marks wording taken from `SRC-1`; "ours" marks our additions (`PROPOSAL`).

| Cause type | Origin | Signature (key evidence → supporting → contradicting) |
|---|---|---|
| Normal operation | PDF p4: "Measurements remain within expected ranges" | Key: assessed metrics within expected ranges across enough of the scope. Contradicting: any critical anomaly |
| Link congestion | PDF p4: "High utilization, elevated queue drops, and increased latency" | Key: high link utilization, elevated queue drops. Supporting: increased latency (and loss/jitter if present); ours: downstream entities affected as the topology predicts. Contradicting: low utilization; clean queues |
| Upstream congestion / upstream fault | PDF p5 example (`"Upstream link congestion"` as an alternative); ours: generalized | Key: symptoms on a downstream entity with healthy local indicators and an unhealthy or saturated upstream element. Needs topology |
| Weak Wi-Fi signal | PDF p4: "Poor signal quality and increased retransmissions" | Key: poor wireless signal measurement. Supporting: retransmissions (availability `UNKNOWN`), loss/latency on wireless entities. Contradicting: good signal; wired entities equally affected |
| Interface / Ethernet fault | PDF p4: "Rising interface errors, link instability, or packet loss" | Key: rising interface errors. Supporting: link instability, packet loss localized to the interface. Contradicting: clean error counters |
| Device overload | PDF p1 lists "device CPU overload"; signature ours | Key: high CPU utilization on the device (memory if present). Supporting: symptoms localized to traffic through it |
| Device / hardware failure | PDF p1 lists "hardware failures"; signature ours | Key: device status down or abnormal; entities behind it unreachable per topology. Contradicting: device reports healthy and reachable |
| DNS / DHCP service failure | PDF p4: "Service-specific connectivity problems" | **Cannot be specified** until service-level evidence exists — see §3.3 |
| Telemetry unreliable / incompatible | PDF p4 interoperability-failure scenario | Key: unmapped fields, ambiguous units, version mismatch, widespread not-assessable. This is a *data-problem* explanation, not a network fault, and prevents misreading broken data as a network fault |

Each signature item carries an importance class — *key*, *supporting*, or *weak* — mapped to numeric weights in `config/` (values pending, §10).

### 3.2 Evidence availability matrix — `PENDING`

For each cause type × signature item: does the generator provide the evidence? Filled after inspection of `SRC-4`; until then no hypothesis is guaranteed diagnosable. A cause type whose key evidence is unavailable is marked *not diagnosable* and is never output as a root cause.

### 3.3 DNS/DHCP — evidence-dependent (`CD-9`)

- **Gap (`OBSERVED` from `SRC-1` only):** the dataset category list (`p4 §5`) has no DNS/DHCP signal, yet one suggested scenario concerns it. Whether the generator supplies any is `UNKNOWN`.
- **If the generator provides service-level evidence:** it is added to §3.1 with its real field names, and §3.2 is updated.
- **If it does not:** the system will not diagnose DNS/DHCP. It may state as a limitation that DNS/DHCP failure cannot be assessed with the supplied telemetry, and recommend collecting service checks. Scenario S-05 is then not produced from generator data (doc 09).
- **Optional probe interface (`PROPOSAL`, not a dataset capability):** an *additional, separately labelled* input type that carries the results of service checks — for each check: where it ran from, which service (DNS or DHCP), the outcome (success, failure, timeout), response time if any, and timestamp. Field names would be defined in doc 06 when adopted. Probe data is **team-authored** unless collected from a real authorized test environment; reports and UI must label it as probe data, never as generator telemetry. In deployment mode the interface could receive real checks (`FUTURE`, `NEEDS-ACCESS`). Decision D-11.

## 4. Scoring

### 4.1 Inputs

For hypothesis *h*: signature items *i* with weights *w_i*; contradicting items *j* with weights *v_j*; the strength of available evidence *e_i* in [0, 1] for each signature item (0 if absent **or not assessable**; graded by severity: normal → 0, elevated → a mid value, critical → 1; values from config); strength *c_j* of any contradicting evidence; the data-quality ceiling from §4.3.

### 4.2 Hypothesis score

```
Support        S_h  = Σ ( w_i · e_i ) / Σ w_i        # denominator includes ALL signature items, even not-assessable ones
Contradiction  C_h  = min( 1, Σ ( v_j · c_j ) )
Corroboration  B_h  = β  if at least 2 independent sources support h, else 0
Base_h              = clamp( S_h − λ · C_h + B_h , 0 , 1 )
Score_h             = min( Base_h , Q_cap )
```

- Because not-assessable items stay in the denominator, missing evidence can never raise a score.
- "Independent" means different agents relying on different underlying metric categories. Two agents reading the same raw metric do not count twice.
- The topology-consistency check (do the entities actually affected match what A-CONN predicts for *h*?) enters as a signature item for cause types that have a topology implication.

### 4.3 Data-quality ceiling

```
Q     = combination of completeness, freshness, consistency  (from the data-quality note)
Q_cap = a banded lookup of Q → maximum allowed score
```

A missing topology or missing specialist lowers the ceiling further (doc 04 §5). The ceiling can make a diagnosis impossible (§4.5 requires *Score ≥ τ_diag*).

### 4.4 Margin and ambiguity

```
margin m = Score_(top) − Score_(second)
```

If *m* < δ the result is ambiguous: both candidates are reported and neither is claimed. A-CORR first tries a clarification (what-if from A-CONN, re-check from a specialist) before settling on ambiguous.

### 4.5 Decision gate

`diagnosed` only if **all** hold; otherwise `insufficient_evidence`:

1. Score_(top) ≥ τ_diag;
2. at least *n_min* distinct signature items have supporting evidence;
3. at least *s_min* independent technical sources support it;
4. margin *m* ≥ δ;
5. the top hypothesis is not "telemetry unreliable".

Special case: if "normal operation" is top with assessed coverage ≥ *coverage_min* → `no_fault_detected`.
Community evidence is **excluded** from conditions 2 and 3 (§6).

### 4.6 Reported confidence

- `confidence` (official key) = Score_(top) when diagnosed; min(Score_(top), *c_insuff_cap*) when insufficient (D-04).
- `confidence_category` = high / medium / low by thresholds *t_high*, *t_med*; `insufficient` when the gate fails.
- `confidence_method` = `heuristic` until §9 is met.

### 4.7 Illustrative toy example — not data

Invented numbers, only to show the arithmetic; real weights are not decided.

Congestion hypothesis with three key items: utilization (w = 3), queue drops (w = 3), latency (w = 2); Σw = 8. Utilization is critical (e = 1); queue drops elevated (e = 0.5); latency is **not assessable** (e = 0). Utilization is seen by A-PERF, queue drops by A-INFRA → independent, so β = 0.1. No contradictions. Q_cap = 0.8.

```
S = (3·1 + 3·0.5 + 2·0) / 8 = 0.5625
Base = 0.5625 + 0.1 = 0.6625  →  Score = min(0.6625, 0.8) = 0.66
```

If latency had been assessed and critical: S = 0.8125, Base = 0.9125, capped at 0.8. Missing data therefore lowered the score from 0.8 to 0.66, which is the intended behaviour.

## 5. Conflict resolution

Applied in order by A-CORR; each application is logged in the extension block (`conflicts`).

1. **Evidence class:** direct measurement > derived or inferred > user report.
2. **Freshness:** a newer observation beats an older one when the difference exceeds a configured tolerance.
3. **Topology consistency:** an explanation consistent with the dependency structure beats one that is not.
4. **Unresolved:** keep both explanations as ranked candidates, lower the score via the margin rule, and say so in `limitations`.
5. **Never** discard a specialist's finding silently; a disregarded observation is listed with the reason.

**In the protocol (1.2):** an unresolved observation conflict is now raised as a `conflict_report` (type `observation_contradiction`, reason `CONFLICTING_READINGS`, proposed rule `unresolved`) and the party's re-check comes back as a `conflict_response`. The decision carries a `conflict_trail`: each conflict with the rule applied and status `resolved` or `unresolved_preserved` (both sides' observation ids kept). Only hypothesis relations `competes`/`contradicts` are conflicts; `compatible`/`refines` never are. See doc 05 §19.

## 6. Community signals (`X-CSI-07`)

Complaints are *unverified* evidence from non-expert people. Treatment:

- They may **trigger** an investigation, **scope** it (reported zone → entities via A-CONN), and **raise priority**.
- They may add a small bounded term *B_comm* to a hypothesis's score — only if its affected entities map to the reported zone and the times overlap. *B_comm* is capped by *γ_max* and is excluded from the gate conditions in §4.5, so complaints can never alone produce `diagnosed`.
- They never appear in `supporting_evidence` or `evidence_sources`.
- Outcomes carry a trust label in the extension block:
  - `reported_unverified` — complaints, no supporting telemetry;
  - `detected` — telemetry evidence, no matching complaints;
  - `corroborated` — both, matching in place and time.
- Many complaints with normal telemetry produce "reported, not technically verified"; the report notes possible causes outside the telemetry (a monitoring gap or a non-network cause) without asserting one.

## 7. Missing-data semantics

| Situation | Treatment |
|---|---|
| Metric absent for an entity | `not_assessable (MISSING)`; contributes 0 to support; stays in denominator; listed under `missing_expected_evidence` |
| Whole agent missing | Its signature items are not assessable; confidence ceiling lowered |
| Metric within range | Counts as evidence of normality only if assessed |
| Device with no status | Observation "status unknown" — never healthy |
| Entity not in topology | Scope `unknown`; no blast-radius claim |

"Normal operation" needs assessed evidence of normality over enough of the scope (*coverage_min*).

## 8. Limitations (to be stated in the project README and demo)

- The score is an ordinal heuristic. 0.8 does not mean "right 80% of the time".
- Weights and thresholds are chosen by the team; the ranking is sensitive to them (tested in §9).
- Synthetic data only; success on it does not show real-world accuracy.
- **Circularity risk:** if catalog rules mirror the generator's own fault logic, high scores prove consistency, not diagnostic skill. Mitigation: include team-authored variants and ambiguous cases the rules were not tuned on.
- Correlated metrics can overstate support; independence handling is a partial mitigation.
- Faults outside the catalog are not diagnosable; they should produce `insufficient_evidence`, not a wrong cause.
- The topology may be simulated; structural conclusions inherit that limit.
- Community evidence is noisy and potentially manipulable.

## 9. Validation plan and the calibration gate

- **Ground truth:** `UNKNOWN` whether the generator labels the true cause. If not, scenario ground truth is defined by construction and documented as such (doc 09).
- **Metrics:** top-1 correct cause on fault scenarios; correct `insufficient_evidence` rate on starved or ambiguous scenarios; false-diagnosis rate (diagnosed but wrong); stability of decisions under ± changes to weights.
- **Property tests:** removing evidence never raises a score; adding contradicting evidence never raises a score; marking an item not-assessable never raises it; community evidence never changes `diagnosed` status alone.
- **Reliability table:** bin scores against correctness. Meaningful only with enough independent scenarios.
- **Gate for the word "calibrated":** the report, UI and docs may use it only after (a) ground truth exists for an agreed number of independent scenarios not used to set parameters, and (b) the reliability table meets a tolerance fixed *before* looking at results. Until both are recorded here, the label stays `heuristic`. Criteria values `PENDING`.

## 10. Parameter register

All values live in `config/`, are `PENDING`, and are set and justified at implementation. Any change is recorded here.

| Parameter | Meaning |
|---|---|
| `w_i`, `v_j` | Importance weights per signature / contradicting item (class → number) |
| `e_mid` | Evidence strength for an "elevated" severity |
| `β` | Corroboration bonus |
| `λ` | Contradiction penalty weight |
| `Q_cap` bands | Data-quality → score ceiling |
| `τ_diag` | Minimum score to diagnose |
| `n_min`, `s_min` | Minimum distinct signature items / independent sources |
| `δ` | Minimum margin over the runner-up |
| `coverage_min` | Assessed coverage needed to call "no fault" |
| `c_insuff_cap` | Ceiling for confidence when insufficient |
| `t_high`, `t_med` | Category thresholds |
| `γ_max` | Cap on the community corroboration term |
| Freshness tolerance | Age beyond which data is stale |
| Clarification rounds / tool budget | Limits from doc 03 §3 |

## 11. Implementation (M5, 2026-10-31) — `IMPLEMENTED`, `TESTED`, still `heuristic`

Code: `src/netcoop/diagnosis/` (`catalog`, `severity`, `evidence`, `scoring`, `params`); values: [`config/diagnosis.toml`](../config/diagnosis.toml) (every value with its basis); tests: `tests/diagnosis/test_scoring.py`.

**Parameter values (§10 register filled).** Severity thresholds: *elevated* starts just above the generator's `normal`-profile maximum; *critical* is a team-chosen level (ID-05). Weights key/supporting/weak = 3/2/1; contradiction strong/moderate = 1/0.5; e_mid 0.5; λ 0.5; β 0.1; γ_max 0.05; Q_cap bands ≥0.85→0.95, ≥0.70→0.85, ≥0.50→0.70, ≥0.30→0.50, else 0.30; missing topology −0.10; each missing agent −0.15; τ_diag 0.55; n_min 2; s_min 2; δ 0.10; coverage_min 0.60; c_insuff_cap 0.40; t_high 0.75; t_med 0.55; freshness tolerance 300 s. **All are heuristic; tuned against the same generator that produces the test data (circularity, §8).**

**Refinements found necessary while testing** (each was a failing test first):

| ID | Change | Why |
|---|---|---|
| ID-11 | **Unexplained-anomaly penalty** `− μ·U_h` (μ = 0.5): U_h = share of the entity's abnormal items that h's signature does not explain | The generator's `hardware_failure` profile drives every metric to critical; support alone scores congestion, overload, interface fault and device failure all ≈ 1. Parsimony separates them |
| ID-12 | **Margin uses `base`** (before the ceiling) | Two strong candidates both capped at Q_cap would otherwise look tied |
| ID-13 | **Key evidence required** (gate check `key_evidence_present`) and a cause is only a candidate for an entity showing at least one abnormal symptom it predicts | Without this, "local utilization normal" alone made every healthy device an upstream-congestion candidate |
| ID-14 | **`no_fault_detected` also requires no abnormal assessed measurement** (`no_abnormal_measurements`); failed probes count as abnormal | PDF p4: normal = "measurements remain within expected ranges"; a single elevated reading previously yielded "no fault" |
| ID-15 | **Community term excluded from ranking and from every gate condition**; `community_bonus` records the increment actually applied | A 0.05 bonus could lift a 0.50 score to the 0.55 threshold — violating "complaints can never alone produce diagnosed". Property test now asserts the decision *and* gate checks are identical with and without complaints |

**Behaviour on the generator's own profiles (unit level, synthetic severities):** `normal` → `no_fault_detected`; `latency_spike` → link congestion is the top cause; `hardware_failure` → device/hardware failure, with interface fault among the alternatives. Weak Wi-Fi is never output (no wireless data); DNS/DHCP is diagnosable only when probe data is supplied.

**ID-16 (M7).** Per-cause hypotheses are now *grouped*: devices whose scores are within δ of a group leader share one hypothesis, and every further group becomes its own hypothesis. Previously only the best group was kept, which hid a weaker same-cause problem on another device (found when a hardware failure on one device masked congestion on another).
