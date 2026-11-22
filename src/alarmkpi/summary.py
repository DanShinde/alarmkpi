"""Plain text, Markdown and JSON summaries."""

from __future__ import annotations

import json
from typing import Any

from alarmkpi.analysis import Analysis
from alarmkpi.benchmarks import duration, kpis, overall
from alarmkpi.events import display_tag

MARK = {"good": "OK  ", "fair": "WARN", "poor": "BAD ", "n/a": "    "}
EMOJI = {"good": "🟢", "fair": "🟡", "poor": "🔴", "n/a": "⚪"}


def _period(a: Analysis) -> str:
    return f"{a.start:%Y-%m-%d %H:%M} to {a.end:%Y-%m-%d %H:%M} ({duration(a.end - a.start)})"


def text(a: Analysis, color: bool = False) -> str:
    items = kpis(a)
    paint = {"good": "32", "fair": "33", "poor": "31", "n/a": "2"}

    def c(status: str, s: str) -> str:
        return f"\033[{paint[status]}m{s}\033[0m" if color else s

    ops = a.settings.operators
    lines = [
        f"Alarm performance: {a.total:,} alarms, {_period(a)}"
        + (f", {ops} operator positions" if ops > 1 else ""),
        "",
    ]
    width = max(len(k.label) for k in items)
    for k in items:
        lines.append(
            f"  {c(k.status, MARK[k.status])}  {k.label:<{width}}  {k.value:>16}   target {k.target}"
        )
    lines += ["", f"Overall: {c(overall(items), overall(items).upper())}", ""]
    if a.tags:
        lines.append(f"Top {min(a.settings.top_n, len(a.tags))} alarms:")
        for t in a.tags[: a.settings.top_n]:
            lines.append(f"  {t.count:>6}  {t.share:5.1f}%  {display_tag(t.tag)}")
        lines.append("")
    if a.floods:
        lines.append(f"Floods ({len(a.floods)}):")
        for f in a.floods:
            top = ", ".join(f"{display_tag(tag)} ×{n}" for tag, n in f.top)
            lines.append(
                f"  {f.start:%Y-%m-%d %H:%M}  {duration(f.duration):>10}  {f.count:>5} alarms"
                f"  peak {f.peak_10min}/10 min  top: {top}"
            )
        lines.append("")
    if a.chattering:
        lines.append("Chattering:")
        for t in a.chattering:
            lines.append(f"  {t.max_per_minute:>3} in 1 min, {t.count} total  {display_tag(t.tag)}")
        lines.append("")
    for note in a.notes:
        lines.append(f"note: {note}")
    return "\n".join(lines).rstrip() + "\n"


def markdown(a: Analysis) -> str:
    items = kpis(a)
    out = [
        "## Alarm performance",
        "",
        f"{a.total:,} alarms, {_period(a)}. Overall: **{overall(items)}**",
        "",
        "| | Metric | Value | ISA-18.2 / EEMUA 191 target |",
        "| --- | --- | ---: | --- |",
    ]
    out += [f"| {EMOJI[k.status]} | {k.label} | {k.value} | {k.target} |" for k in items]
    if a.tags:
        out += ["", "### Top alarms", "", "| Count | Share | Alarm |", "| ---: | ---: | --- |"]
        out += [
            f"| {t.count} | {t.share:.1f}% | `{display_tag(t.tag)}` |"
            for t in a.tags[: a.settings.top_n]
        ]
    if a.floods:
        out += ["", "### Floods", "", "| Start | Duration | Alarms | Peak / 10 min |",
                "| --- | --- | ---: | ---: |"]  # fmt: skip
        out += [
            f"| {f.start:%Y-%m-%d %H:%M} | {duration(f.duration)} | {f.count} | {f.peak_10min} |"
            for f in a.floods
        ]
    return "\n".join(out) + "\n"


def to_dict(a: Analysis) -> dict[str, Any]:
    items = kpis(a)
    return {
        "start": a.start.isoformat(),
        "end": a.end.isoformat(),
        "alarms": a.total,
        "operators": a.settings.operators,
        "overall": overall(items),
        "kpis": [
            {
                "key": k.key,
                "label": k.label,
                "value": k.number,
                "display": k.value,
                "target": k.target,
                "status": k.status,
            }
            for k in items
        ],
        "top": [
            {"tag": t.tag, "count": t.count, "share": round(t.share, 2)}
            for t in a.tags[: a.settings.top_n]
        ],
        "floods": [
            {
                "start": f.start.isoformat(),
                "end": f.end.isoformat(),
                "alarms": f.count,
                "peak_10min": f.peak_10min,
                "top": [{"tag": t, "count": n} for t, n in f.top],
            }
            for f in a.floods
        ],
        "chattering": [
            {"tag": t.tag, "max_per_minute": t.max_per_minute, "count": t.count}
            for t in a.chattering
        ],
        "stale": [{"tag": x.tag, "since": x.time.isoformat()} for x in a.stale],
        "priorities": a.priorities,
        "notes": a.notes,
    }


def to_json(a: Analysis) -> str:
    return json.dumps(to_dict(a), indent=2, ensure_ascii=False) + "\n"
