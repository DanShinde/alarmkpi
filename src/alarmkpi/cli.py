"""``alarmkpi report`` and ``alarmkpi demo``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from alarmkpi import __version__
from alarmkpi.analysis import Settings, analyze
from alarmkpi.benchmarks import kpis, overall
from alarmkpi.demo import write_csv
from alarmkpi.events import PRESETS, JournalError, parse_state_map, parse_time, read_csv
from alarmkpi.report import html
from alarmkpi.summary import markdown, text, to_json

RANK = {"good": 0, "fair": 1, "poor": 2}


def _color(choice: str) -> bool:
    if choice == "always":
        return True
    if choice == "never" or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _write(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")
    print(f"wrote {path}", file=sys.stderr)


def cmd_report(args: argparse.Namespace) -> int:
    try:
        journal = read_csv(
            args.journal,
            preset=args.preset,
            state_map=parse_state_map(args.state_map) if args.state_map else None,
            time_format=args.time_format,
            time=args.time_col,
            tag=args.tag_col,
            state=args.state_col,
            priority=args.priority_col,
            message=args.message_col,
            area=args.area_col,
        )
        start = parse_time(args.start) if args.start else None
        end = parse_time(args.end) if args.end else None
    except (JournalError, OSError, ValueError) as exc:
        print(f"alarmkpi: {exc}", file=sys.stderr)
        return 2
    if args.area:
        journal.events = [e for e in journal.events if e.area in args.area]
        if not journal.events:
            print(f"alarmkpi: no events in area(s) {', '.join(args.area)}", file=sys.stderr)
            return 2
    settings = Settings(
        operators=args.operators,
        chatter_count=args.chatter_count,
        chatter_window=timedelta(seconds=args.chatter_window),
        fleeting=timedelta(seconds=args.fleeting),
        stale=timedelta(hours=args.stale_hours),
        top_n=args.top,
    )
    try:
        a = analyze(journal, settings, start=start, end=end)
    except ValueError as exc:
        print(f"alarmkpi: {exc}", file=sys.stderr)
        return 2
    if args.html:
        _write(args.html, html(a, title=args.title, source=Path(args.journal).name))
    if args.markdown:
        _write(args.markdown, markdown(a))
    if args.json:
        _write(args.json, to_json(a))
    if not args.quiet:
        sys.stdout.write(text(a, color=_color(args.color)))
    if args.fail_on and RANK.get(overall(kpis(a)), 0) >= RANK[args.fail_on]:
        return 1
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    n = write_csv(args.output, days=args.days)
    print(f"wrote {args.output} ({n} events, {args.days} days)", file=sys.stderr)
    print(f"next: alarmkpi report {args.output} --html report.html", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="alarmkpi",
        description="ISA-18.2 / EEMUA 191 alarm performance KPIs from alarm journal CSV exports.",
    )
    p.add_argument("--version", action="version", version=f"alarmkpi {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("report", help="analyze an alarm journal CSV")
    r.add_argument("journal", help="CSV export of the alarm journal / event log")
    out = r.add_argument_group("output")
    out.add_argument("--html", metavar="FILE", help="write the HTML report")
    out.add_argument("--markdown", metavar="FILE", help="write a Markdown summary")
    out.add_argument("--json", metavar="FILE", help="write all metrics as JSON")
    out.add_argument("--title", default="Alarm performance report")
    out.add_argument("-q", "--quiet", action="store_true", help="no text summary on stdout")
    out.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    out.add_argument(
        "--fail-on",
        choices=["fair", "poor"],
        help="exit 1 when the overall rating is this bad or worse (for CI/scheduled checks)",
    )
    cols = r.add_argument_group("columns (found automatically when omitted)")
    cols.add_argument("--preset", choices=sorted(PRESETS), help="known export layout")
    cols.add_argument("--time-col")
    cols.add_argument("--tag-col")
    cols.add_argument("--state-col", help="Active/Clear/Ack; without it every row is an alarm")
    cols.add_argument(
        "--state-map", metavar="MAP", help="raw state values, e.g. '0=active,1=clear,2=ack'"
    )
    cols.add_argument("--priority-col")
    cols.add_argument("--message-col")
    cols.add_argument("--area-col")
    cols.add_argument("--time-format", help="strptime format, e.g. '%%d/%%m/%%Y %%H:%%M:%%S'")
    an = r.add_argument_group("analysis")
    an.add_argument("--operators", type=int, default=1, help="operator positions (default 1)")
    an.add_argument("--area", action="append", help="only this area (repeatable)")
    an.add_argument("--start", help="ignore alarms before this time")
    an.add_argument("--end", help="ignore alarms after this time")
    an.add_argument("--chatter-count", type=int, default=3, metavar="N")
    an.add_argument("--chatter-window", type=float, default=60, metavar="SECONDS")
    an.add_argument("--fleeting", type=float, default=1, metavar="SECONDS")
    an.add_argument("--stale-hours", type=float, default=24)
    an.add_argument("--top", type=int, default=10, help="size of the bad-actor list")
    r.set_defaults(func=cmd_report)

    d = sub.add_parser("demo", help="write a realistic one-week sample journal")
    d.add_argument("-o", "--output", default="demo_journal.csv")
    d.add_argument("--days", type=int, default=7)
    d.set_defaults(func=cmd_demo)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = args.func(args)
    return code
