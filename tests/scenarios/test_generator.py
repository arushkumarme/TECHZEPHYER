"""Tests for the vendored organizer generator and its seeded runner (M0 Task 2)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from netcoop.scenarios.generator import (
    DEFAULT_NOTEBOOK,
    EXPECTED_SHA256,
    FAULT_TYPES,
    GeneratorIntegrityError,
    load_generator,
)

AT = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)


def test_vendored_notebook_hash_is_pinned() -> None:
    import hashlib

    assert hashlib.sha256(DEFAULT_NOTEBOOK.read_bytes()).hexdigest() == EXPECTED_SHA256


def test_modified_notebook_is_refused(tmp_path: Path) -> None:
    tampered = tmp_path / "gen.ipynb"
    tampered.write_bytes(DEFAULT_NOTEBOOK.read_bytes().replace(b"99.9", b"10.0"))
    with pytest.raises(GeneratorIntegrityError):
        load_generator(tampered)


def test_same_seed_gives_identical_record() -> None:
    gen = load_generator()
    assert gen.generate("latency_spike", seed=7, at=AT) == gen.generate(
        "latency_spike", seed=7, at=AT
    )


def test_different_seeds_differ() -> None:
    gen = load_generator()
    a = gen.generate("normal", seed=1, at=AT)
    b = gen.generate("normal", seed=2, at=AT)
    assert a != b


@pytest.mark.parametrize("fault_type", FAULT_TYPES)
def test_record_layout(fault_type: str) -> None:
    rec = load_generator().generate(fault_type, seed=3, at=AT)
    assert set(rec) == {"timestamp", "device_id", "metrics", "status"}
    assert rec["timestamp"] == "2026-10-31T12:00:00Z"
    assert rec["device_id"].startswith("SW_CAMPUS_")


def test_profile_specific_fields() -> None:
    gen = load_generator()
    hw = gen.generate("hardware_failure", seed=1, at=AT)
    assert "interface_errors" in hw["metrics"]
    assert "jitter_ms" not in hw["metrics"]
    assert hw["status"] == "Critical"
    assert gen.generate("normal", seed=1, at=AT)["status"] == "Healthy"
    assert gen.generate("latency_spike", seed=1, at=AT)["status"] == "Warning"


def test_unknown_fault_type_is_rejected() -> None:
    # The organizer code silently falls back to "normal" for unknown types;
    # the runner refuses instead so a typo can never produce a mislabelled scenario.
    with pytest.raises(ValueError, match="unknown fault_type"):
        load_generator().generate("dns_failure", seed=1, at=AT)
