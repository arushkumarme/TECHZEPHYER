"""T-MODE-01: only simulation mode exists; config files are loaded and validated."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from netcoop.config.settings import load_settings
from netcoop.ingestion.aliases import load_aliases


def test_default_settings_are_simulation_with_everything_optional_off() -> None:
    s = load_settings()
    assert s.mode == "simulation"
    assert (s.features.community_signals, s.features.geospatial, s.features.llm) == (
        False,
        False,
        False,
    )


@pytest.mark.parametrize("mode", ["live", "deployment", "", "SIMULATION"])
def test_other_modes_are_refused(tmp_path: Path, mode: str) -> None:
    p = tmp_path / "netcoop.toml"
    p.write_text(f'mode = "{mode}"\n', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(p)


def test_alias_config_declares_team_authored_provenance() -> None:
    a = load_aliases()
    assert "team-authored" in a.provenance
    assert all(a.unit(al.unit) is not None for al in a.metric_aliases.values() if al.unit)


def test_env_enables_features(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETCOOP_ENABLE", "community_signals, geospatial")
    f = load_settings().features
    assert (f.community_signals, f.geospatial, f.llm) == (True, True, False)


def test_env_unknown_feature_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETCOOP_ENABLE", "live_mode")
    with pytest.raises(ValueError, match="unknown features"):
        load_settings()
