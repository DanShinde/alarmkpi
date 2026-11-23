from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from alarmkpi.cli import main


def test_demo_and_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    journal = tmp_path / "j.csv"
    assert main(["demo", "-o", str(journal), "--days", "7"]) == 0
    html = tmp_path / "r.html"
    md = tmp_path / "r.md"
    js = tmp_path / "r.json"
    code = main(
        ["report", str(journal), "--html", str(html), "--markdown", str(md), "--json", str(js)]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Alarm performance:" in out
    assert "Overall: POOR" in out
    page = html.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert "Alarms per 10 minutes" in page and "<svg" in page
    assert "http" not in page.split("<body>")[0]  # no external assets
    assert "| 🔴 | Peak alarms in 10 minutes |" in md.read_text(encoding="utf-8")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["overall"] == "poor"
    assert data["floods"][0]["alarms"] > 10


def test_fail_on(demo_csv: Path) -> None:
    assert main(["report", str(demo_csv), "-q", "--fail-on", "poor"]) == 1
    assert main(["report", str(demo_csv), "-q", "--fail-on", "poor", "--area", "Electrical"]) in (
        0, 1,
    )  # fmt: skip


def test_area_filter_and_columns(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    j = tmp_path / "j.csv"
    j.write_text("When;What;Zone\n16/11/2026 08:00;A;North\n16/11/2026 09:00;B;South\n")
    args = ["report", str(j), "--time-col", "When", "--tag-col", "What", "--area-col", "Zone",
            "--time-format", "%d/%m/%Y %H:%M", "--color", "never"]  # fmt: skip
    assert main([*args, "--area", "North"]) == 0
    out = capsys.readouterr().out
    assert "1 alarms" in out
    assert main([*args, "--area", "West"]) == 2


def test_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["report", str(tmp_path / "missing.csv")]) == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    assert main(["report", str(bad)]) == 2
    assert "--time-col" in capsys.readouterr().err


def test_module_entry_point() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "alarmkpi", "--version"], capture_output=True, text=True, check=True
    )
    assert proc.stdout.startswith("alarmkpi ")
