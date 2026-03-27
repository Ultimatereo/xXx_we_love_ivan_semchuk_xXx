"""Generator for large synthetic medical CSV dumps."""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

from src.common.io_utils import ensure_dir, file_size_bytes
from src.data_generation.medical_vocab import FINDINGS, ICD_10_CODES, PLANS, SYMPTOMS


@dataclass(slots=True)
class GenerationStats:
    """Result metadata for generated dataset."""

    output_path: Path
    requested_records: int
    generated_records: int
    was_adjusted_for_ram: bool
    file_size_bytes: int


def estimate_min_records_for_ram(
    ram_limit_mb: int,
    multiplier: int = 5,
    estimated_row_size_bytes: int = 240,
) -> int:
    """Estimate minimal row count so dataset is larger than RAM budget by multiplier."""
    target_bytes = ram_limit_mb * 1024 * 1024 * multiplier
    return max(1, target_bytes // estimated_row_size_bytes)


def _build_doctor_note(rng: random.Random) -> str:
    symptoms = ", ".join(rng.sample(SYMPTOMS, k=2))
    finding = rng.choice(FINDINGS)
    plan = rng.choice(PLANS)
    return (
        f"Жалобы: {symptoms}. "
        f"Осмотр: {finding}. "
        f"План: {plan}."
    )


def generate_medical_dump(
    output_path: Path,
    records: int,
    ram_limit_mb: int | None = None,
    seed: int = 42,
    patient_pool: int = 100_000,
    region_range: tuple[int, int] = (1, 85),
) -> GenerationStats:
    """Generate synthetic visits dump as CSV for external sorting and analytics."""
    faker = Faker("ru_RU")
    faker.seed_instance(seed)
    rng = random.Random(seed)

    requested_records = max(1, records)
    generated_records = requested_records
    was_adjusted = False

    if ram_limit_mb is not None:
        min_records = estimate_min_records_for_ram(ram_limit_mb)
        if generated_records < min_records:
            generated_records = int(min_records)
            was_adjusted = True

    ensure_dir(output_path.parent)

    today = date.today()
    max_days_back = 3 * 365

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "patient_id",
                "region_id",
                "date",
                "icd_10_code",
                "doctor_notes",
            ],
        )
        writer.writeheader()

        for _ in range(generated_records):
            patient_id = rng.randint(1, patient_pool)
            region_id = rng.randint(region_range[0], region_range[1])
            visit_date = today - timedelta(days=rng.randint(0, max_days_back))
            icd_10_code = rng.choice(ICD_10_CODES)

            # Faker keeps text varied and non-deterministic enough for realistic dumps.
            note_prefix = faker.sentence(nb_words=4).rstrip(".")
            doctor_notes = f"{note_prefix}. {_build_doctor_note(rng)}"

            writer.writerow(
                {
                    "patient_id": patient_id,
                    "region_id": region_id,
                    "date": visit_date.isoformat(),
                    "icd_10_code": icd_10_code,
                    "doctor_notes": doctor_notes,
                }
            )

    return GenerationStats(
        output_path=output_path,
        requested_records=requested_records,
        generated_records=generated_records,
        was_adjusted_for_ram=was_adjusted,
        file_size_bytes=file_size_bytes(output_path),
    )
