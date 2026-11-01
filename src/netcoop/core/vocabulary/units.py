"""Unit registry over the ``unit``, ``dimension`` and ``metric`` vocabularies.

Conversion only happens inside one dimension. A unit must be declared: an empty or unknown
unit is an error, so 0.94 is never silently read as 94 percent (or the reverse).
"""

from __future__ import annotations

from netcoop.core.vocabulary.registry import Term, get_vocabulary


class UnitError(ValueError):
    pass


class UnknownUnitError(UnitError):
    pass


class DimensionMismatchError(UnitError):
    pass


def unit(name: str) -> Term:
    """Resolve a unit by id (``millisecond``) or a listed spelling (``ms``)."""
    for t in get_vocabulary("unit").terms:
        if name == t.id or name in t.attributes.get("spellings", []):
            return t
    raise UnknownUnitError(
        f"unknown unit {name!r}: declare one of the units in config/vocabulary/unit.toml"
    )


def convert(value: float, from_unit: str, to_unit: str) -> float:
    src, dst = unit(from_unit), unit(to_unit)
    if src.attributes["dimension"] != dst.attributes["dimension"]:
        raise DimensionMismatchError(
            f"cannot convert {src.id} ({src.attributes['dimension']}) to "
            f"{dst.id} ({dst.attributes['dimension']})"
        )
    return float(value) * float(src.attributes["factor"]) / float(dst.attributes["factor"])


def metric_dimension(metric: str) -> str:
    return str(get_vocabulary("metric").term(metric).attributes["dimension"])


def unit_fits_metric(metric: str, unit_name: str) -> bool:
    """True if ``unit_name`` is a known unit in the metric's dimension."""
    try:
        return str(unit(unit_name).attributes["dimension"]) == metric_dimension(metric)
    except (UnknownUnitError, ValueError):
        return False
