"""Reducer stage and epidemiological heuristics."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from src.common.io_utils import ensure_dir

PeriodKey = tuple[str, str, str]
TotalKey = tuple[str, str]


def reduce_sorted_map(sorted_mapped_file: Path, reduced_csv: Path) -> dict[PeriodKey, int]:
    """Reduce sorted mapped lines and write period-level aggregates."""
    ensure_dir(reduced_csv.parent)

    aggregates: dict[PeriodKey, int] = {}
    current_key: PeriodKey | None = None
    current_count = 0

    def flush_current(writer: csv.DictWriter) -> None:
        nonlocal current_key, current_count
        if current_key is None:
            return

        region_id, icd_code, period = current_key
        aggregates[current_key] = current_count
        writer.writerow(
            {
                "region_id": region_id,
                "icd_10_code": icd_code,
                "period": period,
                "count": current_count,
            }
        )

    with sorted_mapped_file.open("r", encoding="utf-8") as mapped, reduced_csv.open(
        "w", encoding="utf-8", newline=""
    ) as reduced:
        writer = csv.DictWriter(
            reduced,
            fieldnames=["region_id", "icd_10_code", "period", "count"],
        )
        writer.writeheader()

        for line in mapped:
            region_id, icd_code, period, value = line.rstrip("\n").split("\t")
            key: PeriodKey = (region_id, icd_code, period)
            numeric_value = int(value)

            if current_key is None:
                current_key = key
                current_count = numeric_value
                continue

            if key == current_key:
                current_count += numeric_value
                continue

            flush_current(writer)
            current_key = key
            current_count = numeric_value

        flush_current(writer)

    return aggregates


def aggregate_totals(period_counts: dict[PeriodKey, int]) -> dict[TotalKey, int]:
    """Aggregate period counts to total counts by (region, icd)."""
    totals: dict[TotalKey, int] = defaultdict(int)
    for (region_id, icd_code, _period), count in period_counts.items():
        totals[(region_id, icd_code)] += count
    return dict(totals)


def detect_spikes(
    period_counts: dict[PeriodKey, int],
    spike_factor: float = 1.8,
    min_current_count: int = 8,
    min_previous_mean: float = 3.0,
) -> list[dict[str, str | int | float]]:
    """Detect potential disease spikes by comparing latest period to baseline."""
    grouped: dict[TotalKey, list[tuple[str, int]]] = defaultdict(list)

    for (region_id, icd_code, period), count in period_counts.items():
        grouped[(region_id, icd_code)].append((period, count))

    anomalies: list[dict[str, str | int | float]] = []

    for (region_id, icd_code), series in grouped.items():
        if len(series) < 2:
            continue

        series.sort(key=lambda item: item[0])
        latest_period, latest_count = series[-1]
        baseline_counts = [count for _, count in series[:-1]]
        baseline_mean = sum(baseline_counts) / len(baseline_counts)

        threshold = max(min_current_count, baseline_mean * spike_factor)
        if baseline_mean < min_previous_mean:
            continue
        if latest_count < threshold:
            continue

        growth_ratio = latest_count / baseline_mean if baseline_mean else float("inf")
        anomalies.append(
            {
                "region_id": region_id,
                "icd_10_code": icd_code,
                "latest_period": latest_period,
                "latest_count": latest_count,
                "baseline_mean": round(baseline_mean, 2),
                "growth_ratio": round(growth_ratio, 2),
            }
        )

    anomalies.sort(key=lambda row: float(row["growth_ratio"]), reverse=True)
    return anomalies
