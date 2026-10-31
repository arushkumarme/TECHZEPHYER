"""Session setup shared by all tests."""

from __future__ import annotations

import pytest

from netcoop.scenarios.generator import ensure_notebook


@pytest.fixture(autouse=True, scope="session")
def organizer_generator() -> None:
    """The organizers' notebook is not redistributed (no stated licence); fetch it once
    from their public link and verify its SHA-256 before any test reads it."""
    ensure_notebook()
