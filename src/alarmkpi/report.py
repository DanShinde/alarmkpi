"""A single-file HTML report: no JavaScript, no external assets, prints well."""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from alarmkpi import __version__
from alarmkpi.analysis import PRIORITY_ORDER, Analysis
from alarmkpi.benchmarks import Kpi, duration, kpis, overall
from alarmkpi.events import display_tag

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--muted:#677084;--line:#e3e6ec;
--good:#1f9d55;--fair:#d69e2e;--poor:#d64545;--bar:#4c7bd9;--flood:rgba(214,69,69,.18);
--goodbg:#e8f6ee;--fairbg:#fdf5e2;--poorbg:#fbeaea}
@media (prefers-color-scheme:dark){:root{--bg:#0f1218;--card:#171b23;--ink:#e6e9ef;
--muted:#97a0b3;--line:#2a303c;--bar:#6b95ec;--flood:rgba(240,100,100,.16);
--goodbg:#13281d;--fairbg:#2c2513;--poorbg:#2e1717}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px}
.sub{color:var(--muted)}.badge{display:inline-block;padding:2px 10px;border-radius:99px;
font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.03em}
.good{color:var(--good)}.fair{color:var(--fair)}.poor{color:var(--poor)}
.badge.good{background:var(--goodbg)}.badge.fair{background:var(--fairbg)}
.badge.poor{background:var(--poorbg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);
border-radius:8px;padding:12px 14px}.kpi.good{border-left-color:var(--good)}
.kpi.fair{border-left-color:var(--fair)}.kpi.poor{border-left-color:var(--poor)}
.kpi .v{font-size:24px;font-weight:700;color:var(--ink)}.kpi .l{color:var(--ink);font-weight:500}
.kpi .t{color:var(--muted);font-size:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px}
svg{width:100%;height:auto;display:block}svg text{fill:var(--muted);font-size:11px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:6px 8px;
border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:500;
font-size:12px}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.meter{height:8px;background:var(--line);border-radius:4px;min-width:80px}
.meter>span{display:block;height:8px;border-radius:4px;background:var(--bar)}
code{font-size:12.5px}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:760px){.two{grid-template-columns:1fr}}
.legend{color:var(--muted);font-size:12px;margin-top:6px}
.stack{display:flex;height:22px;border-radius:5px;overflow:hidden;margin:6px 0}
.stack span{display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;
white-space:nowrap;overflow:hidden}
footer{margin-top:40px;color:var(--muted);font-size:12px}
"""

PRIORITY_COLORS = {
    "critical": "#7b2cbf", "high": "#d64545", "medium": "#d69e2e", "low": "#4c7bd9",
    "diagnostic": "#8a94a6", "unknown": "#b5bcc9",
}  # fmt: skip


def _kpi_card(k: Kpi) -> str:
    return (
        f'<div class="kpi {k.status}"><div class="v">{escape(k.value)}</div>'
        f'<div class="l">{escape(k.label)}</div><div class="t">target {escape(k.target)}</div></div>'
    )


def _ticks(lo: datetime, hi: datetime, n: int = 7) -> list[datetime]:
    span = hi - lo
    if span <= timedelta(0):
        return [lo]
    steps = [timedelta(hours=h) for h in (1, 2, 3, 6, 12, 24, 48, 168)]
    step = next((s for s in steps if span / s <= n), timedelta(days=30))
    t = lo.replace(minute=0, second=0, microsecond=0)
    if step >= timedelta(days=1):
        t = t.replace(hour=0)
    while t < lo:
        t += step
    out = []
    while t <= hi:
        out.append(t)
        t += step
    return out


def _rate_chart(a: Analysis) -> str:
    """Alarms per 10 minutes, with acceptable and flood lines and flood periods shaded."""
    w, h, left, bottom, top = 1100, 260, 40, 24, 10
    data = a.buckets
    ops = a.settings.operators
    lo = data[0][0]
    hi = data[-1][0] + timedelta(minutes=10)
    span = (hi - lo).total_seconds()
    ymax = max(max(n for _, n in data), a.settings.flood_start * ops + 2)
    ph = h - bottom - top

    def x(t: datetime) -> float:
        return left + (w - left - 4) * (t - lo).total_seconds() / span

    def y(v: float) -> float:
        return top + ph * (1 - v / ymax)

    bw = max((w - left - 4) / len(data), 0.6)
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Alarms per 10 minutes">']
    for f in a.floods:
        parts.append(
            f'<rect x="{x(f.start):.1f}" y="{top}" width="{max(x(f.end) - x(f.start), 6):.1f}" '
            f'height="{ph}" fill="var(--flood)"><title>Flood {f.start:%a %H:%M}, '
            f"{f.count} alarms</title></rect>"
        )
    for t, n in data:
        if n:
            parts.append(
                f'<rect x="{x(t):.1f}" y="{y(n):.1f}" width="{bw:.2f}" height="{ph - (y(n) - top):.1f}"'
                f' fill="var(--bar)"><title>{t:%a %d %b %H:%M}: {n} alarms</title></rect>'
            )
    for value, label, color in (
        (1 * ops, "acceptable", "var(--good)"),
        (a.settings.flood_start * ops, "flood", "var(--poor)"),
    ):
        parts.append(
            f'<line x1="{left}" x2="{w - 4}" y1="{y(value):.1f}" y2="{y(value):.1f}" '
            f'stroke="{color}" stroke-dasharray="5 4"/>'
            f'<text x="{w - 6}" y="{y(value) - 4:.1f}" text-anchor="end">{label} ({value})</text>'
        )
    for v in _nice_axis(ymax):
        parts.append(f'<text x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v}</text>')
    parts.append(
        f'<line x1="{left}" x2="{w - 4}" y1="{top + ph}" y2="{top + ph}" stroke="var(--line)"/>'
    )
    fmt = "%a %d %b" if span > 2 * 86400 else "%a %H:%M"
    for t in _ticks(lo, hi):
        parts.append(f'<text x="{x(t):.1f}" y="{h - 6}" text-anchor="middle">{t:{fmt}}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _nice_axis(ymax: float) -> list[int]:
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000):
        if ymax / step <= 5:
            return list(range(0, int(ymax) + 1, step))
    return [0, int(ymax)]


def _daily_chart(a: Analysis) -> str:
    w, h, left, bottom, top = 520, 220, 40, 24, 10
    data = a.daily
    ops = a.settings.operators
    ymax = max(max(n for _, n in data), 300 * ops) * 1.05
    ph = h - bottom - top
    slot = (w - left) / len(data)
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Alarms per day">']

    def y(v: float) -> float:
        return top + ph * (1 - v / ymax)

    for i, (t, n) in enumerate(data):
        x = left + i * slot + slot * 0.15
        color = (
            "var(--good)" if n <= 150 * ops else "var(--fair)" if n <= 300 * ops else "var(--poor)"
        )
        parts.append(
            f'<rect x="{x:.1f}" y="{y(n):.1f}" width="{slot * 0.7:.1f}" height="{top + ph - y(n):.1f}"'
            f' fill="{color}" rx="2"><title>{t:%a %d %b}: {n} alarms</title></rect>'
            f'<text x="{x + slot * 0.35:.1f}" y="{h - 6}" text-anchor="middle">{t:%a %d}</text>'
        )
    for value, label in ((150 * ops, "150"), (300 * ops, "300")):
        parts.append(
            f'<line x1="{left}" x2="{w}" y1="{y(value):.1f}" y2="{y(value):.1f}" '
            f'stroke="var(--muted)" stroke-dasharray="4 4"/>'
            f'<text x="{left - 6}" y="{y(value) + 4:.1f}" text-anchor="end">{label}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _priority_bar(a: Analysis) -> str:
    total = sum(a.priorities.values()) or 1
    spans = []
    for p in PRIORITY_ORDER:
        n = a.priorities.get(p, 0)
        if n:
            pct = 100 * n / total
            spans.append(
                f'<span style="width:{pct:.2f}%;background:{PRIORITY_COLORS[p]}" '
                f'title="{p}: {n} ({pct:.1f}%)">{p} {pct:.0f}%</span>'
            )
    target = (
        '<span style="width:5%;background:#d64545">5%</span>'
        '<span style="width:15%;background:#d69e2e">medium 15%</span>'
        '<span style="width:80%;background:#4c7bd9">low 80%</span>'
    )
    return (
        f'<div class="sub">Actual</div><div class="stack">{"".join(spans)}</div>'
        f'<div class="sub">Target (EEMUA 191 / ISA-18.2)</div><div class="stack">{target}</div>'
    )


def _top_table(a: Analysis) -> str:
    if not a.tags:
        return "<p class=sub>No alarms.</p>"
    top = a.tags[: a.settings.top_n]
    peak = top[0].count
    rows = [
        "<table><tr><th>#</th><th>Alarm</th><th>Priority</th><th class=n>Count</th>"
        "<th class=n>Share</th><th></th></tr>"
    ]
    for i, t in enumerate(top, 1):
        flags = []
        if t.max_per_minute >= a.settings.chatter_count:
            flags.append(f'<span class="poor">chattering ({t.max_per_minute}/min)</span>')
        if t.fleeting:
            flags.append(f'<span class="fair">{t.fleeting} fleeting</span>')
        msg = f"<br><span class=sub>{escape(t.message)}</span>" if t.message else ""
        extra = f"<br>{' · '.join(flags)}" if flags else ""
        rows.append(
            f"<tr><td>{i}</td><td><code>{escape(display_tag(t.tag))}</code>{msg}{extra}</td>"
            f"<td>{escape(t.priority)}</td><td class=n>{t.count}</td>"
            f"<td class=n>{t.share:.1f}%</td><td style='width:22%'><div class=meter>"
            f"<span style='width:{100 * t.count / peak:.1f}%'></span></div></td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _floods_table(a: Analysis) -> str:
    if not a.floods:
        return "<p class=sub>No alarm floods. 👍</p>"
    rows = [
        "<table><tr><th>Start</th><th class=n>Duration</th><th class=n>Alarms</th>"
        "<th class=n>Peak / 10 min</th><th>Main contributors</th></tr>"
    ]
    for f in a.floods:
        top = ", ".join(f"<code>{escape(display_tag(t))}</code> ×{n}" for t, n in f.top)
        rows.append(
            f"<tr><td>{f.start:%a %d %b %H:%M}</td><td class=n>{duration(f.duration)}</td>"
            f"<td class=n>{f.count}</td><td class=n>{f.peak_10min}</td><td>{top}</td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _problem_tables(a: Analysis) -> str:
    out = []
    if a.chattering:
        out.append("<h2>Chattering alarms</h2><div class=card><table><tr><th>Alarm</th>"
                   "<th class=n>Most in 1 min</th><th class=n>Total</th></tr>")  # fmt: skip
        out += [
            f"<tr><td><code>{escape(display_tag(t.tag))}</code></td>"
            f"<td class=n>{t.max_per_minute}</td><td class=n>{t.count}</td></tr>"
            for t in a.chattering
        ]
        out.append("</table></div>")
    if a.fleeting:
        counts: dict[str, int] = {}
        for x in a.fleeting:
            counts[x.tag] = counts.get(x.tag, 0) + 1
        out.append(
            "<h2>Fleeting alarms</h2><div class=card><table><tr><th>Alarm</th>"
            f"<th class=n>Activations shorter than {a.settings.fleeting.total_seconds():g} s</th>"
            "</tr>"
        )
        out += [
            f"<tr><td><code>{escape(display_tag(t))}</code></td><td class=n>{n}</td></tr>"
            for t, n in sorted(counts.items(), key=lambda kv: -kv[1])
        ]
        out.append("</table></div>")
    if a.stale or a.standing:
        out.append("<h2>Stale and standing alarms</h2><div class=card><table><tr><th>Alarm</th>"
                   "<th>Active since</th><th class=n>Active for</th><th>State</th></tr>")  # fmt: skip
        stale_ids = {id(x) for x in a.stale}
        seen = set()
        for x in sorted(a.stale + a.standing, key=lambda x: x.time):
            if id(x) in seen:
                continue
            seen.add(id(x))
            active_for = (x.cleared or a.end) - x.time
            state = "stale" if id(x) in stale_ids else "standing"
            state += "" if x.cleared is None else " (cleared)"
            out.append(
                f"<tr><td><code>{escape(display_tag(x.tag))}</code></td>"
                f"<td>{x.time:%a %d %b %H:%M}</td><td class=n>{duration(active_for)}</td>"
                f"<td class={'poor' if 'stale' in state else 'sub'}>{state}</td></tr>"
            )
        out.append("</table></div>")
    return "".join(out)


def html(a: Analysis, title: str = "Alarm performance report", source: str = "") -> str:
    items = kpis(a)
    status = overall(items)
    ops = a.settings.operators
    src = f" · <code>{escape(source)}</code>" if source else ""
    notes = "".join(f"<li>{escape(n)}</li>" for n in a.notes)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{CSS}</style></head>
<body><main>
<h1>{escape(title)} <span class="badge {status}">{status}</span></h1>
<div class="sub">{a.start:%a %d %b %Y %H:%M} to {a.end:%a %d %b %Y %H:%M}
({duration(a.end - a.start)}) · {a.total:,} alarm activations ·
{ops} operator position{"s" if ops != 1 else ""}{src}</div>

<h2>Key performance indicators</h2>
<div class="grid">{"".join(_kpi_card(k) for k in items)}</div>

<h2>Alarms per 10 minutes</h2>
<div class="card">{_rate_chart(a)}
<div class="legend">Shaded: alarm floods (more than {a.settings.flood_start * ops} alarms in 10
minutes, ending below {a.settings.flood_end * ops}). Hover a bar for details.</div></div>

<div class="two">
<div><h2>Alarms per day</h2><div class="card">{_daily_chart(a)}
<div class="legend">Lines: 150 (very likely acceptable) and 300 (maximum manageable) per
operator.</div></div></div>
<div><h2>Priority distribution</h2><div class="card">{_priority_bar(a)}</div></div>
</div>

<h2>Top {min(a.settings.top_n, len(a.tags))} alarms (bad actors)</h2>
<div class="card">{_top_table(a)}</div>

<h2>Alarm floods</h2>
<div class="card">{_floods_table(a)}</div>
{_problem_tables(a)}
<footer>
Generated by alarmkpi {__version__}. Targets are the commonly published ANSI/ISA-18.2 and
EEMUA 191 figures for one operator position; use them as guidance for your own alarm
philosophy. Chattering: {a.settings.chatter_count}+ activations of one alarm within
{a.settings.chatter_window.total_seconds():g} s. Fleeting: cleared within
{a.settings.fleeting.total_seconds():g} s. Stale: active longer than
{a.settings.stale.total_seconds() / 3600:g} h.
{f"<ul>{notes}</ul>" if notes else ""}
</footer>
</main></body></html>
"""
