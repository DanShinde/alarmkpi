from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from alarmkpi import Event, Settings, analyze, read_csv
from alarmkpi.analysis import activations_from, priority_class
from alarmkpi.benchmarks import duration, kpis, overall

T0 = datetime(2026, 11, 16, 8, 0)


def ev(sec: float, tag: str, kind: str = "active", priority: str = "") -> Event:
    return Event(T0 + timedelta(seconds=sec), tag, kind, priority)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "cls"),
    [
        ("Low", "low"), ("MEDIUM", "medium"), ("Med", "medium"), ("High", "high"),
        ("Critical", "critical"), ("Urgent", "critical"), ("Diagnostic", "diagnostic"),
        ("0", "diagnostic"), ("1", "low"), ("3", "high"), ("4", "critical"),
        ("100", "low"), ("300", "medium"), ("700", "high"), ("900", "critical"),
        ("", "unknown"), ("P9000", "unknown"), ("5000", "unknown"),
    ],
)  # fmt: skip
def test_priority_class(value: str, cls: str) -> None:
    assert priority_class(value) == cls


def test_pairing_clear_and_ack() -> None:
    acts, notes = activations_from(
        [ev(0, "A"), ev(10, "A", "ack"), ev(30, "A", "clear"), ev(40, "B", "clear")]
    )
    assert acts[0].duration == timedelta(seconds=30)
    assert acts[0].acked == T0 + timedelta(seconds=10)
    assert notes == ["1 clear event(s) without a preceding activation"]


def test_rates_and_operators() -> None:
    events = [ev(i * 60, f"T{i % 7}") for i in range(120)]  # 120 alarms in 2 hours
    a = analyze(events)
    assert a.total == 120
    assert a.per_hour == pytest.approx(120 / (119 / 60), rel=1e-6)
    b = analyze(events, Settings(operators=2))
    assert b.per_hour == pytest.approx(a.per_hour / 2)


def test_flood_detection_isa_definition() -> None:
    # 10 quiet minutes, 25 alarms in the next 10, 6 the next 10 (still flood), then 1.
    events = [ev(30, "Q")]
    events += [ev(600 + i * 20, f"F{i}") for i in range(25)]
    events += [ev(1200 + i * 90, f"G{i}") for i in range(6)]
    events += [ev(1800 + 60, "Z")]
    a = analyze(events)
    (flood,) = a.floods
    assert flood.start == T0 + timedelta(minutes=10)
    assert flood.end == T0 + timedelta(minutes=30)
    assert flood.count == 31
    assert flood.peak_10min == 25
    assert a.max_10min == 25
    assert a.pct_10min_over_flood == pytest.approx(25.0)


def test_flood_until_end_of_data() -> None:
    a = analyze([ev(i, f"T{i}") for i in range(15)])
    assert len(a.floods) == 1


def test_chattering_fleeting_stale_standing() -> None:
    events = [
        ev(0, "CHAT"), ev(1, "CHAT", "clear"), ev(20, "CHAT"), ev(21, "CHAT", "clear"),
        ev(40, "CHAT"), ev(41, "CHAT", "clear"),
        ev(100, "FLEET"), ev(100.3, "FLEET", "clear"),
        ev(200, "STALE"),
        ev(300, "LONG"), ev(300 + 30 * 3600, "LONG", "clear"),
        ev(40 * 3600, "LAST"),
    ]  # fmt: skip
    a = analyze(events)
    assert [t.tag for t in a.chattering] == ["CHAT"]
    assert a.chattering[0].max_per_minute == 3
    assert [x.tag for x in a.fleeting] == ["FLEET"]
    assert sorted(x.tag for x in a.stale) == ["LONG", "STALE"]
    assert sorted(x.tag for x in a.standing) == ["LAST", "STALE"]


def test_top_share_and_window_filter() -> None:
    events = [ev(i, "A") for i in range(0, 600, 60)] + [ev(700, "B")]
    a = analyze(events, Settings(top_n=1))
    assert a.tags[0].tag == "A"
    assert a.top_share == pytest.approx(100 * 10 / 11)
    b = analyze(events, start=T0 + timedelta(seconds=650))
    assert b.total == 1


def test_benchmarks_on_demo(demo_csv: Path) -> None:
    a = analyze(read_csv(demo_csv))
    by = {k.key: k for k in kpis(a)}
    assert by["per_day"].status == "good"
    assert by["max_10min"].status == "poor"
    assert by["chattering"].status == "poor"
    assert by["fleeting"].number == 9
    assert by["stale"].number == 2
    assert by["priority"].status == "poor"
    assert "ack_median" in by
    assert overall(kpis(a)) == "poor"
    assert len(a.floods) == 1
    assert a.floods[0].start == datetime(2026, 11, 19, 14, 20)


def test_overall_good() -> None:
    events = [ev(i * 3600, f"T{i}", priority="Low") for i in range(48)]
    a = analyze(events)
    assert "no clear events" in a.notes[-1]
    assert not a.stale
    good = [k for k in kpis(a) if k.key != "top10"]
    assert overall(good) == "good"


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(3.25, "3.2 s"), (42, "42 s"), (125, "2 min 05 s"), (7260, "2 h 01 min"),
     (90000, "1 d 1 h")],
)  # fmt: skip
def test_duration(seconds: float, text: str) -> None:
    assert duration(timedelta(seconds=seconds)) == text
