"""ISA-18.2 / EEMUA 191 alarm performance metrics."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from alarmkpi.events import Event, Journal

TEN_MIN = timedelta(minutes=10)
HOUR = timedelta(hours=1)

PRIORITY_ORDER = ("critical", "high", "medium", "low", "diagnostic", "unknown")


def priority_class(value: str) -> str:
    """Map a priority / severity value onto critical/high/medium/low/diagnostic."""
    v = value.strip().lower()
    if not v:
        return "unknown"
    for word, cls in (
        ("crit", "critical"), ("urgent", "critical"), ("emerg", "critical"),
        ("high", "high"), ("med", "medium"), ("low", "low"), ("diag", "diagnostic"),
        ("info", "diagnostic"), ("warn", "low"),
    ):  # fmt: skip
        if word in v:
            return cls
    try:
        number = float(v)
    except ValueError:
        return "unknown"
    if number <= 4:  # Ignition: 0 Diagnostic, 1 Low, 2 Medium, 3 High, 4 Critical
        return ("diagnostic", "low", "medium", "high", "critical")[max(0, int(number))]
    if number <= 1000:  # FactoryTalk-style 1..1000 severity
        return ("low", "medium", "high", "critical")[min(3, int((number - 1) // 250))]
    return "unknown"


@dataclass
class Activation:
    tag: str
    time: datetime
    priority: str = "unknown"
    message: str = ""
    area: str = ""
    cleared: datetime | None = None
    acked: datetime | None = None

    @property
    def duration(self) -> timedelta | None:
        return self.cleared - self.time if self.cleared else None


@dataclass
class Flood:
    start: datetime
    end: datetime
    count: int
    peak_10min: int
    top: list[tuple[str, int]]

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass
class TagStat:
    tag: str
    count: int
    share: float
    message: str = ""
    priority: str = "unknown"
    max_per_minute: int = 0
    fleeting: int = 0
    longest: timedelta | None = None


@dataclass
class Settings:
    operators: int = 1
    flood_start: int = 10
    """A flood starts when a 10-minute period has more than this many alarms ..."""
    flood_end: int = 5
    """... and ends at the first 10-minute period with fewer than this many."""
    chatter_count: int = 3
    chatter_window: timedelta = timedelta(minutes=1)
    fleeting: timedelta = timedelta(seconds=1)
    stale: timedelta = timedelta(hours=24)
    top_n: int = 10


@dataclass
class Analysis:
    start: datetime
    end: datetime
    settings: Settings
    activations: list[Activation]
    buckets: list[tuple[datetime, int]]
    """Alarm count per 10-minute period (all operators)."""
    hourly: list[tuple[datetime, int]]
    daily: list[tuple[datetime, int]]
    tags: list[TagStat]
    floods: list[Flood]
    chattering: list[TagStat]
    fleeting: list[Activation]
    stale: list[Activation]
    standing: list[Activation]
    priorities: dict[str, int]
    ack_times: list[timedelta]
    notes: list[str] = field(default_factory=list)

    # ---- headline numbers -------------------------------------------------
    @property
    def total(self) -> int:
        return len(self.activations)

    @property
    def span(self) -> timedelta:
        return max(self.end - self.start, TEN_MIN)

    @property
    def per_operator(self) -> float:
        return self.total / self.settings.operators

    @property
    def per_day(self) -> float:
        return self.per_operator / (self.span / timedelta(days=1))

    @property
    def per_hour(self) -> float:
        return self.per_operator / (self.span / HOUR)

    @property
    def per_10min(self) -> float:
        return self.per_operator / (self.span / TEN_MIN)

    @property
    def max_10min(self) -> int:
        return max((n for _, n in self.buckets), default=0)

    @property
    def max_10min_per_operator(self) -> float:
        return self.max_10min / self.settings.operators

    @property
    def pct_10min_over_flood(self) -> float:
        if not self.buckets:
            return 0.0
        limit = self.settings.flood_start * self.settings.operators
        return 100.0 * sum(1 for _, n in self.buckets if n > limit) / len(self.buckets)

    @property
    def pct_hours_over_30(self) -> float:
        if not self.hourly:
            return 0.0
        limit = 30 * self.settings.operators
        return 100.0 * sum(1 for _, n in self.hourly if n > limit) / len(self.hourly)

    @property
    def pct_time_in_flood(self) -> float:
        flooded = sum((f.duration for f in self.floods), timedelta())
        return 100.0 * (flooded / self.span)

    @property
    def top_share(self) -> float:
        if not self.total:
            return 0.0
        return 100.0 * sum(t.count for t in self.tags[: self.settings.top_n]) / self.total

    @property
    def priority_shares(self) -> dict[str, float]:
        known = {k: v for k, v in self.priorities.items() if k != "unknown"}
        total = sum(known.values())
        if not total:
            return {}
        return {k: 100.0 * v / total for k, v in known.items()}

    @property
    def ack_median(self) -> timedelta | None:
        return _median(self.ack_times)


def _median(values: list[timedelta]) -> timedelta | None:
    if not values:
        return None
    return timedelta(seconds=statistics.median(v.total_seconds() for v in values))


def _floor(dt: datetime, step: timedelta) -> datetime:
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + ((dt - midnight) // step) * step


def _series(
    times: list[datetime], start: datetime, end: datetime, step: timedelta
) -> list[tuple[datetime, int]]:
    first = _floor(start, step)
    n = int((end - first) // step) + 1
    counts = [0] * n
    for t in times:
        counts[int((t - first) // step)] += 1
    return [(first + i * step, c) for i, c in enumerate(counts)]


def activations_from(events: list[Event]) -> tuple[list[Activation], list[str]]:
    """Pair activations with their clear and acknowledgement events."""
    acts: list[Activation] = []
    open_: dict[str, deque[Activation]] = defaultdict(deque)
    last: dict[str, Activation] = {}
    orphan_clears = 0
    for e in events:
        if e.kind == "active":
            a = Activation(e.tag, e.time, priority_class(e.priority), e.message, e.area)
            acts.append(a)
            open_[e.tag].append(a)
            last[e.tag] = a
        elif e.kind == "clear":
            queue = open_.get(e.tag)
            if queue:
                queue.popleft().cleared = e.time
            else:
                orphan_clears += 1
        elif e.kind == "ack":
            a_last = last.get(e.tag)
            if a_last is not None and a_last.acked is None:
                a_last.acked = e.time
    notes = []
    if orphan_clears:
        notes.append(f"{orphan_clears} clear event(s) without a preceding activation")
    return acts, notes


def analyze(
    journal: Journal | list[Event],
    settings: Settings | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Analysis:
    s = settings or Settings()
    events = (
        journal.events if isinstance(journal, Journal) else sorted(journal, key=lambda e: e.time)
    )
    notes = list(journal.notes) if isinstance(journal, Journal) else []
    acts, more = activations_from(events)
    notes += more
    if not events:
        raise ValueError("no events to analyze")
    t0 = start or events[0].time
    t1 = end or events[-1].time
    acts = [a for a in acts if t0 <= a.time <= t1]
    times = [a.time for a in acts]

    buckets = _series(times, t0, t1, TEN_MIN)
    hourly = _series(times, t0, t1, HOUR)
    daily = _series(times, t0, t1, timedelta(days=1))

    by_tag: dict[str, list[Activation]] = defaultdict(list)
    for a in acts:
        by_tag[a.tag].append(a)
    tag_stats: list[TagStat] = []
    for tag, items in by_tag.items():
        stat = TagStat(
            tag=tag,
            count=len(items),
            share=100.0 * len(items) / len(acts),
            message=next((a.message for a in items if a.message), ""),
            priority=Counter(a.priority for a in items).most_common(1)[0][0],
            max_per_minute=_max_in_window([a.time for a in items], s.chatter_window),
            fleeting=sum(1 for a in items if a.duration is not None and a.duration < s.fleeting),
            longest=max((a.duration for a in items if a.duration is not None), default=None),
        )
        tag_stats.append(stat)
    tag_stats.sort(key=lambda t: (-t.count, t.tag))

    stale: list[Activation] = []
    standing: list[Activation] = []
    has_clears = any(e.kind == "clear" for e in events)
    if not has_clears:
        notes.append("no clear events: stale, standing and fleeting alarms not evaluated")
    for a in acts if has_clears else []:
        if a.cleared is None:
            standing.append(a)
            if t1 - a.time > s.stale:
                stale.append(a)
        elif a.cleared - a.time > s.stale:
            stale.append(a)

    return Analysis(
        start=t0,
        end=t1,
        settings=s,
        activations=acts,
        buckets=buckets,
        hourly=hourly,
        daily=daily,
        tags=tag_stats,
        floods=_floods(buckets, acts, s),
        chattering=[t for t in tag_stats if t.max_per_minute >= s.chatter_count],
        fleeting=[a for a in acts if a.duration is not None and a.duration < s.fleeting],
        stale=stale,
        standing=standing,
        priorities=dict(Counter(a.priority for a in acts)),
        ack_times=[a.acked - a.time for a in acts if a.acked is not None],
        notes=notes,
    )


def _max_in_window(times: list[datetime], window: timedelta) -> int:
    best = 0
    lo = 0
    for hi, t in enumerate(times):
        while t - times[lo] > window:
            lo += 1
        best = max(best, hi - lo + 1)
    return best


def _floods(
    buckets: list[tuple[datetime, int]], acts: list[Activation], s: Settings
) -> list[Flood]:
    """ISA-18.2: a flood starts above ``flood_start`` per 10 min per operator and ends below
    ``flood_end``."""
    start_limit = s.flood_start * s.operators
    end_limit = s.flood_end * s.operators
    spans: list[tuple[datetime, datetime, int]] = []
    current: datetime | None = None
    peak = 0
    for t, n in buckets:
        if current is None and n > start_limit:
            current, peak = t, n
        elif current is not None:
            if n < end_limit:
                spans.append((current, t, peak))
                current = None
            else:
                peak = max(peak, n)
    if current is not None:
        spans.append((current, buckets[-1][0] + TEN_MIN, peak))
    floods = []
    for f_start, f_end, f_peak in spans:
        inside = [a for a in acts if f_start <= a.time < f_end]
        top = Counter(a.tag for a in inside).most_common(3)
        floods.append(Flood(f_start, f_end, len(inside), f_peak, top))
    return floods
