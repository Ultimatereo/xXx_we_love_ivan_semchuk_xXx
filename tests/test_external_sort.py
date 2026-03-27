from __future__ import annotations

import csv
from pathlib import Path

from src.external_sort.sorter import external_merge_sort, merge_sorted_runs
from src.external_sort.validator import validate_sorted_csv


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["patient_id", "region_id", "date", "icd_10_code", "doctor_notes"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_external_sort_and_validation(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    runs_dir = tmp_path / "runs"

    rows = [
        {
            "patient_id": "3",
            "region_id": "2",
            "date": "2026-03-10",
            "icd_10_code": "I48",
            "doctor_notes": "аритмия",
        },
        {
            "patient_id": "1",
            "region_id": "1",
            "date": "2026-01-01",
            "icd_10_code": "E11",
            "doctor_notes": "слабость",
        },
        {
            "patient_id": "2",
            "region_id": "3",
            "date": "2026-02-14",
            "icd_10_code": "J10",
            "doctor_notes": "одышка",
        },
        {
            "patient_id": "1",
            "region_id": "4",
            "date": "2026-01-03",
            "icd_10_code": "I10",
            "doctor_notes": "головокружение",
        },
    ]
    _write_csv(input_csv, rows)

    stats = external_merge_sort(
        input_csv=input_csv,
        output_csv=output_csv,
        runs_dir=runs_dir,
        sort_keys=("patient_id", "date"),
        rows_per_chunk=2,
        cleanup_runs=False,
    )

    assert stats.run_files_count == 2
    assert stats.total_rows == 4
    ok, checked = validate_sorted_csv(output_csv, ("patient_id", "date"))
    assert ok is True
    assert checked == 4


def test_k_way_merge(tmp_path: Path) -> None:
    run1 = tmp_path / "run1.csv"
    run2 = tmp_path / "run2.csv"
    output = tmp_path / "merged.csv"

    rows1 = [
        {
            "patient_id": "1",
            "region_id": "10",
            "date": "2026-01-01",
            "icd_10_code": "J10",
            "doctor_notes": "кашель",
        },
        {
            "patient_id": "3",
            "region_id": "11",
            "date": "2026-01-05",
            "icd_10_code": "I10",
            "doctor_notes": "боль",
        },
    ]
    rows2 = [
        {
            "patient_id": "2",
            "region_id": "20",
            "date": "2026-01-02",
            "icd_10_code": "E11",
            "doctor_notes": "слабость",
        }
    ]

    _write_csv(run1, rows1)
    _write_csv(run2, rows2)

    merged = merge_sorted_runs(
        run_files=[run1, run2],
        output_csv=output,
        sort_keys=("patient_id", "date"),
        headers=["patient_id", "region_id", "date", "icd_10_code", "doctor_notes"],
    )
    assert merged == 3

    with output.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        patient_ids = [row["patient_id"] for row in reader]

    assert patient_ids == ["1", "2", "3"]
