"""Controlled-vocabulary registry (protocol upgrade, Prompt 1).

The registry is metadata (definition, status, source, attributes) layered over the term
sets the code already enforces. These tests are the single-source-of-truth guard: they
fail if a vocabulary file and the code's Literal / config drift apart.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import pytest
from pydantic import BaseModel, ValidationError

from netcoop.config.fields import load_field_dictionary
from netcoop.core.vocabulary import (
    BlockedTermError,
    UnknownTermError,
    VocabTerm,
    all_vocabularies,
    get_vocabulary,
    is_valid,
    require,
)
from netcoop.core.vocabulary.units import (
    DimensionMismatchError,
    UnknownUnitError,
    convert,
    metric_dimension,
    unit_fits_metric,
)
from netcoop.ingestion.aliases import load_aliases
from netcoop.ingestion.issues import SEVERITY
from netcoop.scenarios.generator import REPO_ROOT

SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
UPPER = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")


# ------------------------------------------------------------------ structure


def test_every_vocabulary_loads_with_complete_terms() -> None:
    vocabs = all_vocabularies()
    assert len(vocabs) >= 25
    for v in vocabs.values():
        assert v.description and v.version
        ids = [t.id for t in v.terms]
        assert len(ids) == len(set(ids)), v.name
        for t in v.terms:
            assert t.definition.strip(), (v.name, t.id)
            assert t.source.strip(), (v.name, t.id)
            assert t.status in ("active", "deprecated", "blocked")
            if v.id_style == "snake":
                assert SNAKE.match(t.id), (v.name, t.id)
            elif v.id_style == "upper":
                assert UPPER.match(t.id), (v.name, t.id)


def test_vocabularies_linked_to_code_match_the_literals_exactly() -> None:
    """ONE source of truth: the non-blocked terms equal the values the code enforces."""
    linked = [v for v in all_vocabularies().values() if v.code_literal]
    assert len(linked) >= 15
    for v in linked:
        assert set(v.code_values()) == {t.id for t in v.terms if t.status != "blocked"}, v.name


def test_metric_terms_match_the_observed_field_dictionary() -> None:
    fields = load_field_dictionary().fields
    metrics = {t.id: t for t in get_vocabulary("metric").terms}
    generator = {t for t, m in metrics.items() if m.attributes.get("origin") == "generator"}
    assert generator == set(fields) - {"timestamp", "device_id"}
    for name in generator - {"status"}:
        m, spec = metrics[name], fields[name]
        assert m.attributes["unit"] == spec.unit, name
        category = get_vocabulary("metric_category").term(m.attributes["category"])
        assert category.label == spec.category, name
        assert m.attributes["dimension"] == metric_dimension(name), name


def test_every_problem_statement_category_is_listed() -> None:
    cats = get_vocabulary("metric_category")
    assert [t.id for t in cats.terms] == [
        "latency",
        "jitter",
        "packet_loss",
        "throughput",
        "bandwidth",
        "link_utilization",
        "device_status",
        "cpu_utilization",
        "memory_utilization",
        "egress_queue_drops",
        "interface_errors",
        "wireless_signal",
    ]
    # Categories the generator does not provide are marked, never given invented fields.
    absent = {t.id for t in cats.terms if not t.attributes["in_generator_data"]}
    assert absent == {"throughput", "bandwidth", "memory_utilization", "wireless_signal"}


def test_every_error_code_emitted_by_the_source_is_registered() -> None:
    known = {t.id for t in get_vocabulary("error_code").terms}
    other_upper = set()
    for name in ("incident_state", "bundle_acceptance", "not_assessable_reason", "rationale_code"):
        other_upper |= {t.id for t in get_vocabulary(name).terms}
    found: set[str] = set()
    for path in (REPO_ROOT / "src" / "netcoop").rglob("*.py"):
        for m in re.finditer(r"[\"']([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)[\"']", path.read_text("utf-8")):
            found.add(m.group(1))
    found = {c for c in found if not c.startswith(("NETCOOP_", "SW_", "ZONE_"))}
    # Ids of the other UPPER vocabularies are not error codes (some names are shared, e.g.
    # UNIT_AMBIGUOUS is both a code and a not-assessable reason).
    assert found - other_upper - known == set(), "unregistered codes"
    unused = known - found
    assert unused == set(), f"registered but never emitted: {sorted(unused)}"


def test_ingestion_severities_agree_with_the_registry() -> None:
    codes = {t.id: t for t in get_vocabulary("error_code").terms}
    for code, severity in SEVERITY.items():
        assert codes[code].attributes["severity"] == severity, code


# ------------------------------------------------------------------ lookups


def test_require_suggests_close_matches() -> None:
    assert require("cause_type", "link_congestion").label
    with pytest.raises(UnknownTermError) as exc:
        require("cause_type", "link_congestoin")
    assert "link_congestion" in exc.value.suggestions
    assert "did you mean" in str(exc.value)
    with pytest.raises(KeyError):
        get_vocabulary("no_such_vocabulary")


@pytest.mark.parametrize(
    ("vocab", "term"),
    [
        ("score_method", "calibrated"),
        ("mode", "deployment"),
        ("data_provenance", "verified-iitbbs"),
        ("data_provenance", "verified-public"),
    ],
)
def test_blocked_terms_are_always_rejected(vocab: str, term: str) -> None:
    assert not is_valid(vocab, term)
    with pytest.raises(BlockedTermError):
        require(vocab, term)


def test_extensible_rule() -> None:
    v = get_vocabulary("rationale_code")
    assert v.extensible
    t = require("rationale_code", "x-site-specific-rule")
    assert t.unrecognised
    with pytest.raises(UnknownTermError):
        require("rationale_code", "SITE_SPECIFIC_RULE")  # extensions need the x- prefix
    with pytest.raises(UnknownTermError):
        require("cause_type", "x-new-cause")  # closed vocabulary: no extensions


def test_annotated_type_in_a_model() -> None:
    class M(BaseModel):
        cause: Annotated[str, VocabTerm("cause_type")]

    assert M(cause="device_failure").cause == "device_failure"
    with pytest.raises(ValidationError, match="did you mean"):
        M(cause="device_fail")
    with pytest.raises(ValidationError, match="blocked"):

        class S(BaseModel):
            method: Annotated[str, VocabTerm("score_method")]

        S(method="calibrated")


# ------------------------------------------------------------------ units


def test_unit_round_trips() -> None:
    assert convert(0.25, "second", "millisecond") == pytest.approx(250.0)
    assert convert(250, "millisecond", "second") == pytest.approx(0.25)
    assert convert(0.94, "ratio", "percent") == pytest.approx(94.0)
    assert convert(94, "percent", "ratio") == pytest.approx(0.94)
    assert convert(12, "count", "count") == 12


def test_unit_errors_are_typed_and_never_guessed() -> None:
    with pytest.raises(DimensionMismatchError):
        convert(5, "millisecond", "percent")
    with pytest.raises(UnknownUnitError):
        convert(5, "furlong", "millisecond")
    # 0.94 is not silently treated as 94 %: without a declared unit there is no conversion.
    with pytest.raises(UnknownUnitError):
        convert(0.94, "", "percent")


def test_units_agree_with_the_ingestion_alias_table() -> None:
    aliases = load_aliases()
    units = {t.id: t for t in get_vocabulary("unit").terms}
    for spelling, (dimension_unit, factor) in aliases.units.items():
        matches = [u for u in units.values() if spelling in u.attributes["spellings"]]
        assert len(matches) == 1, spelling
        u = matches[0]
        canonical = units[dimension_unit]
        assert u.attributes["dimension"] == canonical.attributes["dimension"], spelling
        assert u.attributes["factor"] == pytest.approx(factor), spelling


def test_unit_fits_metric() -> None:
    assert unit_fits_metric("latency_ms", "millisecond")
    assert unit_fits_metric("latency_ms", "second")
    assert not unit_fits_metric("latency_ms", "percent")
    assert unit_fits_metric("queue_drops", "count")
    assert unit_fits_metric("status", "none")


# ------------------------------------------------------------------ generated artefacts


def test_docs_appendix_and_json_export_are_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_docs.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generator_is_idempotent(tmp_path: Path) -> None:
    from netcoop.core.vocabulary.render import render_appendix, render_json

    assert render_appendix() == render_appendix()
    assert render_json() == render_json()


# ------------------------------------------------------------------ registry-only drift


def test_every_gate_check_maps_to_an_abstention_reason() -> None:
    src = (REPO_ROOT / "src" / "netcoop" / "diagnosis" / "scoring.py").read_text("utf-8")
    checks = set(re.findall(r'checks\["([a-z_]+)"\]', src))
    block = src[src.index("checks = {") : src.index("}", src.index("checks = {"))]
    checks |= set(re.findall(r'"([a-z_]+)":', block))
    mapped = {t.attributes["gate_check"] for t in get_vocabulary("abstention_reason").terms}
    assert checks == mapped


def test_scenario_provenance_values_are_registered() -> None:
    from netcoop.scenarios.runner import list_scenarios, load_scenario

    for sid in list_scenarios():
        assert is_valid("data_provenance", load_scenario(sid).meta["provenance"]), sid


def test_report_builder_values_are_registered() -> None:
    src = (REPO_ROOT / "src" / "netcoop" / "report" / "builder.py").read_text("utf-8")
    for method in re.findall(r'"confidence_method": "([a-z_]+)"', src):
        assert is_valid("score_method", method)
    modes = set(re.findall(r'return "([a-z_]+)", ', src)) | set(
        re.findall(r'"recommendation_mode": "([a-z_]+)"', src)
    )
    assert modes == {t.id for t in get_vocabulary("recommendation_mode").terms}
