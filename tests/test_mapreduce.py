from __future__ import annotations

from pathlib import Path

from src.mapreduce.reducer import aggregate_totals, detect_spikes, reduce_sorted_map


def test_reduce_aggregation(tmp_path: Path) -> None:
    sorted_map = tmp_path / "mapped_sorted.tsv"
    reduced = tmp_path / "reduced.csv"

    sorted_map.write_text(
        "\n".join(
            [
                "1\tJ10\t2026-01\t1",
                "1\tJ10\t2026-01\t1",
                "1\tJ10\t2026-02\t1",
                "2\tE11\t2026-02\t1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    period_counts = reduce_sorted_map(sorted_map, reduced)
    assert period_counts[("1", "J10", "2026-01")] == 2
    assert period_counts[("1", "J10", "2026-02")] == 1
    assert period_counts[("2", "E11", "2026-02")] == 1

    totals = aggregate_totals(period_counts)
    assert totals[("1", "J10")] == 3
    assert totals[("2", "E11")] == 1


def test_spike_detection() -> None:
    period_counts = {
        ("1", "J10", "2026-01"): 4,
        ("1", "J10", "2026-02"): 5,
        ("1", "J10", "2026-03"): 14,
    }

    spikes = detect_spikes(
        period_counts,
        spike_factor=2.0,
        min_current_count=8,
        min_previous_mean=3.0,
    )

    assert len(spikes) == 1
    assert spikes[0]["region_id"] == "1"
    assert spikes[0]["icd_10_code"] == "J10"
