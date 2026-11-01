# Campus network dashboard: frontend redesign

Date: 2026-11-01 · Owner: arushkumarme · Scope: `dashboard/` only

## 1. Intent

Hackathon judges must understand NetCoop AI within 30 seconds, and the dashboard should look like a product built by a professional team. Today it is a light, document-like page: correct, but plain. The redesign makes the **IIT Bhubaneswar campus map, with the simulated network drawn on it,** the centre of the screen. A judge sees *where* the fault is, *what* the agents concluded, and *how* they got there, in that order.

**Success:** someone who has never seen the project can say "five AI agents looked at the campus network, found congestion on this switch in this hall, and here is why", after one scenario run, without reading a paragraph.

## 2. Goals, non-goals, anti-goals

**Goals**
- Layout A (owner's choice): campus map as the hero, a compact diagnosis panel on the right, the five-agent strip at the bottom.
- Interactive 2D campus map built from the owner's research package. Buildings, switches and links are clickable. The selected incident highlights its devices and paths.
- Clear visual states for each report status (§6).
- An agent strip plus a detailed message view, built from the real trace, with a step-by-step replay.
- Frontend-only "future complaints" layer: report markers, clusters and a per-building summary, built from clearly labelled sample data, with components shaped so a backend can be plugged in later.
- A restrained dark visual system, consistent across every tab.

**Non-goals**
- No backend, API, database, schema or diagnosis-logic change. No complaint backend, WhatsApp integration or complaint processing.
- No new chart types and no KPI tiles.
- No new npm dependencies (Leaflet, React and the two installed font packages are enough).

**Anti-goals (these would be failures even if everything works)**
- Fake numbers: invented telemetry, counters, uptime, "live" feeds or "real-time monitoring". Every number on screen comes from the API, or sits inside the labelled sample-data layer.
- Implying real switch locations without a visible "illustrative placement" label.
- Glow, gradients, glassmorphism and decorative motion that carry no meaning.
- Losing any existing feature: scenario runs, simulated agent failure, approvals, pause/resume, community reports and investigation, map layers, blast radius.

## 3. Constraints

- The project rules in `CLAUDE.md` apply: simulated data, no "live" or "real-time", confidence is a heuristic score and never "calibrated", missing data is never shown as healthy.
- The existing gates must stay green: `npm --prefix dashboard run build`, `npm --prefix dashboard test`, `uv run pytest -q`, and the 7 browser tests (`uv run pytest -m ui -q`, `tests/ui/test_dashboard_e2e.py`). Those tests pin roles, labels and class names: the `note` banner, the tab names, `Scenario` / `Failure` labels, the `Run diagnosis` button, the `meter` "Heuristic confidence score" containing "not a probability", the `img` "Message exchange" with `.swim .arrow`, `.row-hit` and `.swim-detail`, `Approve` buttons, the reviewer-name label, `.outcome`, the "No finding from performance_agent" text, the community-form labels and `.notice`, and on the Campus map tab `.leaflet-container`, the API provenance text "Team-authored SCHEMATIC layout", the `Show incident` select, at least 20 `path.leaflet-interactive`, and the `Map legend` label. **Keep these hooks.** If a test must change, list it and the reason before changing it.
- The campus artwork is the owner's package at `TECHZEPHYER/design-references/iitbbs-campus-map-research-package/`. It is diagrammatic and not to scale. Its own notes say it does not place switches.

## 4. Decisions made with the owner

1. **Layout A**: network map first, diagnosis right, agents bottom.
2. **Labelled demo placement**: each simulated topology zone is assigned to a real campus building in one small frontend table. Switches and links are drawn at those buildings, with a permanent label: "Simulated network, illustrative placement, not real switch locations." Record this as decision **D-26 (PROVISIONAL)** in docs/00 §7, and add a note to doc 11 saying it refines D-08 / ID-17 for the dashboard only. The backend's schematic layout remains unchanged.
3. **No real-time framing**: the page says "Simulated data · scenario playback". The sense of activity comes from replaying the recorded messages.
4. **Frontend-only complaint layer** with labelled sample data; the existing "User reports" tab and its backend flow stay as they are.

## 5. Screens

### 5.1 Shell (all tabs)
- A top bar with the NetCoop AI wordmark, the tabs (Incidents, Campus map, User reports; map and reports appear only when the API's feature flags are on, as today), a "Simulated data · scenario playback" pill, and the run controls (scenario select, "Simulate an agent failure" disclosure, `Run diagnosis`).
- The existing `role="note"` simulation banner stays, restyled as a slim line under the top bar.
- A narrow left rail lists incidents (id, scenario, status tag, top cause). It collapses to icons below 1200 px.

### 5.2 Incidents tab (Layout A)
- **Centre: the campus map** (§7), filling the space. With no incident selected, all switches are neutral and a one-line hint says "Run a scenario to start".
- **Right: the diagnosis panel** (about 380 px wide, scrolls on its own). In order: incident id, status tag and state; the root-cause sentence; the confidence meter with its threshold tick and the "heuristic score, not a probability" note; supporting evidence (metric, value, interpretation); "Also considered" (alternative causes); recommended actions with reviewer name, Approve and Reject, and the simulated outcome; "What could not be assessed" and the limitations, collapsed by default and one click away. Resume stays where it is today for paused incidents.
- **Bottom: the agent strip.** Five agents (Performance, Infrastructure, Connectivity, Correlation, Reporting), each with its message count and a status dot from the trace: replied, error or rejected, no reply. Plus "Replay" and a "Messages" toggle. Below the strip sits the message panel with the restyled sequence diagram (`Swimlane`) and its detail pane. It is **always mounted**, and it is **open by default** whenever an incident is selected. The toggle collapses it, and the page scrolls to reach it. (Builder-check call: this keeps the browser tests unchanged, because they expect the exchange to be visible right after a run.)

### 5.2a When the geospatial feature is off
`/api/geo/*` is not registered by default (`geospatial` is off in `config/netcoop.toml`). The Incidents tab still shows the campus artwork, with no switches and a quiet notice: "Network layer off. Start the backend with `NETCOOP_ENABLE=community_signals,geospatial` (doc 13)." The diagnosis panel and the agent strip work as normal. The documented demo command (doc 13, README) already enables both flags, so judges see the full map. No config default changes.

### 5.3 Campus map tab
The same map component, full width, with its layer controls: the `Show incident` select, layer toggles (network, user-report areas from the API, blast radius, sample complaints), the legend (`Map legend`), and an "About this data" footer. The footer shows the API's provenance note verbatim plus the placement note. The blast radius and corroboration shown today stay.

### 5.4 User reports tab
Restyled only. The form, candidate table and Investigate flow are unchanged.

## 6. Visual states

| Report status | Map | Panel tag | Meaning shown |
|---|---|---|---|
| `no_fault_detected` | all switches neutral or healthy | green "No fault" | "Agents found no fault" |
| `diagnosed` | affected devices red, ring pulses once; path to core highlighted; blast-radius `degraded` devices amber | red "Fault diagnosed" | cause + confidence |
| `insufficient_evidence` | `affected_devices`, or if empty the leading hypothesis's devices (`netcoop_extensions.hypotheses[0].entities`, real report data, typed in `api.ts`), amber with a **dashed** outline; none when both are empty | amber "Needs more evidence" | the leading candidate and why the gate was not met |
| `failed` | no highlight | grey "Run failed" | the error |

Devices listed as not assessable get a hollow marker, never green. Colour is never the only signal: tags carry text, and dashed versus solid outlines distinguish the amber states.

## 7. Campus map

- **Rendering:** Leaflet with `CRS.Simple`. The base layer is the package's SVG **cropped to the map area** (drop its title and right-hand info panels; viewBox about `48 155 1255 1010`), served as a static asset from `dashboard/public/`. Network, report and highlight layers are Leaflet vector layers, so pan, zoom and clicks work and the existing test hooks remain.
- **Buildings:** clickable hit areas at the package's `features[].position_xy`. A click opens a small popover with the building name, its category, the switches placed there (if any) and, when the sample layer is on, its sample report summary.
- **Placement table** (`dashboard/src/campus/placement.ts`, the only place zone→building is decided; D-26):

| Topology zone | Switches | Campus building |
|---|---|---|
| ZONE_DATA_CENTRE | SW_CAMPUS_1 (core), 2, 3 (distribution) | Administrative Building (three markers offset around it) |
| ZONE_HOSTEL_A | SW_CAMPUS_4 | MHR (Mahanadi Hall) |
| ZONE_HOSTEL_B | SW_CAMPUS_5 | BHR (Brahmaputra Hall) |
| ZONE_ADMIN | SW_CAMPUS_10 | SAC (Student Activity Centre) |
| ZONE_LECTURE_HALLS | SW_CAMPUS_8 | LHC |
| ZONE_ACADEMIC_BLOCK | SW_CAMPUS_6 | SBS |
| ZONE_LIBRARY | SW_CAMPUS_7 | SECS |
| ZONE_DEPT_LAB | SW_CAMPUS_9 | SIF |

  Switch IDs, roles, zones and links come **only** from `/api/geo/layers`; the table only maps zones to drawing positions. A zone missing from the table is listed in the legend as "not placed" and is never silently dropped.
- **Links** are drawn as gently curved lines between placed switches. When an incident is selected, the shortest path from each affected device to the core is highlighted. The path is computed in the frontend over the API's links (breadth-first search; no new topology).
- **Switch markers** are small, with the role shown by size (core > distribution > access) and the state colour from §6. Clicking a switch shows its id, role, zone, building and, for the selected incident, its evidence rows and blast-radius class.

## 8. Agent workflow and replay

- Data comes from `/api/incidents/{id}/trace` (real events). Nothing is synthesised.
- **Every arrow is in the DOM from the start.** Replay only restyles: arrows not yet reached are dimmed, the current one is emphasised. `.swim .arrow`, `.arrow.error` and `.row-hit` therefore exist immediately (browser tests).
- **Replay** steps through the trace in `seq` order, about 450 ms per message (respecting `prefers-reduced-motion`, which shows everything at once). For each message, the sender's and recipient's chips in the strip light up, the swimlane arrow draws, and, when the message's trace `summary` names a device (in practice `decision` and `clarification_*` messages; `finding` summaries hold only counts), that switch pulses on the map. Specialist findings light up their agent chip, not the map. No API change: the trace returns summaries, not payloads, and that is accepted. Pause, step and restart controls are available. After a fresh `Run diagnosis` the replay starts automatically once.

## 9. Future complaint layer (frontend only)

- `dashboard/src/complaints/types.ts` defines `ComplaintMarker { id, buildingId, category, text, reportedAt }` and `ComplaintCluster { buildingId, count, categories }`.
- `ComplaintSource` is an interface with `list(): Promise<ComplaintMarker[]>`. Today's implementation is `sampleComplaintSource` (about 15 hand-written demo reports across 4–5 buildings, in `sample.ts`). A later backend implements the same interface; no UI change is needed.
- On the map, markers cluster per building as a count badge. Clicking a building shows the summary: count by category and the three most recent sample texts.
- **Labelling:** the layer is off by default. Its toggle reads "Sample reports (demo data)"; every badge and popover carries "SAMPLE"; the legend says "Illustrative demo data, not real reports". These never feed diagnosis.

## 10. Visual system

- **Colour:** background `#0a0e13`, panels `#10161d`, hairlines `#1d2630`, text `#e6edf3`, muted `#8592a0`; one accent blue `#5b9bff` for interaction and selection; status colours only for state: ok `#46b98a`, warning `#e0a43c`, critical `#e5605a`. The map artwork is recoloured toward this palette with a CSS filter or by editing the copied SVG's fills (builder's choice). No gradients beyond what the artwork has.
- **Type:** Atkinson Hyperlegible for UI and IBM Plex Mono for ids, metrics and values (both already installed). Scale: 11 / 12 / 13 / 15 / 20 px; uppercase 10 px labels with letter spacing for section headers.
- **Spacing:** 4 px grid; panels have 12–16 px padding, 8 px radius and 1 px borders; no drop shadows except the popovers.
- **Motion:** only for state changes (highlight, replay, drawer). 150–250 ms ease-out; one pulse per highlight, no infinite animation.
- **Accessibility:** keyboard focus rings, every interactive map element reachable from a list too (the switch and building lists in the legend), WCAG AA contrast for text.

## 11. Files (expected shape)

- `dashboard/public/campus/iitbbs-campus-map.svg` (cropped, recoloured copy) and `campus-features.json` (subset: id, name, short, category, position).
- `dashboard/src/campus/`: `CampusMap.tsx`, `placement.ts`, `paths.ts` (BFS, unit-tested), `layers.ts`.
- `dashboard/src/complaints/`: `types.ts`, `source.ts`, `sample.ts`, `ComplaintLayer.tsx`, `BuildingSummary.tsx`.
- `dashboard/src/components/`: `DiagnosisPanel.tsx` (from `IncidentView`), `AgentStrip.tsx`, `ReplayControls.tsx`, restyled `Swimlane.tsx`, `CommunityView.tsx`; `MapView.tsx` replaced by `CampusMap` in both tabs.
- `dashboard/src/styles.css` rewritten around CSS custom properties.
- Docs: D-26 in docs/00 §7, a note in doc 11, doc 14 (demo) screenshots refreshed, the dashboard section of doc 13 if commands change, and an `IMPLEMENTATION_LOG.md` entry.

## 12. Left to the builder

Exact component boundaries, the SVG recolouring method, popover positioning, curve shapes, the sample complaint texts (realistic but obviously illustrative), responsive breakpoints below 1200 px, and the unit tests for `paths.ts`, `placement.ts` (every API zone either placed or reported "not placed") and the complaint source.

## 13. Verification

All gates in §3 pass. In addition, run S-01, S-02, S-03 and S-10 in the browser, take screenshots, and check that each shows the state in §6. A judge-style check: open the app cold, run S-02, and confirm the cause, the switch on the map and the agent replay are all visible without scrolling at 1440×900.
