# Contributing to alarmkpi

Thanks for helping!

## Most useful: sample exports

If your alarm system's export does not load, or loads wrongly, open an issue with:

- the system and version (e.g. Ignition 8.1, FactoryTalk View SE 13, DeltaV 14, WinCC 8),
- the header row and 20 to 50 sanitized rows (rename tags, remove plant names).

That is enough to add a preset and a test.

## Development

```console
git clone https://github.com/DanShinde/alarmkpi
cd alarmkpi
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

- `events.py` reads CSV into `Event`s, `analysis.py` computes the metrics, `benchmarks.py`
  holds the ISA-18.2 / EEMUA 191 targets, `report.py` renders HTML, `summary.py` text,
  Markdown and JSON.
- Keep the package dependency-free and the HTML report a single file without JavaScript.
- Add a test for every change and a line in `CHANGELOG.md` under *Unreleased*.
