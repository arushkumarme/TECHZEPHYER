# Provenance — organizer telemetry generator (`SRC-4`)

| Item | Value |
|---|---|
| Linked from | `SRC-1 p4 §5` ("Sample- Input-generator-code-COLAB") |
| Colab URL (from the PDF's link annotation) | `https://colab.research.google.com/drive/1xFOtO114qWICAxGisK9K6oOHoOxwvGi1` |
| Retrieved | 2026-10-31, via the public Drive export URL `https://drive.google.com/uc?export=download&id=1xFOtO114qWICAxGisK9K6oOHoOxwvGi1` (no sign-in needed) |
| File | `organizer_generator.ipynb` — stored **unchanged** |
| SHA-256 | `f245012f96a878a10653d14df95bdb45cbd6c59f42c8fe61d33efebf70aea460` |
| Licence | Not stated by the organizers |

## How it is used

`src/netcoop/scenarios/generator.py` extracts the single code cell, checks the hash, and runs the organizer's `generate_telemetry(fault_type)` with a seeded `random.Random` and a fixed clock in place of the module globals `random` and `datetime`. The organizer's code is not edited. The runner refuses unknown fault types (the original code would silently fall back to `normal`).

## What the generator does *not* provide (OBSERVED by reading the code)

Topology, links, locations/zones, wireless signal, retransmissions, memory, throughput, bandwidth, DNS/DHCP or other service checks, schema version, seed support, multi-record output, and ground-truth labels beyond the `fault_type` argument itself.
