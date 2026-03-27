from __future__ import annotations

import csv
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

fake = Faker("ru_RU")

ICD_CODES = [
    "I48",   # фибрилляция предсердий / аритмии
    "R06.0", # одышка
    "J10",   # грипп
    "J06.9", # ОРВИ
    "R50.9", # температура
    "R05",   # кашель
    "I10",   # гипертензия
    "E11",   # диабет 2 типа
]

SYMPTOMS = [
    "аритмия",
    "одышка",
    "кашель",
    "температура",
    "слабость",
    "озноб",
    "головная боль",
    "тошнота",
    "тахикардия",
    "боль в груди",
]

NOTES_TEMPLATES = [
    "Пациент жалуется на {s1}, {s2}. Состояние средней тяжести.",
    "Наблюдаются {s1} и {s2}. Рекомендовано наблюдение.",
    "Зафиксированы {s1}, {s2}, {s3}. Требуется дополнительная диагностика.",
    "Симптомы: {s1}, {s2}. Назначено амбулаторное лечение.",
    "Отмечены {s1}, {s2}, {s3}. Возможна госпитализация.",
]

REGION_IDS = [f"region_{i:02d}" for i in range(1, 31)]


def random_visit_date(start_date: datetime, end_date: datetime) -> str:
    delta_days = (end_date - start_date).days
    day_offset = random.randint(0, max(delta_days, 1))
    dt = start_date + timedelta(days=day_offset)
    return dt.strftime("%Y-%m-%d")


def generate_doctor_note() -> str:
    template = random.choice(NOTES_TEMPLATES)
    symptoms = random.sample(SYMPTOMS, k=3)
    return template.format(s1=symptoms[0], s2=symptoms[1], s3=symptoms[2])


def estimate_row_size() -> int:
    sample = {
        "patient_id": "patient_00000123",
        "region_id": "region_01",
        "visit_date": "2026-03-27",
        "icd_10_code": "J10",
        "doctor_notes": "Пациент жалуется на аритмия, одышка. Состояние средней тяжести.",
    }
    row = f'{sample["patient_id"]},{sample["region_id"]},{sample["visit_date"]},{sample["icd_10_code"]},"{sample["doctor_notes"]}"\n'
    return len(row.encode("utf-8"))


def generate_dump(
    output_file: str,
    ram_limit_mb: int = 50,
    multiplier: int = 5,
) -> None:
    """
    Генерирует CSV, размер которого минимум в multiplier раз больше ram_limit_mb.
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    target_size_bytes = ram_limit_mb * multiplier * 1024 * 1024
    approx_row_size = estimate_row_size()
    num_rows = target_size_bytes // max(approx_row_size, 1)

    start_date = datetime(2024, 1, 1)
    end_date = datetime(2026, 3, 1)

    print(f"[generate_dump] RAM limit: {ram_limit_mb} MB")
    print(f"[generate_dump] Target file size: ~{target_size_bytes / 1024 / 1024:.2f} MB")
    print(f"[generate_dump] Approx row size: {approx_row_size} bytes")
    print(f"[generate_dump] Planned rows: {num_rows}")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["patient_id", "region_id", "visit_date", "icd_10_code", "doctor_notes"])

        for i in range(int(num_rows)):
            patient_id = f"patient_{random.randint(1, 2_000_000):08d}"
            region_id = random.choice(REGION_IDS)
            visit_date = random_visit_date(start_date, end_date)

            # слегка повышаем вероятность гриппа зимой
            month = int(visit_date.split("-")[1])
            if month in (12, 1, 2):
                icd_10_code = random.choices(ICD_CODES, weights=[8, 7, 18, 12, 10, 10, 8, 7])[0]
            else:
                icd_10_code = random.choice(ICD_CODES)

            doctor_notes = generate_doctor_note()

            writer.writerow([patient_id, region_id, visit_date, icd_10_code, doctor_notes])

            if i > 0 and i % 500_000 == 0:
                print(f"[generate_dump] Generated {i} rows")

    actual_size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"[generate_dump] Done: {output_path}")
    print(f"[generate_dump] Actual file size: {actual_size_mb:.2f} MB")


if __name__ == "__main__":
    generate_dump("data/raw/visits.csv", ram_limit_mb=50, multiplier=5)