# Campus Network Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the dashboard into Layout A: the IIT Bhubaneswar campus map, with the simulated network drawn on it, at the centre; the diagnosis panel on the right; the agent strip and a replayable message view at the bottom; plus a labelled sample-complaint layer.

**Architecture:** Pure logic first (geometry, placement, paths, highlight, replay, sample complaints), each unit-tested with Vitest. Then presentational React components on top: one `CampusMap` (Leaflet `CRS.Simple` + an SVG image overlay) used by both the Incidents and Campus map tabs. The backend and the API are untouched; every number comes from the existing endpoints or the labelled sample module.

**Tech Stack:** React 19, TypeScript, Vite, Leaflet + react-leaflet (existing), Vitest + Testing Library (existing), Playwright browser tests (existing, Python).

**Spec:** `docs/superpowers/specs/2026-11-01-campus-dashboard-design.md`

## Global Constraints

- Frontend only: change nothing under `src/netcoop/`, `config/`, `sample_data/`, or any API contract. No new npm or Python dependencies.
- Branch: create `feature/campus-dashboard` from `feature/protocol-upgrade`; never commit to `develop` or `main`.
- Copy rules: never "live", "real-time" or "calibrated". Confidence copy keeps "heuristic score … not a probability". The simulation banner (`role="note"`, containing "Simulated data" and "no access to any real campus network") stays.
- Placement label, verbatim, always visible when switches are drawn: `Simulated network, illustrative placement, not real switch locations.`
- Sample complaints: toggle label `Sample reports (demo data)`; every badge and popover carries `SAMPLE`; legend line `Illustrative demo data, not real reports`.
- Palette: bg `#0a0e13`, panel `#10161d`, line `#1d2630`, text `#e6edf3`, muted `#8592a0`, accent `#5b9bff`, ok `#46b98a`, warning `#e0a43c`, critical `#e5605a`. Fonts: Atkinson Hyperlegible (UI), IBM Plex Mono (ids, metrics). Type scale 11/12/13/15/20 px; 4 px spacing grid; 8 px radius; motion 150–250 ms ease-out, no infinite animation; honour `prefers-reduced-motion`.
- Browser-test hooks that must survive (all in `tests/ui/test_dashboard_e2e.py`; do not edit that file): `role=note` banner; text `Run a scenario to start one.`; tabs `Incidents` / `Campus map` / `User reports`; Tab from the `Incidents` tab lands on a BUTTON/SELECT/INPUT/SUMMARY/TEXTAREA; labels `Scenario`, `Failure`; button `Run diagnosis`; disclosure text `Simulate an agent failure`; `.cause`; `meter` "Heuristic confidence score" inside `.meter` with "not a probability"; `img` "Message exchange…" visible after a run with ≥10 `.swim .arrow`, clickable `.swim .row-hit`, `.swim-detail`; evidence as table cells (`cell` "link_utilization_pct"); `Approve` buttons disabled until `Your name (recorded with each decision)` is filled; `.outcome` starting "SIMULATED"; **limitations visible without a click** ("No finding from performance_agent"); community form labels, `role=status`, `cell` "ZONE_HOSTEL_A", `Investigate`, `.notice` containing "corroborated"; on Campus map: `.leaflet-container`, the API `provenance_note` text, select labelled `Show incident` with candidate-sourced options, ≥20 `path.leaflet-interactive`, `aria-label="Map legend"` containing "Reported by users (unverified)", "Detected fault", "Would be isolated"; no page errors.
- Gates after every task: `npm --prefix dashboard test`, `npm --prefix dashboard run build`. After tasks 5–8 also `uv run pytest -m ui -q` (7 passed). Final task: all gates in CLAUDE.md.
- Commits end with the session attribution lines (Co-Authored-By + Claude-Session).

## Review Focus

1. Affected device is the core (`SW_CAMPUS_1`) or has no path to it → no highlighted path, device still marked, no exception. (Test in Task 2.)
2. An API zone with no entry in the placement table → device not drawn, listed under "Not placed" in the legend, never silently lost. (Test in Task 1.)
3. Switching incident while a replay runs → the old timer stops, no pulse from the previous incident appears. (Test in Task 4.)
4. Incident with `report: null` (paused, failed or still running) → panel shows state and status, map neutral, no crash. (Test in Task 2 for highlight, Task 7 for the panel.)
5. Geospatial feature off (`/api/geo/layers` → 404) → Incidents tab shows the artwork with the "Network layer off" notice and works; no page error. (Test in Task 7.)

