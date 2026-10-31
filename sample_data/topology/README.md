# Simulated topology — `SIMULATED`, team-authored

The organizer generator provides **no topology** (doc 06 §3). `campus_v1.json` is a team-authored synthetic network for hackathon simulation mode (decision ID-04). It reuses the generator's device IDs `SW_CAMPUS_1..10`. Zone names (`ZONE_HOSTEL_A`, …) are **placeholders**, not claims about IIT Bhubaneswar naming, wiring or buildings (doc 12 §1).

```
                 SW_CAMPUS_1 (core, ZONE_DATA_CENTRE)
                /                         \
   SW_CAMPUS_2 (distribution) ───── SW_CAMPUS_3 (distribution)
   /     |      |       \             /    |     \
 SW_4   SW_5   SW_10     └── SW_8 ───┘   SW_6   SW_7   SW_9
 Hostel Hostel Admin     Lecture halls   Acad.  Library Dept lab
   A      B              (dual-homed)
```

Blast-radius semantics (code: `src/netcoop/tools/topology.py`): failing `SW_CAMPUS_2` *isolates* SW_4, SW_5, SW_10 and *degrades* SW_3 and SW_8 (they keep a path through the remaining redundancy). These are structural statements about this simulated graph, not measured impact.
