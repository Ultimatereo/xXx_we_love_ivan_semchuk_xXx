from __future__ import annotations

import csv
import heapq
import os
import time
from pathlib import Path
from typing import Iterator


SORT_COLUMNS = ("region_id", "icd_10_code", "visit_date", "patient_id")


def row_sort_key(row: dict) -> tuple:
    return (
        row["region_id"],
        row["icd_10_code"],
        row["visit_date"],
        row["patient_id"],
    )


def read_csv_in_chunks(input_file: str, chunk_size: int) -> Iterator[list[dict]]:
    with open(input_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        chunk = []
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def write_run_file(rows: list[dict], run_file: str, fieldnames: list[str]) -> None:
    with open(run_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_initial_runs(input_file: str, runs_dir: str, chunk_size: int = 100_000) -> list[str]:
    Path(runs_dir).mkdir(parents=True, exist_ok=True)

    run_files = []
    fieldnames = None

    start = time.time()

    for i, chunk in enumerate(read_csv_in_chunks(input_file, chunk_size), start=1):
        if fieldnames is None and chunk:
            fieldnames = list(chunk[0].keys())

        chunk.sort(key=row_sort_key)

        run_file = os.path.join(runs_dir, f"run_{i:04d}.csv")
        write_run_file(chunk, run_file, fieldnames)
        run_files.append(run_file)

        print(f"[external_sort] Created run file: {run_file}, rows={len(chunk)}")

    elapsed = time.time() - start
    print(f"[external_sort] Initial runs created in {elapsed:.2f}s")
    print(f"[external_sort] Total run files: {len(run_files)}")
    return run_files


def merge_runs(run_files: list[str], output_file: str) -> None:
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    files = [open(run_file, "r", encoding="utf-8", newline="") for run_file in run_files]
    readers = [csv.DictReader(f) for f in files]

    try:
        fieldnames = readers[0].fieldnames
        if not fieldnames:
            raise ValueError("No fieldnames found in run files")

        with open(output_file, "w", encoding="utf-8", newline="") as out_f:
            writer = csv.DictWriter(out_f, fieldnames=fieldnames)
            writer.writeheader()

            heap = []
            for idx, reader in enumerate(readers):
                try:
                    row = next(reader)
                    heapq.heappush(heap, (row_sort_key(row), idx, row))
                except StopIteration:
                    pass

            written = 0
            while heap:
                _, reader_idx, smallest_row = heapq.heappop(heap)
                writer.writerow(smallest_row)
                written += 1

                if written % 500_000 == 0:
                    print(f"[external_sort] Merged rows: {written}")

                try:
                    next_row = next(readers[reader_idx])
                    heapq.heappush(heap, (row_sort_key(next_row), reader_idx, next_row))
                except StopIteration:
                    pass

        print(f"[external_sort] Merge complete: {output_file}")

    finally:
        for f in files:
            f.close()


def external_merge_sort(
    input_file: str,
    runs_dir: str,
    output_file: str,
    chunk_size: int = 100_000,
) -> None:
    input_size_mb = os.path.getsize(input_file) / 1024 / 1024
    print(f"[external_sort] Input file: {input_file}")
    print(f"[external_sort] Input size: {input_size_mb:.2f} MB")
    print(f"[external_sort] Chunk size: {chunk_size}")
    print(f"[external_sort] Sort key: {SORT_COLUMNS}")

    start = time.time()
    run_files = create_initial_runs(input_file, runs_dir, chunk_size=chunk_size)
    merge_runs(run_files, output_file)
    elapsed = time.time() - start

    output_size_mb = os.path.getsize(output_file) / 1024 / 1024
    print(f"[external_sort] Output file: {output_file}")
    print(f"[external_sort] Output size: {output_size_mb:.2f} MB")
    print(f"[external_sort] Total elapsed: {elapsed:.2f}s")


if __name__ == "__main__":
    external_merge_sort(
        input_file="data/raw/visits.csv",
        runs_dir="data/runs",
        output_file="data/sorted/sorted_visits.csv",
        chunk_size=100_000,
    )