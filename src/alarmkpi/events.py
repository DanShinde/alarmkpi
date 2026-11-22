"""Reading alarm journals (CSV) into a list of :class:`Event` objects.

Alarm systems export very different CSV layouts. Columns are found by name
(``EventTime``, ``Timestamp``, ``Source``, ``Tag``, ``State``, ``Priority`` ...)
and can always be given explicitly.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Kind = Literal["active", "clear", "ack", "other"]

TIME_NAMES = (
    "eventtime", "eventtimestamp", "timestamp", "time", "datetime", "date/time", "datetime",
    "activetime", "activationtime", "occurrencetime", "eventdate", "date",
)  # fmt: skip
TAG_NAMES = (
    "source", "sourcename", "sourcepath", "tag", "tagname", "alarm", "alarmname", "alarmid",
    "point", "pointname", "name", "conditionname", "module", "displaypath",
)  # fmt: skip
STATE_NAMES = (
    "eventstate", "state", "eventtype", "type", "action", "transition", "status",
    "alarmstate", "event",
)  # fmt: skip
PRIORITY_NAMES = ("priority", "severity", "pri", "prio", "level", "alarmpriority")
MESSAGE_NAMES = ("message", "description", "desc", "text", "label", "displaypath", "eventtext")
AREA_NAMES = ("area", "plantarea", "unit", "group", "console", "operator", "section")

ACTIVE_WORDS = {
    "active", "activated", "act", "alarm", "alm", "in", "raised", "on", "set", "1", "true",
    "activeunacked", "activeunack", "unackactive", "new", "occurred", "start", "begin",
}  # fmt: skip
CLEAR_WORDS = {
    "clear", "cleared", "rtn", "returntonormal", "normal", "out", "off", "reset", "0", "false",
    "inactive", "ok", "end", "cleared/rtn", "clearunacked", "clearacked",
}  # fmt: skip
ACK_WORDS = {"ack", "acked", "acknowledged", "acknowledge", "acknowledgement", "activeacked"}

TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y/%m/%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S.%f",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M",
    "%d.%m.%Y %H:%M:%S.%f",
    "%d.%m.%Y %H:%M:%S",
    "%a %b %d %H:%M:%S %Z %Y",
)


class JournalError(ValueError):
    """The CSV could not be understood as an alarm journal."""


@dataclass(frozen=True)
class Event:
    time: datetime
    tag: str
    kind: Kind
    priority: str = ""
    message: str = ""
    area: str = ""


@dataclass
class Columns:
    """Which CSV column holds what. ``None`` means "not present"."""

    time: str
    tag: str
    state: str | None = None
    priority: str | None = None
    message: str | None = None
    area: str | None = None


@dataclass
class Journal:
    events: list[Event]
    columns: Columns
    source: str = ""
    skipped: int = 0
    notes: list[str] = field(default_factory=list)


PRESETS: dict[str, dict[str, tuple[str, ...]]] = {
    # Ignition alarm journal: the Alarm Journal Table export or the alarm_events table
    # (where eventtype is 0 = active, 1 = clear, 2 = acknowledged).
    "ignition": {"time": ("EventTime",), "tag": ("Source",),
                 "state": ("EventState", "EventType"), "priority": ("Priority",),
                 "message": ("DisplayPath", "Label")},
    # The CSV that `alarmkpi demo` writes.
    "alarmkpi": {"time": ("Timestamp",), "tag": ("Tag",), "state": ("State",),
                 "priority": ("Priority",), "message": ("Message",), "area": ("Area",)},
}  # fmt: skip

PRESET_STATES: dict[str, dict[str, Kind]] = {
    "ignition": {"0": "active", "1": "clear", "2": "ack"},
}


def parse_state_map(spec: str) -> dict[str, Kind]:
    """``"0=active,1=clear,2=ack"`` -> mapping of raw state values to kinds."""
    out: dict[str, Kind] = {}
    for part in spec.split(","):
        if not part.strip():
            continue
        raw, _, kind = part.partition("=")
        kind = kind.strip().lower()
        if kind not in ("active", "clear", "ack", "other"):
            raise JournalError(f"bad state map entry {part!r}: use VALUE=active|clear|ack|other")
        out[_norm(raw)] = kind  # type: ignore[assignment]
    return out


def _norm(name: str) -> str:
    return re.sub(r"[\s_\-]", "", name.strip().lower())


def _find(headers: Sequence[str], names: Iterable[str], exclude: set[str]) -> str | None:
    by_norm = {_norm(h): h for h in headers if h not in exclude}
    for name in names:
        if name in by_norm:
            return by_norm[name]
    return None


def detect_columns(headers: Sequence[str], **given: str | None) -> Columns:
    """Pick columns by well-known names; explicit names always win."""
    missing = [v for v in given.values() if v and v not in headers]
    if missing:
        raise JournalError(f"column(s) not in the file: {', '.join(missing)}")
    used: set[str] = {v for v in given.values() if v}

    def pick(key: str, names: Iterable[str]) -> str | None:
        value = given.get(key)
        if value:
            return value
        found = _find(headers, names, used)
        if found:
            used.add(found)
        return found

    time = pick("time", TIME_NAMES)
    tag = pick("tag", TAG_NAMES)
    state = pick("state", STATE_NAMES)
    priority = pick("priority", PRIORITY_NAMES)
    message = pick("message", MESSAGE_NAMES)
    area = pick("area", AREA_NAMES)
    if time is None or tag is None:
        raise JournalError(
            "could not find the time and tag columns in "
            f"{list(headers)}; pass them with --time-col and --tag-col"
        )
    return Columns(time, tag, state, priority, message, area)


def classify(state: str) -> Kind:
    s = _norm(state)
    if s in ACTIVE_WORDS:
        return "active"
    if s in CLEAR_WORDS:
        return "clear"
    if s in ACK_WORDS or s.startswith("ack"):
        return "ack"
    if "clear" in s or "normal" in s or "rtn" in s:
        return "clear"
    if "active" in s or "alarm" in s:
        return "active"
    return "other"


def parse_time(value: str, fmt: str | None = None) -> datetime:
    value = value.strip()
    if fmt:
        return _naive(datetime.strptime(value, fmt))
    try:
        return _naive(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        pass
    for f in TIME_FORMATS:
        try:
            return _naive(datetime.strptime(value, f))
        except ValueError:
            continue
    if re.fullmatch(r"\d{12,14}(\.\d+)?", value):  # epoch milliseconds
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).replace(tzinfo=None)
    if re.fullmatch(r"\d{9,10}(\.\d+)?", value):  # epoch seconds
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
    raise ValueError(f"unrecognised time {value!r}; pass --time-format")


def _naive(dt: datetime) -> datetime:
    """Compare everything in one clock: aware times are converted to UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _sniff(text: str) -> csv.Dialect | type[csv.Dialect]:
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def read_text(
    text: str,
    *,
    source: str = "<text>",
    preset: str | None = None,
    time_format: str | None = None,
    state_map: dict[str, Kind] | None = None,
    **columns: str | None,
) -> Journal:
    """Parse CSV text into a :class:`Journal`."""
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text), dialect=_sniff(text))
    headers = reader.fieldnames or []
    if not headers:
        raise JournalError(f"{source}: empty file")
    given: dict[str, str | None] = {}
    states: dict[str, Kind] = {}
    if preset:
        lower = {h.lower(): h for h in headers}
        for key, names in PRESETS[preset].items():
            hit = next((lower[n.lower()] for n in names if n.lower() in lower), None)
            if hit:
                given[key] = hit
        states.update(PRESET_STATES.get(preset, {}))
    states.update(state_map or {})
    given.update({k: v for k, v in columns.items() if v})
    cols = detect_columns(headers, **given)
    events: list[Event] = []
    skipped = 0
    first_error = ""
    for row in reader:
        raw_time = (row.get(cols.time) or "").strip()
        tag = (row.get(cols.tag) or "").strip()
        if not raw_time or not tag:
            skipped += 1
            continue
        try:
            time = parse_time(raw_time, time_format)
        except ValueError as exc:
            skipped += 1
            first_error = first_error or str(exc)
            continue
        if cols.state:
            raw_state = row.get(cols.state) or ""
            kind: Kind = states.get(_norm(raw_state)) or classify(raw_state)
        else:
            kind = "active"
        events.append(
            Event(
                time=time,
                tag=tag,
                kind=kind,
                priority=(row.get(cols.priority) or "").strip() if cols.priority else "",
                message=(row.get(cols.message) or "").strip() if cols.message else "",
                area=(row.get(cols.area) or "").strip() if cols.area else "",
            )
        )
    if not events:
        detail = f" ({first_error})" if first_error else ""
        raise JournalError(f"{source}: no usable alarm events{detail}")
    events.sort(key=lambda e: e.time)
    journal = Journal(events, cols, source, skipped)
    if cols.state is None:
        journal.notes.append("no state column: every row counted as an alarm activation")
    if skipped:
        journal.notes.append(f"{skipped} row(s) skipped (missing or unreadable time/tag)")
    return journal


def read_csv(path: str | Path, **kwargs: Any) -> Journal:
    p = Path(path)
    raw = p.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    return read_text(text, source=str(p), **kwargs)


def display_tag(tag: str) -> str:
    """Shorten Ignition-style source paths: ``prov:default:/tag:A/B:/alm:Hi`` -> ``A/B: Hi``."""
    m = re.match(r"prov:[^:]*:/tag:(.*?)(?::/alm:(.*))?$", tag)
    if m:
        return m.group(1) + (f": {m.group(2)}" if m.group(2) else "")
    return tag
