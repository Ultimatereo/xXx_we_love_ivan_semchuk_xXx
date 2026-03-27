"""Orchestration layer for file-based local MapReduce."""

from __future__ import annotations

import csv
import heapq
import json
import time
from dataclasses import dataclass
from pathlib import Path

from src.common.io_utils import ensure_dir
from src.mapreduce.mapper import map_csv_to_file
from src.mapreduce.reducer import aggregate_totals, detect_spikes, reduce_sorted_map


@dataclass(slots=True)
class MapReduceResult:
    """Output metadata for completed MapReduce run."""

    mapped_records: int
    shuffle_chunks: int
    period_groups: int
    total_groups: int
    spikes_count: int
    duration_seconds: float
    mapped_path: Path
    shuffled_path: Path
    reduced_path: Path
    totals_path: Path
    spikes_path: Path
    report_path: Path


def _flush_shuffle_chunk(
    chunk_lines: list[str],
    chunk_idx: int,
    temp_dir: Path,
) -> Path:
    chunk_lines.sort()
    chunk_path = temp_dir / f"shuffle_{chunk_idx:05d}.tsv"
    with chunk_path.open("w", encoding="utf-8") as chunk_file:
        chunk_file.writelines(chunk_lines)
    return chunk_path


def shuffle_sort_file(
    mapped_input: Path,
    shuffled_output: Path,
    temp_dir: Path,
    lines_per_chunk: int = 100_000,
) -> int:
    """Run local shuffle/sort using chunk sort + merge over files."""
    ensure_dir(temp_dir)
    ensure_dir(shuffled_output.parent)

    chunk_lines: list[str] = []
    chunk_files: list[Path] = []
    chunk_idx = 0

    with mapped_input.open("r", encoding="utf-8") as source:
        for line in source:
            chunk_lines.append(line)
            if len(chunk_lines) >= lines_per_chunk:
                chunk_idx += 1
                chunk_files.append(_flush_shuffle_chunk(chunk_lines, chunk_idx, temp_dir))
                chunk_lines = []

        if chunk_lines:
            chunk_idx += 1
            chunk_files.append(_flush_shuffle_chunk(chunk_lines, chunk_idx, temp_dir))

    handles = [chunk_path.open("r", encoding="utf-8") for chunk_path in chunk_files]
    try:
        with shuffled_output.open("w", encoding="utf-8") as target:
            for line in heapq.merge(*(handle for handle in handles)):
                target.write(line)
    finally:
        for handle in handles:
            handle.close()
        for chunk_path in chunk_files:
            if chunk_path.exists():
                chunk_path.unlink()

    return len(chunk_files)


def _write_totals_csv(totals: dict[tuple[str, str], int], output_path: Path) -> None:
    ensure_dir(output_path.parent)
    with output_path.open("w", encoding="utf-8", newline="") as totals_file:
        writer = csv.DictWriter(
            totals_file,
            fieldnames=["region_id", "icd_10_code", "count"],
        )
        writer.writeheader()

        for (region_id, icd_code), count in sorted(
            totals.items(), key=lambda item: item[1], reverse=True
        ):
            writer.writerow(
                {
                    "region_id": region_id,
                    "icd_10_code": icd_code,
                    "count": count,
                }
            )


def _write_spikes_csv(spikes: list[dict[str, str | int | float]], output_path: Path) -> None:
    ensure_dir(output_path.parent)
    with output_path.open("w", encoding="utf-8", newline="") as spikes_file:
        fieldnames = [
            "region_id",
            "icd_10_code",
            "latest_period",
            "latest_count",
            "baseline_mean",
            "growth_ratio",
        ]
        writer = csv.DictWriter(spikes_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(spikes)


def _write_report(
    output_path: Path,
    mapped_records: int,
    period_groups: int,
    total_groups: int,
    spikes_count: int,
    duration_seconds: float,
) -> None:
    ensure_dir(output_path.parent)
    payload = {
        "mapped_records": mapped_records,
        "period_groups": period_groups,
        "total_groups": total_groups,
        "spikes_count": spikes_count,
        "duration_seconds": round(duration_seconds, 4),
    }
    with output_path.open("w", encoding="utf-8") as report_file:
        json.dump(payload, report_file, ensure_ascii=False, indent=2)


def run_mapreduce_pipeline(
    input_csv: Path,
    work_dir: Path,
    output_dir: Path,
    spike_factor: float = 1.8,
    min_current_count: int = 8,
    min_previous_mean: float = 3.0,
) -> MapReduceResult:
    """Run map -> shuffle/sort -> reduce -> analytics over local files."""
    ensure_dir(work_dir)
    ensure_dir(output_dir)

    mapped_path = work_dir / "mapped.tsv"
    shuffled_path = work_dir / "mapped_sorted.tsv"
    reduced_path = output_dir / "period_aggregates.csv"
    totals_path = output_dir / "summary_totals.csv"
    spikes_path = output_dir / "spikes.csv"
    report_path = output_dir / "mapreduce_report.json"

    start = time.perf_counter()
    mapped_records = map_csv_to_file(input_csv=input_csv, mapped_output=mapped_path)
    shuffle_chunks = shuffle_sort_file(
        mapped_input=mapped_path,
        shuffled_output=shuffled_path,
        temp_dir=work_dir,
    )
    period_counts = reduce_sorted_map(shuffled_path, reduced_path)
    totals = aggregate_totals(period_counts)
    spikes = detect_spikes(
        period_counts,
        spike_factor=spike_factor,
        min_current_count=min_current_count,
        min_previous_mean=min_previous_mean,
    )

    _write_totals_csv(totals, totals_path)
    _write_spikes_csv(spikes, spikes_path)

    duration = time.perf_counter() - start
    _write_report(
        output_path=report_path,
        mapped_records=mapped_records,
        period_groups=len(period_counts),
        total_groups=len(totals),
        spikes_count=len(spikes),
        duration_seconds=duration,
    )

    return MapReduceResult(
        mapped_records=mapped_records,
        shuffle_chunks=shuffle_chunks,
        period_groups=len(period_counts),
        total_groups=len(totals),
        spikes_count=len(spikes),
        duration_seconds=duration,
        mapped_path=mapped_path,
        shuffled_path=shuffled_path,
        reduced_path=reduced_path,
        totals_path=totals_path,
        spikes_path=spikes_path,
        report_path=report_path,
    )
