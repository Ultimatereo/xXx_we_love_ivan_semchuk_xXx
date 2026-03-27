"""External merge sort with run generation and k-way heap merge."""

from __future__ import annotations

import csv
import heapq
import time
from dataclasses import dataclass
from pathlib import Path

from src.common.io_utils import ensure_dir
from src.external_sort.keying import build_sort_key
from src.external_sort.validator import validate_sorted_csv


@dataclass(slots=True)
class ExternalSortStats:
    """Execution statistics for external sort pipeline."""

    input_path: Path
    output_path: Path
    run_files_count: int
    chunk_count: int
    total_rows: int
    duration_seconds: float
    is_sorted: bool


def _flush_run(
    rows: list[dict[str, str]],
    run_idx: int,
    headers: list[str],
    runs_dir: Path,
    sort_keys: tuple[str, ...],
) -> Path:
    rows.sort(key=lambda row: build_sort_key(row, sort_keys))
    run_path = runs_dir / f"run_{run_idx:05d}.csv"
    with run_path.open("w", encoding="utf-8", newline="") as run_file:
        writer = csv.DictWriter(run_file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return run_path


def split_into_sorted_runs(
    input_csv: Path,
    runs_dir: Path,
    sort_keys: tuple[str, ...],
    rows_per_chunk: int,
) -> tuple[list[Path], int, int, list[str]]:
    """Read source CSV chunk-by-chunk and dump sorted run files."""
    ensure_dir(runs_dir)

    run_files: list[Path] = []
    chunk: list[dict[str, str]] = []
    total_rows = 0
    chunk_count = 0

    with input_csv.open("r", encoding="utf-8", newline="") as source_file:
        reader = csv.DictReader(source_file)
        if not reader.fieldnames:
            raise ValueError("Input CSV has no header.")
        headers = list(reader.fieldnames)

        for row in reader:
            chunk.append(row)
            total_rows += 1

            if len(chunk) >= rows_per_chunk:
                chunk_count += 1
                run_files.append(
                    _flush_run(chunk, chunk_count, headers, runs_dir, sort_keys)
                )
                chunk = []

        if chunk:
            chunk_count += 1
            run_files.append(_flush_run(chunk, chunk_count, headers, runs_dir, sort_keys))

    return run_files, chunk_count, total_rows, headers


def merge_sorted_runs(
    run_files: list[Path],
    output_csv: Path,
    sort_keys: tuple[str, ...],
    headers: list[str],
) -> int:
    """Merge sorted run files into one globally sorted output via min-heap."""
    ensure_dir(output_csv.parent)

    file_handles = []
    readers = []
    heap: list[tuple[tuple[object, ...], int, dict[str, str]]] = []
    merged_rows = 0

    try:
        for run_idx, run_path in enumerate(run_files):
            handle = run_path.open("r", encoding="utf-8", newline="")
            file_handles.append(handle)
            reader = csv.DictReader(handle)
            readers.append(reader)

            first_row = next(reader, None)
            if first_row is not None:
                heapq.heappush(
                    heap,
                    (build_sort_key(first_row, sort_keys), run_idx, first_row),
                )

        with output_csv.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=headers)
            writer.writeheader()

            while heap:
                _, run_idx, row = heapq.heappop(heap)
                writer.writerow(row)
                merged_rows += 1

                next_row = next(readers[run_idx], None)
                if next_row is not None:
                    heapq.heappush(
                        heap,
                        (build_sort_key(next_row, sort_keys), run_idx, next_row),
                    )
    finally:
        for handle in file_handles:
            handle.close()

    return merged_rows


def _default_rows_per_chunk(ram_limit_mb: int) -> int:
    estimated_row_size_bytes = 240
    rows = (ram_limit_mb * 1024 * 1024) // estimated_row_size_bytes
    return max(1_000, rows)


def external_merge_sort(
    input_csv: Path,
    output_csv: Path,
    runs_dir: Path,
    sort_keys: tuple[str, ...] = ("patient_id", "date"),
    ram_limit_mb: int = 64,
    rows_per_chunk: int | None = None,
    cleanup_runs: bool = True,
) -> ExternalSortStats:
    """Run external merge sort end-to-end and validate output order."""
    if rows_per_chunk is None:
        rows_per_chunk = _default_rows_per_chunk(ram_limit_mb)

    start_time = time.perf_counter()
    run_files, chunk_count, total_rows, headers = split_into_sorted_runs(
        input_csv=input_csv,
        runs_dir=runs_dir,
        sort_keys=sort_keys,
        rows_per_chunk=rows_per_chunk,
    )

    merge_sorted_runs(
        run_files=run_files,
        output_csv=output_csv,
        sort_keys=sort_keys,
        headers=headers,
    )

    is_sorted, _ = validate_sorted_csv(output_csv, sort_keys=sort_keys)
    duration = time.perf_counter() - start_time

    if cleanup_runs:
        for run_file in run_files:
            if run_file.exists():
                run_file.unlink()

    return ExternalSortStats(
        input_path=input_csv,
        output_path=output_csv,
        run_files_count=len(run_files),
        chunk_count=chunk_count,
        total_rows=total_rows,
        duration_seconds=duration,
        is_sorted=is_sorted,
    )
