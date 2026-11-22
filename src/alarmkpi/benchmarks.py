"""Compare the metrics with the ISA-18.2 / EEMUA 191 performance targets.

The figures are the commonly published ANSI/ISA-18.2 (Table "Recommended alarm
performance metrics") and EEMUA 191 targets for one operator position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from alarmkpi.analysis import Analysis

Status = Literal["good", "fair", "poor", "n/a"]


@dataclass
class Kpi:
    key: str
    label: str
    value: str
    target: str
    status: Status
    number: float | None = None


def _band(x: float, good: float, fair: float) -> Status:
    if x <= good:
        return "good"
    if x <= fair:
        return "fair"
    return "poor"


def _fmt(x: float) -> str:
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.0f}" if x >= 100 else f"{x:,.1f}" if x >= 10 else f"{x:,.2f}"


def kpis(a: Analysis) -> list[Kpi]:
    out = [
        Kpi("per_day", "Alarms per operator per day", _fmt(a.per_day),
            "≈150 acceptable, ≈300 max manageable", _band(a.per_day, 150, 300), a.per_day),
        Kpi("per_hour", "Alarms per operator per hour", _fmt(a.per_hour),
            "≈6 acceptable, ≈12 max manageable", _band(a.per_hour, 6, 12), a.per_hour),
        Kpi("per_10min", "Alarms per operator per 10 min", _fmt(a.per_10min),
            "≈1 acceptable, ≈2 max manageable", _band(a.per_10min, 1, 2), a.per_10min),
        Kpi("max_10min", "Peak alarms in 10 minutes", _fmt(a.max_10min_per_operator),
            "≤10", _band(a.max_10min_per_operator, 10, 10), a.max_10min_per_operator),
        Kpi("pct_10min_flood", "10-min periods in flood (>10 alarms)",
            f"{a.pct_10min_over_flood:.1f}%", "<1%",
            _band(a.pct_10min_over_flood, 1, 1), a.pct_10min_over_flood),
        Kpi("pct_hours_30", "Hours with more than 30 alarms", f"{a.pct_hours_over_30:.1f}%",
            "<1%", _band(a.pct_hours_over_30, 1, 1), a.pct_hours_over_30),
        Kpi("time_in_flood", "Time in flood", f"{a.pct_time_in_flood:.1f}%", "<1%",
            _band(a.pct_time_in_flood, 1, 1), a.pct_time_in_flood),
        Kpi("top10", f"Top {a.settings.top_n} alarms share of total", f"{a.top_share:.1f}%",
            "≈1% to 5% max", _band(a.top_share, 1, 5) if a.tags else "n/a", a.top_share),
        Kpi("chattering", "Chattering alarms", str(len(a.chattering)), "0",
            _band(len(a.chattering), 0, 0), len(a.chattering)),
        Kpi("fleeting", "Fleeting alarm activations", str(len(a.fleeting)), "0",
            _band(len(a.fleeting), 0, 0), len(a.fleeting)),
        Kpi("stale", "Stale alarms (active > 24 h)", str(len({x.tag for x in a.stale})), "<5",
            _band(len({x.tag for x in a.stale}), 4, 4), len({x.tag for x in a.stale})),
    ]  # fmt: skip
    shares = a.priority_shares
    if shares:
        low = shares.get("low", 0.0)
        high = shares.get("high", 0.0) + shares.get("critical", 0.0)
        status: Status = (
            "good" if low >= 70 and high <= 10 else "fair" if low >= 50 and high <= 20 else "poor"
        )
        out.append(
            Kpi("priority", "Priority mix (low / medium / high)",
                f"{low:.0f}% / {shares.get('medium', 0.0):.0f}% / {high:.0f}%",
                "≈80% / 15% / 5%", status, low)
        )  # fmt: skip
    median = a.ack_median
    if median is not None:
        secs = median.total_seconds()
        out.append(
            Kpi("ack_median", "Median time to acknowledge", _duration(median), "context dependent",
                "n/a", secs)
        )  # fmt: skip
    return out


def _duration(td: object) -> str:
    from datetime import timedelta

    assert isinstance(td, timedelta)
    s = int(td.total_seconds())
    if s < 60:
        return f"{td.total_seconds():.1f} s" if s < 10 else f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    if s < 86400:
        return f"{s // 3600} h {s % 3600 // 60:02d} min"
    return f"{s // 86400} d {s % 86400 // 3600} h"


duration = _duration


def overall(items: list[Kpi]) -> Status:
    statuses = [k.status for k in items if k.status != "n/a"]
    if "poor" in statuses:
        return "poor"
    if "fair" in statuses:
        return "fair"
    return "good"
