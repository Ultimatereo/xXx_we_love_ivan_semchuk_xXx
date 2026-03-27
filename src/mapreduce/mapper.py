"""Mapper stage for local MapReduce pipeline."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from src.common.io_utils import ensure_dir


def _period_from_date(date_value: str) -> str:
    parsed = datetime.fromisoformat(date_value)
    return f"{parsed.year:04d}-{parsed.month:02d}"


def map_csv_to_file(input_csv: Path, mapped_output: Path) -> int:
    """Map input rows to key-value lines: region, icd, period -> 1."""
    ensure_dir(mapped_output.parent)
    records_written = 0

    with input_csv.open("r", encoding="utf-8", newline="") as source, mapped_output.open(
        "w", encoding="utf-8"
    ) as target:
        reader = csv.DictReader(source)
        for row in reader:
            region_id = row["region_id"]
            icd_code = row["icd_10_code"]
            period = _period_from_date(row["date"])
            target.write(f"{region_id}\t{icd_code}\t{period}\t1\n")
            records_written += 1

    return records_written
