"""Injectable clocks (timezone-aware UTC). Defined in ``ids.py`` since M1; re-exported here
under the protocol-pack module name."""

from netcoop.core.ids import Clock, FixedClock, SystemClock

__all__ = ["Clock", "FixedClock", "SystemClock"]
