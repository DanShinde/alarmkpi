from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from alarmkpi.events import (
    JournalError,
    classify,
    detect_columns,
    display_tag,
    parse_state_map,
    parse_time,
    read_csv,
    read_text,
)


@pytest.mark.parametrize(
    ("state", "kind"),
    [
        ("Active", "active"), ("ACTIVE", "active"), ("Alarm", "active"), ("1", "active"),
        ("Clear", "clear"), ("RTN", "clear"), ("Return to normal", "clear"), ("0", "clear"),
        ("Cleared, Unacked", "clear"), ("Acknowledged", "ack"), ("Ack", "ack"),
        ("Shelved", "other"),
    ],
)  # fmt: skip
def test_classify(state: str, kind: str) -> None:
    assert classify(state) == kind


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-16 06:10:18.788", datetime(2026, 11, 16, 6, 10, 18, 788000)),
        ("2026-11-16T06:10:18Z", datetime(2026, 11, 16, 6, 10, 18)),
        ("2026-11-16T07:10:18+01:00", datetime(2026, 11, 16, 6, 10, 18)),
        ("11/16/2026 06:10:18", datetime(2026, 11, 16, 6, 10, 18)),
        ("11/16/2026 6:10:18 AM", datetime(2026, 11, 16, 6, 10, 18)),
        ("16.11.2026 06:10:18", datetime(2026, 11, 16, 6, 10, 18)),
        ("1794809418000", datetime(2026, 11, 16, 6, 10, 18)),
        ("1794809418", datetime(2026, 11, 16, 6, 10, 18)),
    ],
)
def test_parse_time(value: str, expected: datetime) -> None:
    assert parse_time(value) == expected


def test_parse_time_explicit_format_and_error() -> None:
    assert parse_time("16/11/2026 06:10", "%d/%m/%Y %H:%M") == datetime(2026, 11, 16, 6, 10)
    with pytest.raises(ValueError, match="time-format"):
        parse_time("yesterday")


def test_detect_columns_by_common_names() -> None:
    cols = detect_columns(["Event Time", "Source Name", "Event_State", "Severity", "Description"])
    assert (cols.time, cols.tag, cols.state, cols.priority, cols.message) == (
        "Event Time", "Source Name", "Event_State", "Severity", "Description",
    )  # fmt: skip


def test_detect_columns_errors() -> None:
    with pytest.raises(JournalError, match="--time-col"):
        detect_columns(["foo", "bar"])
    with pytest.raises(JournalError, match="not in the file"):
        detect_columns(["Time", "Tag"], state="Nope")


def test_ignition_style_export() -> None:
    text = (
        "EventId,Source,DisplayPath,Priority,EventTime,EventState,EventFlags\n"
        "a1,prov:default:/tag:Line1/Pump1:/alm:High,Pump 1 high,3,2026-11-16 08:00:00,0,0\n"
    )
    j = read_text(text, preset="ignition")
    assert j.columns.state == "EventState"
    # Ignition's alarm_events table stores the state as a number: 0 active, 1 clear, 2 ack.
    assert j.events[0].kind == "active"
    assert display_tag(j.events[0].tag) == "Line1/Pump1: High"


def test_no_state_column_means_every_row_is_an_alarm() -> None:
    j = read_text("Time;Tag\n2026-11-16 08:00:00;A\n2026-11-16 08:00:05;B\n")
    assert [e.kind for e in j.events] == ["active", "active"]
    assert "no state column" in j.notes[0]


def test_bad_rows_skipped_and_sorted() -> None:
    j = read_text(
        "Timestamp,Tag,State\n2026-11-16 09:00:00,A,Active\nnope,B,Active\n,C,Active\n"
        "2026-11-16 08:00:00,D,Active\n"
    )
    assert [e.tag for e in j.events] == ["D", "A"]
    assert j.skipped == 2


def test_nothing_usable() -> None:
    with pytest.raises(JournalError, match="no usable"):
        read_text("Timestamp,Tag\nnope,A\n")
    with pytest.raises(JournalError, match="empty"):
        read_text("")


def test_read_csv_cp1252_and_bom(tmp_path: Path) -> None:
    p = tmp_path / "j.csv"
    p.write_bytes(
        "Timestamp,Tag,Message\n2026-11-16 08:00:00,A,Température haute\n".encode("cp1252")
    )
    assert read_csv(p).events[0].message == "Température haute"
    p.write_bytes("﻿Timestamp,Tag\n2026-11-16 08:00:00,A\n".encode())
    assert read_csv(p).columns.time == "Timestamp"


def test_display_tag_passthrough() -> None:
    assert display_tag("FIC-101.HI") == "FIC-101.HI"


def test_ignition_alarm_events_table_and_state_map() -> None:
    text = (
        "id,eventid,source,displaypath,priority,eventtype,eventflags,eventtime\n"
        "1,a,prov:p:/tag:T1:/alm:Hi,T1 high,2,0,0,2026-11-16 08:00:00\n"
        "2,a,prov:p:/tag:T1:/alm:Hi,T1 high,2,2,0,2026-11-16 08:00:30\n"
        "3,a,prov:p:/tag:T1:/alm:Hi,T1 high,2,1,0,2026-11-16 08:01:00\n"
    )
    j = read_text(text, preset="ignition")
    assert [e.kind for e in j.events] == ["active", "ack", "clear"]
    assert j.events[0].message == "T1 high"
    j2 = read_text(
        "Time,Tag,Code\n2026-11-16 08:00:00,A,ON\n",
        state_map=parse_state_map("on=clear"),
        state="Code",
    )
    assert j2.events[0].kind == "clear"
    with pytest.raises(JournalError, match="bad state map"):
        parse_state_map("x=maybe")
