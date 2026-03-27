from __future__ import annotations

import csv
from pathlib import Path

from src.indexing.inverted_index import build_index_from_csv


def test_inverted_index_and_search(tmp_path: Path) -> None:
    csv_path = tmp_path / "records.csv"

    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["patient_id", "region_id", "date", "icd_10_code", "doctor_notes"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "patient_id": "100",
                    "region_id": "1",
                    "date": "2026-01-01",
                    "icd_10_code": "I48",
                    "doctor_notes": "Аритмия и одышка при нагрузке.",
                },
                {
                    "patient_id": "101",
                    "region_id": "1",
                    "date": "2026-01-02",
                    "icd_10_code": "J10",
                    "doctor_notes": "Лихорадка и кашель.",
                },
                {
                    "patient_id": "102",
                    "region_id": "2",
                    "date": "2026-01-03",
                    "icd_10_code": "I48",
                    "doctor_notes": "Аритмия без выраженной одышка.",
                },
            ]
        )

    index = build_index_from_csv(csv_path)

    assert index.search("аритмия") == ["100", "102"]
    assert index.search_and(["аритмия", "одышка"]) == ["100", "102"]
    assert index.search("неизвестный") == []