Spec deviations (builder-check and test constraints, recorded here so reviewers don't flag them):
- Limitations and "What could not be assessed" stay **expanded** (spec §5.2 said collapsed): a browser test reads a limitation without clicking.
- Not-assessable devices are **not** drawn hollow (spec §6): the generator omits `interface_errors` for all devices outside hardware failures, so every switch would be hollow in almost every run. The device popover lists that device's not-assessable metrics instead, so missing data is never presented as healthy.
- Campus features ship as a typed module (`src/campus/features.ts`) rather than `public/campus-features.json`.

---

### Task 1: Campus geometry and placement

**Files:**
- Create: `dashboard/public/campus/iitbbs-campus-map.svg` (copy of `../TECHZEPHYER/design-references/iitbbs-campus-map-research-package/iitbbs-campus-map.svg`, root `viewBox` changed to `48 155 1255 1010`, `width="1255" height="1010"`; keep the artwork otherwise)
- Create: `dashboard/src/campus/coords.ts`, `dashboard/src/campus/features.ts`, `dashboard/src/campus/placement.ts`
- Test: `dashboard/src/campus/placement.test.ts`

**Interfaces:**
- Produces:
  - `coords.ts`: `export const MAP_CROP = { x: 48, y: 155, w: 1255, h: 1010 }`, `export const SVG_HEIGHT = 1240`; `toLatLng(x: number, y: number): [number, number]` returning `[SVG_HEIGHT - y, x]`; `IMAGE_BOUNDS: [[number, number], [number, number]]` = `[[75, 48], [1085, 1303]]`.
  - `features.ts`: `export interface CampusFeature { id: string; name: string; short: string; category: string; x: number; y: number }` and `export const CAMPUS_FEATURES: CampusFeature[]`, the 19 features from the package's `iitbbs-campus-map-data.json` (`id`, `name`, `short`, `category`, `position_xy.x/y`), with a header comment naming the source file and its "diagrammatic, not to scale" note.
  - `placement.ts`: `export const PLACEMENT_NOTE = "Simulated network, illustrative placement, not real switch locations."`; `export const ZONE_TO_BUILDING: Record<string, string>` (spec §7 table: DATA_CENTRE→`admin`, HOSTEL_A→`mhr`, HOSTEL_B→`bhr`, ADMIN→`sac`, LECTURE_HALLS→`lhc`, ACADEMIC_BLOCK→`sbs`, LIBRARY→`secs`, DEPT_LAB→`sif`, keys are the full `ZONE_…` ids); `export interface PlacedDevice { id: string; role: string; zone: string; core: boolean; buildingId: string; x: number; y: number }`; `placeDevices(devices: MapLayers["devices"]): { placed: PlacedDevice[]; notPlaced: string[] }`. Devices sharing a building are fanned out so they never overlap each other or cover the building label (the builder picks the offsets; deterministic, sorted by id).

- [ ] **Step 1: Write the failing tests** in `placement.test.ts`:
  - `toLatLng(650, 620)` equals `[620, 650]`; `IMAGE_BOUNDS` equals `[[75, 48], [1085, 1303]]`.
  - Every value of `ZONE_TO_BUILDING` is an id in `CAMPUS_FEATURES`.
  - With the 10 devices of `sample_data/topology/campus_v1.json` (inline fixture: ids, roles, zones, `core` true only for `SW_CAMPUS_1`), `placeDevices` places 10, `notPlaced` is `[]`, `SW_CAMPUS_4.buildingId === "mhr"`, and the three `ZONE_DATA_CENTRE` devices are on `admin` at three distinct `(x, y)`.
  - A device in `ZONE_UNKNOWN` lands in `notPlaced` (Review Focus 2).
  - All placed coordinates fall inside `MAP_CROP`.
- [ ] **Step 2: Run** `npm --prefix dashboard test -- placement`. Expected: FAIL (modules missing).
- [ ] **Step 3: Implement** the three modules and copy and crop the SVG.
- [ ] **Step 4: Run** `npm --prefix dashboard test -- placement`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(dashboard): campus geometry, features and illustrative switch placement`.

### Task 2: Paths and incident highlight

**Files:**
- Modify: `dashboard/src/api.ts` (add `hypotheses?: { cause_type: string; entities: string[]; score: number }[]` to `Report["netcoop_extensions"]`)
- Create: `dashboard/src/campus/paths.ts`, `dashboard/src/campus/highlight.ts`
- Test: `dashboard/src/campus/highlight.test.ts`

**Interfaces:**
- Consumes: `MapLayers`, `Overlay`, `Report` from `api.ts`.
- Produces:
  - `paths.ts`: `shortestPath(links: { id: string; a: string; b: string }[], from: string, to: string): string[]`, the link ids along a BFS shortest path, ties broken by link id order; `[]` when `from === to` or unreachable.
  - `highlight.ts`: `export type DeviceState = "neutral" | "ok" | "critical" | "warning" | "isolated" | "suspect"`; `export interface Highlight { status: string | null; devices: Record<string, DeviceState>; links: string[]; focus: string[] }`; `deriveHighlight(report: Report | null, layers: MapLayers, overlay: Overlay | null): Highlight`.
  - Rules (spec §6): `report` null or status `failed` → every device `neutral`, no links. `no_fault_detected` → every device `ok`. `diagnosed` → `affected_devices` are `critical`, and the links are the union of `shortestPath` from each to the core device; from the first `overlay.blast_radius` entry, `degraded` → `warning` and `isolated` → `isolated` (never overriding `critical`). `insufficient_evidence` → `affected_devices`, or if empty `hypotheses[0].entities`, are `suspect`; no links. Every other device is `neutral`. `focus` = the critical or suspect ids.

- [ ] **Step 1: Write the failing tests** (fixture: the campus_v1 links, inline):
  - `shortestPath(links, "SW_CAMPUS_4", "SW_CAMPUS_1")` equals `["L-2-4", "L-1-2"]`; core→core gives `[]`; to `"SW_X"` gives `[]`.
  - S-02-like report (`diagnosed`, affected `["SW_CAMPUS_4"]`) with overlay blast `{ degraded: ["SW_CAMPUS_5"], isolated: [] }` → `devices.SW_CAMPUS_4 === "critical"`, `SW_CAMPUS_5 === "warning"`, `links` equal `["L-2-4", "L-1-2"]`, `focus` `["SW_CAMPUS_4"]`.
  - `diagnosed` with affected `["SW_CAMPUS_1"]` → `SW_CAMPUS_1` critical, `links` `[]`, no throw (Review Focus 1).
  - `insufficient_evidence` with `affected_devices: []` and `hypotheses: [{ entities: ["SW_CAMPUS_7"], … }]` → `SW_CAMPUS_7 === "suspect"`; with both empty → all `neutral`.
  - `no_fault_detected` → all `ok`; `null` report → all `neutral`, `status` null (Review Focus 4).
- [ ] **Step 2: Run** `npm --prefix dashboard test -- highlight`. Expected: FAIL.
- [ ] **Step 3: Implement** `paths.ts`, `highlight.ts` and the `api.ts` type.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(dashboard): shortest paths and per-status incident highlight`.

### Task 3: Sample complaint source

**Files:**
- Create: `dashboard/src/complaints/types.ts`, `source.ts`, `sample.ts`
- Test: `dashboard/src/complaints/complaints.test.ts`

**Interfaces:**
- Produces:
  - `types.ts`: `ComplaintMarker { id: string; buildingId: string; category: "wifi" | "slow" | "disconnect" | "other"; text: string; reportedAt: string }`; `ComplaintCluster { buildingId: string; count: number; byCategory: Record<string, number>; latest: ComplaintMarker[] }`; `interface ComplaintSource { readonly label: string; readonly isSample: boolean; list(): Promise<ComplaintMarker[]> }`.
  - `source.ts`: `clusterByBuilding(markers: ComplaintMarker[]): ComplaintCluster[]`, sorted by count descending then by building id, with `latest` = the 3 newest by `reportedAt`.
  - `sample.ts`: `export const sampleComplaintSource: ComplaintSource` with `label: "Sample reports (demo data)"`, `isSample: true`, and 15 hand-written markers across 5 buildings (`mhr`, `bhr`, `lhc`, `sbs`, `sac`). The ids start `SAMPLE-` and the timestamps are fixed ISO strings (deterministic). The texts are plainly illustrative, e.g. "SAMPLE: Wi-Fi drops in the evening (demo)".

- [ ] **Step 1: Write the failing tests:** `sampleComplaintSource.isSample` is true; every marker id starts with `SAMPLE-` and every `buildingId` is in `CAMPUS_FEATURES`; `clusterByBuilding` on 3 markers (2 at `mhr` with categories wifi and slow, 1 at `lhc`) returns `mhr` first with `count 2` and `byCategory { wifi: 1, slow: 1 }`; `latest` has length ≤ 3, newest first.
- [ ] **Step 2: Run** `npm --prefix dashboard test -- complaints`. Expected: FAIL.
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(dashboard): complaint source interface with labelled sample data`.

### Task 4: Replay and agent activity logic

**Files:**
- Create: `dashboard/src/lib/replay.ts`
- Test: `dashboard/src/lib/replay.test.ts`

**Interfaces:**
- Consumes: `TraceEvent` (`api.ts`), `layoutTrace` / `Row` (`lib/lanes.ts`).
- Produces:
  - `export const STRIP_AGENTS = ["performance_agent", "infrastructure_agent", "connectivity_agent", "correlation_agent", "reporting_agent"] as const`.
  - `devicesIn(summary: string): string[]`: unique matches of `/SW_CAMPUS_\d+/g`, in order of first appearance.
  - `agentActivity(events: TraceEvent[], upTo: number): Record<string, { messages: number; status: "idle" | "waiting" | "replied" | "error" }>`: over `events.slice(0, upTo + 1)` of kind `message`. `error` if the agent sent an invalid message or an `agent_error`, or an invalid message was addressed to it; else `replied` if it sent a valid message; else `waiting` if it received one; else `idle`. `messages` counts the messages it sent or received.
  - `useReplay(rowCount: number, opts: { auto: boolean; stepMs?: number; resetKey: string }): { cursor: number; playing: boolean; play(): void; pause(): void; step(): void; restart(): void }`. `cursor` is the last revealed row index; it equals `rowCount - 1` when not playing and replay never started. `stepMs` defaults to 450. When `matchMedia("(prefers-reduced-motion: reduce)")` matches, `play` jumps straight to the end. A change of `resetKey` stops the timer and resets (Review Focus 3). The timer is cleared on unmount.

- [ ] **Step 1: Write the failing tests:**
  - `devicesIn("decision: link_congestion on SW_CAMPUS_4, SW_CAMPUS_4 and SW_CAMPUS_10")` equals `["SW_CAMPUS_4", "SW_CAMPUS_10"]`.
  - `agentActivity`: task to performance, then a valid finding back → `performance_agent.status === "replied"` and `messages === 2`; an invalid message from performance → `error`; a task only → `waiting`; `reporting_agent` with no messages → `idle`.
  - `useReplay` with fake timers (`renderHook` from Testing Library): with `auto: true`, `rowCount 5`, `stepMs 100`, cursor goes 0→4 after 400 ms and then `playing` is false; `pause` freezes the cursor; changing `resetKey` mid-play stops the advance (cursor unchanged after another 500 ms, `playing` false).
- [ ] **Step 2: Run** `npm --prefix dashboard test -- replay`. Expected: FAIL.
- [ ] **Step 3: Implement** `replay.ts`.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(dashboard): replay cursor, agent activity and device mentions`.

### Task 5: Visual system and app shell

**Files:**
- Modify: `dashboard/src/styles.css` (rewrite around CSS custom properties from Global Constraints; restyle the existing classes `.banner .topbar .tabs .rail .incident-list .status.* .meter* .swim* .arrow* .lane-* .state-* .notice .error-box .legend .review-item .outcome table` for dark), `dashboard/src/App.tsx`
- Test: none new (presentational). Verified by the existing browser tests.

**Interfaces:**
- Produces: CSS variables `--bg --panel --line --text --muted --accent --ok --warning --critical --radius --font-ui --font-mono`, and utility classes `.panel`, `.label` (10 px uppercase), `.tag` and `.tag.ok|warning|critical|neutral`, `.pill`, used by Tasks 6–8.

- [ ] **Step 1:** Rebuild the shell in `App.tsx` per spec §5.1. The top bar holds the wordmark, the tabs (`role=tab`, same feature-flag gating), the `Simulated data · scenario playback` pill, and the run controls (same `Scenario` select, the `Simulate an agent failure` `<details>` with `Agent`/`Failure` selects, and `Run diagnosis`). The slim `role=note` banner (same text) sits below it. The left rail keeps the incident list and the empty text `No incidents yet. Run a scenario to start one.` Keep the DOM order so Tab from the `Incidents` tab reaches a button. Fetch `api.layers()` once when `health.features.geospatial` is true and pass it down; on failure store `null`.
- [ ] **Step 2:** Rewrite `styles.css` to the dark system; the rail collapses below 1200 px.
- [ ] **Step 3: Run** `npm --prefix dashboard run build && npm --prefix dashboard test`, then `uv run pytest -m ui -q`. Expected: build OK, all Vitest pass, `7 passed`.
- [ ] **Step 4: Commit** `feat(dashboard): dark visual system and redesigned shell`.

### Task 6: CampusMap and the Campus map tab

**Files:**
- Create: `dashboard/src/campus/CampusMap.tsx`, `dashboard/src/complaints/BuildingSummary.tsx`
- Modify: `dashboard/src/components/MapView.tsx` (becomes the Campus map tab: controls, legend and footer around `CampusMap`)
- Test: `dashboard/src/complaints/BuildingSummary.test.tsx`

**Interfaces:**
- Consumes: Task 1 (`IMAGE_BOUNDS`, `toLatLng`, `CAMPUS_FEATURES`, `placeDevices`, `PLACEMENT_NOTE`), Task 2 (`Highlight`, `DeviceState`), Task 3 (`ComplaintCluster`).
- Produces:
  - `CampusMap(props: { layers: MapLayers | null; highlight: Highlight | null; reportedZones?: { zone: string; corroborated: boolean }[]; complaints?: ComplaintCluster[] | null; pulse?: string[]; deviceInfo?: (id: string) => ReactNode; onDeviceClick?: (id: string) => void; variant: "hero" | "full" })`.
  - It renders a `MapContainer` (`crs={CRS.Simple}`, `bounds={IMAGE_BOUNDS}`, `attributionControl={false}`), an `ImageOverlay` of `/campus/iitbbs-campus-map.svg` at `IMAGE_BOUNDS`, building hit areas as `CircleMarker`s at each feature (transparent fill, visible on hover and focus, popover with name and category plus switches there plus `BuildingSummary` when complaints are given), links as curved `Polyline`s (highlighted links in `--critical`, others in `--line`), and devices as `CircleMarker`s (radius by role: core 9, distribution 7, access 6; colour by `DeviceState`; `suspect` uses a dashed outline). Pulse: a CSS class on the marker path for one 600 ms ring per id in `pulse`. With `layers === null` it shows only the artwork, plus an overlay notice `Network layer off. Start the backend with NETCOOP_ENABLE=community_signals,geospatial (doc 13).` `PLACEMENT_NOTE` is always shown in the bottom-left corner when devices are drawn. User-report zones from the API are drawn as amber (dashed) or violet (corroborated) rings around the zone's building.
  - `BuildingSummary(props: { building: CampusFeature; cluster: ComplaintCluster })`: heading with a `SAMPLE` tag, the count by category, and the 3 latest texts.
- Tab (`MapView`) keeps: the API `provenance_note` paragraph, the `Show incident` select (same options as today), toggles `Blast radius` and `Sample reports (demo data)` (off by default), device click → `api.blast` as today, and a legend with `aria-label="Map legend"` containing (verbatim) `Reported by users (unverified)`, `Reported and confirmed by telemetry`, `Detected fault (telemetry)`, `Would be isolated`, `Would lose redundancy`, `Device, no finding`, `Illustrative demo data, not real reports` (when the sample layer is on), `Not placed: …` (when `notPlaced` is non-empty), plus `PLACEMENT_NOTE`. In this tab the highlight comes from `deriveHighlight(incidentReport, layers, overlay)`. Fetch the report with `api.incident(id)` when an incident is chosen.

- [ ] **Step 1: Write the failing test** `BuildingSummary.test.tsx`: rendering MHR with a cluster `{ count: 2, byCategory: { wifi: 1, slow: 1 }, latest: [2 markers] }` shows the text `SAMPLE`, `Mahanadi` (or the feature's name), `2 reports`, and both marker texts.
- [ ] **Step 2: Run** `npm --prefix dashboard test -- BuildingSummary`. Expected: FAIL.
- [ ] **Step 3: Implement** `BuildingSummary`, `CampusMap` and the new `MapView`.
- [ ] **Step 4: Run** `npm --prefix dashboard test && npm --prefix dashboard run build && uv run pytest -m ui -q`. Expected: PASS and `7 passed` (`test_map_layers` needs ≥20 interactive paths: 11 links + 10 devices + building hit areas).
- [ ] **Step 5:** Start the app (`NETCOOP_ENABLE=community_signals,geospatial uv run fastapi dev` plus `npm --prefix dashboard run dev`, both as tracked background tasks) and check the Campus map tab at 1440×900: the artwork is crisp, switches don't cover labels, the placement note is visible, and the sample toggle shows badges with `SAMPLE`.
- [ ] **Step 6: Commit** `feat(dashboard): interactive IIT BBS campus map with simulated network and sample report layer`.

### Task 7: Incidents tab, Layout A

**Files:**
- Create: `dashboard/src/components/DiagnosisPanel.tsx`, `dashboard/src/components/AgentStrip.tsx`
- Modify: `dashboard/src/components/IncidentView.tsx` (composition only), `dashboard/src/components/Swimlane.tsx` (add the `cursor` prop), `dashboard/src/App.tsx` (pass `layers` and `autoReplay`)
- Test: `dashboard/src/components/DiagnosisPanel.test.tsx`, `dashboard/src/components/AgentStrip.test.tsx`

**Interfaces:**
- Consumes: Tasks 2, 4, 6.
- Produces:
  - `DiagnosisPanel(props: { id: string; detail: IncidentDetail; review: ReviewItem[]; onChanged: () => void; onReload: () => void })`. It moves today's header, resume notice, `.cause`, narrative rule, `ConfidenceMeter`, evidence `<table>`, community-signals `.notice`, alternatives ("Also considered"), `ReviewPanel` and `NotAssessable` + limitations (expanded) out of `IncidentView` unchanged in behaviour. `StatusTag` text becomes: diagnosed "Fault diagnosed", insufficient_evidence "Needs more evidence", no_fault_detected "No fault", failed "Run failed", null "Not reported yet"; the class still keys off status. With `detail.report === null` it shows the header and state only.
  - `AgentStrip(props: { activity: ReturnType<typeof agentActivity>; replay: ReturnType<typeof useReplay>; messagesOpen: boolean; onToggleMessages: () => void })`. Five chips in `STRIP_AGENTS` order with `AGENT_LABELS`, a message count and a status dot, each with an `aria-label` like "Performance: replied, 2 messages". Buttons: `Replay`/`Pause`, `Step`, and `Messages` (`aria-expanded`).
  - `Swimlane({ events, cursor }: { events: TraceEvent[]; cursor?: number })`: rows with index > `cursor` get the class `pending` (dimmed via CSS) and the row at `cursor` gets `current`. All rows are always rendered. Its `role="img"` label is unchanged.
  - `IncidentView({ id, onChanged, layers, autoReplay }: { id: string; onChanged: () => void; layers: MapLayers | null; autoReplay: boolean })`. It lays out a grid: `CampusMap variant="hero"` (highlight from `deriveHighlight(detail.report, layers, overlay)`; when `layers` is set it fetches `api.overlay(id)`, a failure gives `null`; `pulse = devicesIn(currentRow.summary)` while playing; `deviceInfo` shows id, role, zone, building, matching evidence rows and that device's not-assessable metrics) | `DiagnosisPanel` on the right (380 px, scrolls on its own) | `AgentStrip` + the messages panel (`Swimlane` with `cursor`, plus the legend sentence) below, open by default. `useReplay(rows.length, { auto: autoReplay, resetKey: id })`.

- [ ] **Step 1: Write the failing tests:**
  - `DiagnosisPanel`: with the S-02 report fixture (trimmed from `docs/results/example-S-02-report.json`), it shows `.cause` text, a `meter` named "Heuristic confidence score", the text "not a probability", a cell `link_utilization_pct`, `Fault diagnosed`, and a limitation's text without any click. With `report: null` and `state: "COLLECTING"` it renders `Not reported yet` and `COLLECTING` and doesn't throw (Review Focus 4).
  - `AgentStrip`: given an activity where performance is `error` and the others are `replied`, it renders 5 chips and the label "Performance: error"; clicking `Messages` calls `onToggleMessages`.
- [ ] **Step 2: Run** `npm --prefix dashboard test -- DiagnosisPanel AgentStrip`. Expected: FAIL.
- [ ] **Step 3: Implement** the components, the `Swimlane` cursor and the `IncidentView` composition. Pass `autoReplay` true from `App` only for the incident just created by `Run diagnosis`.
- [ ] **Step 4: Write a test for Review Focus 5:** `IncidentView` rendered with `layers={null}` and mocked `api.incident`/`api.trace` (vi.mock of `../api`) shows `Network layer off` and the `.cause` text. Run it. Expected: PASS once implemented.
- [ ] **Step 5: Run** `npm --prefix dashboard test && npm --prefix dashboard run build && uv run pytest -m ui -q`. Expected: all pass, `7 passed`.
- [ ] **Step 6:** In the running app, run S-01, S-02, S-03 and S-10 at 1440×900. Check: S-02 shows a red SW_CAMPUS_4 at MHR with the highlighted path to the core and the cause, map and agent strip all on screen without scrolling; S-01 is all green with the "No fault" tag; S-03 is amber dashed (or neutral with the panel explaining) with "Needs more evidence"; S-10 shows the performance chip as `error` and the red arrow; replay plays once after a run and pulses SW_CAMPUS_4 on the decision.
- [ ] **Step 7: Commit** `feat(dashboard): Layout A incident screen with diagnosis panel, agent strip and replay`.

### Task 8: User reports restyle, docs and release check

**Files:**
- Modify: `dashboard/src/components/CommunityView.tsx` (classes only; same labels, roles and flow), `docs/00-scope-and-decisions.md` (§7 row **D-26**), `docs/11-geospatial-network-intelligence.md` (a note after ID-17), `docs/14-demo-and-submission.md` (the demo path uses the new screen), `docs/13-setup-and-operations.md` (only if a command changed), `IMPLEMENTATION_LOG.md`, `docs/results/screenshots/*.png` (regenerated)

- [ ] **Step 1:** Restyle `CommunityView` to the panel system without changing any label, role or table.
- [ ] **Step 2:** Docs:
  - D-26 row: `| D-26 | Dashboard placement of simulated switches on the IIT BBS campus artwork | Doc 11, dashboard | **PROVISIONAL** (owner choice, option 1): frontend table dashboard/src/campus/placement.ts maps each simulated zone to a campus building; drawn with "Simulated network, illustrative placement, not real switch locations."; backend schematic layout unchanged |`.
  - Doc 11: the dashboard now draws the simulated topology over the owner's diagrammatic campus artwork (source package, not to scale), refining ID-17 for display only.
  - Log entry: what changed, the three spec deviations, and that no backend file changed (`git diff --stat feature/protocol-upgrade -- src config sample_data` is empty).
- [ ] **Step 3: Run every gate:** `uv run pytest -q`, `NETCOOP_SCREENSHOTS=docs/results/screenshots uv run pytest -m ui -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `npm --prefix dashboard run build`, `npm --prefix dashboard test`, `uv run netcoop scenarios run-all`. Expected: all pass, 13/13, `7 passed`. Then grep the dashboard source for `real-time|live |calibrated` and expect no hits.
- [ ] **Step 4:** Read the three regenerated screenshots and confirm each matches spec §5 and §6.
- [ ] **Step 5: Commit** `docs(dashboard): D-26 placement decision, demo path and refreshed screenshots`.
