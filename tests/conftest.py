from __future__ import annotations

from pathlib import Path

import pytest

from alarmkpi.demo import write_csv


@pytest.fixture(scope="session")
def demo_csv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("demo") / "journal.csv"
    write_csv(path)
    return path
