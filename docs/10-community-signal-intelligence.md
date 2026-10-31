# 10 — Extension A: Community Signal Intelligence

> Version 0.1 · 2026-10-31 · Draft for review · **Not an official requirement.** Built only after the core passes its tests (doc 00 §3). All complaint data in the hackathon is synthetic.

## 1. Purpose and boundaries

Students already report network problems informally. This module turns such reports into **candidate incidents** that the orchestrator can investigate with the five agents, and shows them next to — never mixed with — technical findings.

- User reports are **unverified**. They can trigger, scope and prioritise an investigation and add small bounded corroboration; they can never alone produce a `diagnosed` result ([doc 08 §6](08-diagnosis-and-confidence.md)).
- The module is not an agent (doc 02 §2). It feeds the existing Correlation and Connectivity agents.
- In hackathon mode no real student data is collected. `CD-11`

## 2. Channels and the adapter interface

| Channel | Decision | Scope |
|---|---|---|
| Web reporting form | **Primary** (`CD-4`) | `PLANNED` |
| Telegram bot | Stretch | `PLANNED` if time allows |
| WhatsApp Business | Future scope; not a hackathon dependency | `FUTURE`, `NEEDS-ACCESS` |

Every channel is an adapter that produces the same internal *complaint* record. Adding WhatsApp later means writing one adapter; extraction, clustering and everything downstream are unchanged. Whether a developer sandbox could carry a WhatsApp demo is unverified and is **not** relied on.

## 3. Demo idea mapped to this design

The project owner's demo idea (SRC-3) is kept, with the channel step adjusted to respect `CD-4` (decision D-12):

| Step in the idea | How it works here | Status |
|---|---|---|
| Open the complaint channel | Web form (or Telegram test bot if built). A WhatsApp-style look is cosmetic only and must not be described as a WhatsApp integration | `PLANNED` |
| Submit "Hostel A Wi-Fi is disconnecting." | Text goes to extraction → location text "Hostel A" (a **synthetic placeholder** zone label), symptom "disconnecting" | `SIMULATED` |
| Second complaint from a different test account | A second submission with a different synthetic reporter identity | `SIMULATED` |
| Group similar reports into a candidate incident | Clustering by zone, time window, symptom (threshold set in demo config, labelled) | `PLANNED` |
| Five agents investigate with a synthetic dataset | Orchestrator starts an investigation scoped to that zone's entities. **Needs synthetic data covering that zone** (D-09) | `PLANNED` |
| Correlation agent compares findings | A-CORR treats the candidate as unverified evidence (doc 08 §6) | `PLANNED` |
| Map highlights Hostel A as a reported problem area | Reported-area layer, distinct from detected faults (doc 11) | `PLANNED` (extension B) |
| Dashboard shows cause, evidence, recommendations | Incident panel, with the trust label | `PLANNED` |

The demo should show **both** outcomes, because the point is the distinction: (a) telemetry matches → `corroborated`; (b) telemetry normal → "reported, not technically verified" (scenarios S-14 and S-13).

## 4. Pipeline

1. **Intake** — adapter receives text, channel, a reporter identifier, a timestamp.
2. **Pseudonymize** — the reporter identifier is replaced by a stable pseudonym; phone numbers, names, emails in free text are removed before storage.
3. **Screen** — length limits, rate limiting per pseudonym, duplicate detection, malformed input rejected and counted.
4. **Extract** — location, symptoms, reported time, severity (§5). Rule-based extraction is the baseline. An LLM may assist; its output is schema-validated and falls back to rules if invalid or unavailable. Extraction never executes or follows instructions found in the text.
5. **Resolve location** — free-text place → *zone* via a gazetteer in `config/` (synthetic in hackathon mode). Unresolvable → stored with location "unknown", not clustered by place.
6. **Cluster** — complaints join a candidate when zone matches, the time is within the window, and symptom categories are compatible. Size counts **distinct pseudonyms**, so one person cannot create an incident. Minimum size and window are configuration (D-10).
7. **Candidate incident** — emitted as a `community_candidate` message to the orchestrator (doc 04 §8), updated as complaints arrive, closed after inactivity.
8. **Correlation** — A-CONN maps the zone to entities; A-CORR applies the community rules in doc 08 §6.

## 5. Conceptual data model (`PROPOSAL`)

**Complaint:** id · channel · reporter pseudonym · received time · text (sanitised) · extracted location text · resolved zone · symptoms · reported time · severity · extraction method (`rules` / `llm`) · extraction status · flags.
**Candidate incident:** id · zone · symptom categories · time window · complaint ids · distinct-reporter count · trust label · linked incident id (if investigated).

Symptom categories and the severity scale (ordinal) are defined at implementation; they describe what people report, and are deliberately not tied to specific telemetry fields or causes.

