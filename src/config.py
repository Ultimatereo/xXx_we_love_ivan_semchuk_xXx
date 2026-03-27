"""Project-level paths and defaults."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RUNS_DIR = DATA_DIR / "runs"
SORTED_DIR = DATA_DIR / "sorted"
WAL_DIR = DATA_DIR / "wal"
OUTPUTS_DIR = DATA_DIR / "outputs"
MAPREDUCE_WORK_DIR = OUTPUTS_DIR / "mapreduce_work"

DEFAULT_RAW_DUMP = RAW_DIR / "medical_dump.csv"
DEFAULT_SORTED_DUMP = SORTED_DIR / "medical_dump_sorted.csv"
DEFAULT_INDEX_PATH = OUTPUTS_DIR / "inverted_index.json"
DEFAULT_WAL_DIR = WAL_DIR


def ensure_project_dirs() -> None:
    """Create all project directories if they do not exist."""
    for path in (
        DATA_DIR,
        RAW_DIR,
        RUNS_DIR,
        SORTED_DIR,
        WAL_DIR,
        OUTPUTS_DIR,
        MAPREDUCE_WORK_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
