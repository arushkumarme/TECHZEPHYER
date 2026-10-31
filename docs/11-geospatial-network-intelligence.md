# 11 — Extension B: Geospatial Network Intelligence

> Version 0.1 · 2026-10-31 · Draft for review · **Not an official requirement.** Built after the core and the basic dashboard. Stack: React + FastAPI + Leaflet, separated (`CD-3`).

## 1. Purpose and boundaries

An interactive map that makes an incident understandable at a glance: where complaints came from, which devices are technically implicated, and how far a failure would spread.

- **Read-only view.** It displays the topology file and incident reports; it never runs diagnosis and never changes anything.
- **Every layer says where its data came from** (§2). In hackathon mode devices, links and zones are simulated.
- **No "live" wording.** The map is *scenario playback* of synthetic data (doc 12 §1).

## 2. Data inputs and provenance

| Layer data | Hackathon source | Provenance label |
|---|---|---|
| Buildings / zones | Team-authored layer. Coordinates are approximate and illustrative unless verified against an official or public source (D-08) | `SIMULATED` (approximate) |
| Network devices and links | Simulated topology (generator's if it has one — D-09) | `SIMULATED` |
| Incident reports | Core pipeline output | synthetic |
| Community candidates | Extension A | synthetic |

Provenance values: `SIMULATED`, `TEAM-AUTHORED SYNTHETIC`, `VERIFIED-PUBLIC`, `VERIFIED-IITBBS` (the last two are `FUTURE`/`NEEDS-ACCESS` unless a source is actually checked). Every layer carries a badge; the page carries a persistent simulated-data banner. Location names such as "Hostel A" in demos are placeholders, not claims about real campus naming.

## 3. Layers and visual semantics

| Layer | Meaning | Rule |
|---|---|---|
| Buildings / zones | Spatial context | Always on |
| Devices and links | Simulated topology | Shown with provenance badge |
| **Reported areas** | Zones with a community candidate (`reported_unverified`) | Distinct style from technical faults — e.g. dashed outline with a speech-bubble marker |
| **Detected faults** | Entities implicated by telemetry (`detected`) | Solid style with a device marker |
| **Corroborated** | Both agree in place and time | Combines both marks plus its own label |
| **Blast radius** | Entities affected if a selected entity failed or is implicated | Separate toggle; two states (§4) |

Colour is never the only cue: each state also has a distinct marker shape and a legend entry (accessibility). Exact colours are chosen at implementation.

## 4. Dependency and blast radius

- **Computed by A-CONN** (deterministic graph traversal, `networkx`, doc 02 §4), not by the browser. The map renders the result.
- **Isolated:** the entity has no remaining path to the network's upstream/core once the implicated entity is removed.
- **Degraded:** a path remains (redundancy), so the entity is still connected but may have reduced capacity — capacity is not claimed.
- **Unknown:** topology missing or entity absent from it (never drawn as unaffected).
- Blast radius is **structural reach, not measured impact**. Measured impact comes only from telemetry, and the panel says so.
- What counts as "upstream/core" depends on topology data (`UNKNOWN` until D-09).
- Zone → device mapping (which access devices serve a zone) is part of the simulated topology.

## 5. Incident panel

Shows, for the selected incident: status; probable cause and confidence with its method label (`heuristic`); trust label; affected devices; blast radius; supporting evidence (telemetry only); alternative causes; limitations; what could not be assessed; community summary (separate block); recommendations marked *requires human approval* and *simulated*; link to the message trace.

## 6. Scenario playback

A scenario selector replays the stored scenario and its resulting report. The UI says "playback". It does not poll devices.

## 7. Backend interface (`PROPOSAL`)

Read-only resources served by FastAPI, consumed by React: incident list and detail; topology; map layers with provenance; community candidates; message trace; and one write path for recording a (simulated) human approval and one for complaint submission (extension A). Exact routes decided at implementation. Frontend and backend are separate deployables.

## 8. Map data and offline operation

- Tile servers need internet. A fallback is required for a venue without it: a pre-saved base image or a schematic (non-geographic) layout of the same layers.
- Building coordinates and any outlines must come from a source we have actually checked (D-08); otherwise they are labelled approximate.

## 9. Testing

`T-GEO-PROV-*` (every layer carries provenance; banner present), `T-GEO-LAYER-*` (reported and detected styled and filtered separately), `T-GEO-PANEL-01` (panel content), `T-GEO-BLAST-*` (isolated vs degraded vs unknown on scenario S-16 and a no-topology case), `T-UI-LABEL-*`.

## 10. Pending and limitations

- Real building geometry and positions: unavailable without verified sources (D-08).
- Topology realism: simulated, so blast radius demonstrates the method, not the real campus.
- Performance with large topologies is not a goal.

## 11. Implementation (M16 backend, 2026-10-31) — `IMPLEMENTED`, `TESTED`, `SIMULATED`

- **ID-17: schematic map.** No verified building coordinates exist (D-08), so `sample_data/topology/campus_v1_layout.json` is a team-authored *schematic, non-geographic* layout (x/y units; Leaflet `CRS.Simple`). It needs no tile server (offline, §8) and cannot be mistaken for real campus geography. Zone labels say "(placeholder)".
- Code: `src/netcoop/geo/layers.py` (`campus_layers`, `blast_radius`, `incident_overlay`), API `src/netcoop/api/geo.py` (`GET /api/geo/layers`, `GET /api/geo/blast-radius/{entity}`, `GET /api/geo/incidents/{id}`), registered only when `features.geospatial = true`.
- Layers: zones, devices, links (each with `provenance: SIMULATED`), `reported_areas` (style `reported`, from community signals), `detected_faults` (style `detected`, only for `diagnosed` reports), `corroborated`, `blast_radius` (isolated / degraded / unaffected / unknown + affected zones; basis "structural reach … not measured impact"), and the incident `panel` (§5 fields incl. recommendations marked simulated and approval-gated, community summary, trace link).
- Tests: `tests/geo/test_geo.py` (provenance on every layer, layout ↔ topology, S-16 isolated vs degraded, unknown without topology, reported vs detected separation, corroborated, panel fields, API behind the flag).
- The React/Leaflet rendering is M17.

## 12. Dashboard (M17, 2026-10-31) — `IMPLEMENTED`, `TESTED`

`dashboard/` (React 19 + Vite 8 + TypeScript 7 + react-leaflet 5, `CRS.Simple`). Views: incidents (cause, heuristic confidence meter with threshold, **agent exchange swimlane** of every message, evidence, alternatives, review with recorded reviewer and simulated outcome, what could not be assessed, limitations), campus map (zones with permanent placeholder labels, reported = dashed amber, corroborated = violet fill, detected = solid red marker, isolated = filled ink, degraded = dashed amber ring; click a device for its blast radius; legend coded by shape and stroke, not colour alone), user reports (web form + candidates + investigate). A persistent, non-dismissible "Simulated data — scenario playback" banner sits on every view. Browser-verified (`tests/ui/`, Chromium) incl. keyboard reachability and no page errors; screenshots in `docs/results/screenshots/`.