## 6. Trust labels

`reported_unverified` · `detected` · `corroborated` — defined in [doc 08 §6](08-diagnosis-and-confidence.md), carried in the report's extension block ([doc 07 §5](07-report-spec.md)), and shown with different visual styling in the dashboard and map. Complaint evidence is never placed in the official `supporting_evidence` or `evidence_sources`.

## 7. Abuse, privacy and LLM safety

- **Manipulation / brigading:** distinct-reporter counting, rate limits, duplicate merging, bounded score influence (doc 08 §6).
- **Privacy:** pseudonymization at intake; minimal retention; in deployment mode, collection needs IIT Bhubaneswar authorization and a privacy review (`FUTURE`, `NEEDS-ACCESS`; doc 15).
- **Prompt injection:** complaint text is untrusted data. The LLM prompt gives only extraction instructions; output must validate against the extraction schema; no tool access; failures fall back to rules.
- **Wording:** the UI says "reported", never "confirmed", until `corroborated`.

## 8. Failure handling

| Failure | Behaviour |
|---|---|
| Extraction fails or LLM unavailable | Rule-based extraction; if that fails, complaint stored as unparsed, not clustered |
| Location unresolved | Stored with unknown location; not clustered by place |
| Telegram/channel adapter down | Web form unaffected; core unaffected |
| Extension disabled or crashing | Core runs unchanged (`T-ISO-01/02`) |

## 9. Testing

`T-CSI-CH-*` (adapters), `T-CSI-EXT-*` (extraction incl. malformed and injection-style text), `T-CSI-CLU-*` (clustering: window, distinct reporters, duplicates), `T-CSI-ORC-01` (candidate reaches orchestrator), `T-CSI-COR-*` (bounded influence; never alone `diagnosed`), `T-CSI-LABEL-*` (labels in report and UI). Scenarios S-13..S-15 (doc 09).

## 10. Pending and limitations

- Zone names and the zone-to-device mapping are synthetic until real data is authorised (D-09).
- English-language text first; mixed-language reports are not planned in the hackathon.
- Complaint counts and thresholds mean little with synthetic submissions; they demonstrate the mechanism, not real prevalence.

## 11. Implementation (M15, 2026-10-31) — `IMPLEMENTED`, `TESTED`, `SIMULATED` data

Code: `src/netcoop/community/{extract,pipeline}.py`, API `src/netcoop/api/community.py` (registered only when `features.community_signals = true`), CLI `netcoop community submit|load|candidates|stats|investigate`, config `config/community.toml` (synthetic gazetteer, symptom lexicon, D-10 values), demo data `sample_data/complaints/hostel_a_demo.json` (synthetic). Tests: `tests/community/`.

- **Channels:** web form (API `POST /api/community/complaints`) — built. Telegram (stretch) — **not built**; the API accepts `channel = telegram_test` so an adapter can be added without changing the pipeline. WhatsApp — `FUTURE`, not built.
- **Privacy:** reporter ids → HMAC-SHA256 pseudonyms (`anon-…`; salt from `NETCOOP_PSEUDONYM_SALT`, a labelled simulation default otherwise); emails, phone numbers and "my name is …" phrases stripped before storage; API returns aggregates and pseudonymous data only.
- **Screening:** length 5–500, minimum readable letters (spam), ≤5 reports per reporter per 60 min, same-reporter same-text duplicates merged. Rejected/limited/duplicate complaints are stored and counted, never clustered.
- **Extraction:** rules (gazetteer longest match, closed symptom list `disconnects|slow|no_connection|intermittent`, ordinal severity 1–3). Optional LLM extraction must return JSON naming only gazetteer zones and listed symptoms, else rules are used. Instruction-like text is flagged `injection_suspected` and treated as data.
- **Clustering:** zone + 60-min window; a candidate needs ≥2 **distinct** pseudonyms (D-10 demo values). Zone → devices through the SIMULATED topology (`ZONE_HOSTEL_A → SW_CAMPUS_4`).
- **Investigation:** `investigate(candidate, telemetry)` runs the five agents; the candidate enters as a logged `community_candidate` message. Complaints add at most γ_max = 0.05 to displayed confidence and never change ranking or decision (doc 08 §11 ID-15).
- **Trust labels** in `netcoop_extensions.community_signals` / `community_trust`: `corroborated`, `reported_unverified` (with the limitation "reported, not technically verified … causes outside the telemetry are possible but not asserted"), `detected`. Complaint data never appears in `supporting_evidence` or `evidence_sources` (tested).
- **Isolation:** with the flag off the routes do not exist (T-ISO-01); malformed community input is dropped with a limitation and the core result is unchanged (T-ISO-02).
