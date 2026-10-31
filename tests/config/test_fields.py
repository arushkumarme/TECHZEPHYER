"""T-DOC-01: the field dictionary only contains fields observed in the organizer generator."""

import re
from datetime import UTC, datetime

import pytest

from netcoop.config.fields import DEFAULT_FIELDS_PATH, FieldSpec, load_field_dictionary
from netcoop.scenarios.generator import FAULT_TYPES, load_generator


@pytest.fixture(scope="module")
def fields() -> dict[str, FieldSpec]:
    return load_field_dictionary(DEFAULT_FIELDS_PATH).fields


def test_every_field_cites_a_generator_line(fields: dict[str, FieldSpec]) -> None:
    gen_lines = load_generator().source.splitlines()
    for name, spec in fields.items():
        lines = [int(n) for n in re.findall(r"L(\d+)", spec.source)]
        assert lines, f"{name} has no line citation"
        for n in lines:
            assert f'"{name}"' in gen_lines[n - 1], f"{name}: gen:L{n} does not contain the field"


def test_names_appear_verbatim_in_generator(fields: dict[str, FieldSpec]) -> None:
    src = load_generator().source
    for name in fields:
        assert f'"{name}"' in src


def test_dictionary_matches_generator_output_exactly(fields: dict[str, FieldSpec]) -> None:
    gen = load_generator()
    at = datetime(2026, 10, 31, tzinfo=UTC)
    emitted_metrics: set[str] = set()
    for fault in FAULT_TYPES:
        for seed in range(20):
            rec = gen.generate(fault, seed=seed, at=at)
            emitted_metrics |= set(rec["metrics"])
            for metric, value in rec["metrics"].items():
                lo, hi = fields[metric].observed_ranges[fault]
                assert lo <= value <= hi, (fault, metric, value)
            assert rec["status"] in (fields["status"].allowed_values or [])
    dict_metrics = {n for n, s in fields.items() if s.location == "metrics"}
    assert emitted_metrics == dict_metrics


def test_observed_profiles_match_presence(fields: dict[str, FieldSpec]) -> None:
    gen = load_generator()
    at = datetime(2026, 10, 31, tzinfo=UTC)
    for fault in FAULT_TYPES:
        present = set(gen.generate(fault, seed=0, at=at)["metrics"])
        expected = {n for n, s in fields.items() if fault in s.observed_ranges}
        assert present == expected, fault


def test_percent_fields_have_plausible_bounds(fields: dict[str, FieldSpec]) -> None:
    for name, spec in fields.items():
        if spec.unit == "percent":
            assert (spec.plausible_min, spec.plausible_max) == (0, 100), name
