"""A realistic, reproducible week of alarm journal for demos and tests."""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# (tag, message, priority, area, relative frequency)
TAGS = [
    ("FW-LT-101.LO", "Feedwater tank level low", "Medium", "Feedwater", 8),
    ("FW-PT-110.HI", "Feedwater pump discharge pressure high", "High", "Feedwater", 3),
    ("FW-P-102.FLT", "Feedwater pump 2 fault", "High", "Feedwater", 1),
    ("BLR-TT-201.HI", "Boiler outlet temperature high", "High", "Boiler", 4),
    ("BLR-PT-202.HI", "Steam drum pressure high", "High", "Boiler", 3),
    ("BLR-AT-205.HI", "Flue gas O2 high", "Low", "Boiler", 9),
    ("BLR-AT-206.LO", "Flue gas O2 low", "Medium", "Boiler", 4),
    ("BLR-FT-210.LO", "Fuel gas flow low", "Medium", "Boiler", 2),
    ("BLR-BMS-01", "Burner management trip", "Critical", "Boiler", 0.2),
    ("TB-VT-210.HI", "Turbine bearing 2 vibration high", "High", "Turbine", 2),
    ("TB-TT-220.HI", "Turbine lube oil temperature high", "Medium", "Turbine", 3),
    ("TB-PT-221.LO", "Turbine lube oil pressure low", "High", "Turbine", 1),
    ("TB-ST-230.HI", "Turbine speed high", "Critical", "Turbine", 0.3),
    ("CW-TT-305.HI", "Cooling water return temperature high", "Low", "Cooling", 5),
    ("CW-FT-310.LO", "Cooling water flow low", "Medium", "Cooling", 3),
    ("CW-P-301.FLT", "Cooling water pump 1 fault", "High", "Cooling", 0.5),
    ("CW-LT-320.LO", "Cooling tower basin level low", "Low", "Cooling", 6),
    ("CMP-PT-401.LO", "Instrument air pressure low", "High", "Compressor", 2),
    ("CMP-TT-402.HI", "Compressor discharge temperature high", "Medium", "Compressor", 3),
    ("CMP-K-401.TRIP", "Air compressor K-401 trip", "Critical", "Compressor", 0.1),
    ("CMP-DP-405.HI", "Inlet filter differential pressure high", "Low", "Compressor", 7),
    ("WT-AT-501.HI", "Boiler water conductivity high", "Low", "Water treatment", 10),
    ("WT-AT-502.LO", "Phosphate dosing low", "Low", "Water treatment", 6),
    ("WT-LT-510.LO", "Chemical tank level low", "Low", "Water treatment", 4),
    ("WT-PH-520.HI", "Condensate pH high", "Low", "Water treatment", 0),
    ("EL-HTR-07.FLT", "Panel 7 anti-condensation heater fault", "Low", "Electrical", 0),
    ("EL-UPS-01", "UPS on battery", "High", "Electrical", 0.3),
    ("EL-MCC-02.FLT", "MCC-2 feeder fault", "Medium", "Electrical", 0.5),
]

# Everything that alarms when the instrument air compressor trips.
FLOOD_TAGS = [
    "CMP-K-401.TRIP", "CMP-PT-401.LO", "FW-PT-110.HI", "FW-LT-101.LO", "BLR-FT-210.LO",
    "BLR-AT-206.LO", "BLR-PT-202.HI", "TB-TT-220.HI", "CW-FT-310.LO", "BLR-TT-201.HI",
    "BLR-BMS-01", "TB-PT-221.LO", "CW-TT-305.HI", "FW-P-102.FLT",
]  # fmt: skip

META = {t[0]: t for t in TAGS}
HEADER = ["Timestamp", "Tag", "Message", "Priority", "State", "Area"]


def generate(
    start: datetime = datetime(2026, 11, 16, 6, 0), days: int = 7, seed: int = 18_2
) -> list[tuple[datetime, str, str]]:
    """Return (time, tag, state) rows: Active / Clear / Ack."""
    rng = random.Random(seed)
    end = start + timedelta(days=days)
    rows: list[tuple[datetime, str, str]] = []

    def alarm(t: datetime, tag: str, on_for: float, ack_after: float | None = None) -> None:
        rows.append((t, tag, "Active"))
        if ack_after is None:
            ack_after = rng.uniform(15, 240)
        rows.append((t + timedelta(seconds=ack_after), tag, "Ack"))
        if on_for >= 0:
            rows.append((t + timedelta(seconds=on_for), tag, "Clear"))

    # Background: about 5 alarms an hour, busier in the day shift.
    tags = [t[0] for t in TAGS]
    weights = [t[4] for t in TAGS]
    t = start
    while t < end:
        rate = 7.0 if 8 <= t.hour < 18 else 3.5
        t += timedelta(hours=rng.expovariate(rate))
        if t >= end:
            break
        alarm(t, rng.choices(tags, weights)[0], rng.uniform(30, 1800))

    # Chattering level switch on day 2: bursts of 4-6 activations within a minute.
    for _ in range(14):
        burst = start + timedelta(days=1, hours=rng.uniform(1, 22))
        for k in range(rng.randint(4, 6)):
            alarm(burst + timedelta(seconds=k * rng.uniform(6, 11)), "FW-LT-101.LO", 4, 30)

    # Fleeting vibration alarm: active for a fraction of a second.
    for _ in range(9):
        at = start + timedelta(days=rng.uniform(2, 6))
        alarm(at, "TB-VT-210.HI", rng.uniform(0.2, 0.8), 40)

    # Alarm flood on day 4: the instrument air compressor trips and most of the
    # plant follows within half an hour, each alarm once or a few times.
    trip = start + timedelta(days=3, hours=8, minutes=20)
    alarm(trip, "CMP-K-401.TRIP", 2400)
    for tag in FLOOD_TAGS[1:] + rng.sample(
        [t for t, w in zip(tags, weights, strict=False) if w], 12
    ):
        first = trip + timedelta(seconds=rng.expovariate(1 / 420))
        for k in range(rng.choice((1, 1, 2, 3))):
            at = first + timedelta(seconds=k * rng.uniform(70, 300))
            alarm(at, tag, rng.uniform(20, 60))

    # Stale alarms: active for days, nobody fixes them.
    alarm(start + timedelta(hours=2, minutes=13), "WT-PH-520.HI", -1, 120)
    alarm(start + timedelta(days=2, hours=5), "EL-HTR-07.FLT", 3.5 * 86400, 300)

    rows.sort(key=lambda r: r[0])
    return rows


def write_csv(path: str | Path, **kwargs: object) -> int:
    rows = generate(**kwargs)  # type: ignore[arg-type]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for t, tag, state in rows:
            _, message, priority, area, _ = META[tag]
            w.writerow(
                [t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], tag, message, priority, state, area]
            )
    return len(rows)
