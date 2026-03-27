from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def mapper(input_csv: str, mapped_file: str) -> None:
    Path(mapped_file).parent.mkdir(parents=True, exist_ok=True)

    with open(input_csv, "r", encoding="utf-8", newline="") as in_f, \
         open(mapped_file, "w", encoding="utf-8", newline="") as out_f:
        reader = csv.DictReader(in_f)
        writer = csv.writer(out_f)
        writer.writerow(["region_id", "icd_10_code", "visit_date", "count"])

        processed = 0
        for row in reader:
            writer.writerow([row["region_id"], row["icd_10_code"], row["visit_date"], 1])
            processed += 1
            if processed % 500_000 == 0:
                print(f"[mapreduce] Mapper processed: {processed}")

    print(f"[mapreduce] Mapper output: {mapped_file}")


def shuffle_sort(mapped_file: str, shuffled_file: str) -> None:
    with open(mapped_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows.sort(key=lambda r: (r["region_id"], r["icd_10_code"], r["visit_date"]))

    with open(shuffled_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["region_id", "icd_10_code", "visit_date", "count"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[mapreduce] Shuffle/sort output: {shuffled_file}")


def reducer(shuffled_file: str, summary_file: str) -> None:
    aggregated: dict[tuple[str, str, str], int] = defaultdict(int)

    with open(shuffled_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["region_id"], row["icd_10_code"], row["visit_date"])
            aggregated[key] += int(row["count"])

    with open(summary_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["region_id", "icd_10_code", "visit_date", "cases_count"])
        for (region_id, icd_code, visit_date), total in sorted(aggregated.items()):
            writer.writerow([region_id, icd_code, visit_date, total])

    print(f"[mapreduce] Reducer output: {summary_file}")


def detect_spikes(summary_file: str, spikes_file: str) -> None:
    grouped: dict[tuple[str, str], list[tuple[datetime, int]]] = defaultdict(list)

    with open(summary_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["region_id"], row["icd_10_code"])
            dt = datetime.strptime(row["visit_date"], "%Y-%m-%d")
            count = int(row["cases_count"])
            grouped[key].append((dt, count))

    with open(spikes_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "region_id",
            "icd_10_code",
            "visit_date",
            "cases_count",
            "avg_prev_7d",
            "spike_flag",
        ])

        for (region_id, icd_code), series in grouped.items():
            series.sort(key=lambda x: x[0])

            counts_by_date = {dt: count for dt, count in series}

            for dt, count in series:
                prev_counts = []
                for i in range(1, 8):
                    prev_day = dt - timedelta(days=i)
                    if prev_day in counts_by_date:
                        prev_counts.append(counts_by_date[prev_day])

                avg_prev_7d = sum(prev_counts) / len(prev_counts) if prev_counts else 0.0
                spike_flag = int(avg_prev_7d > 0 and count > 2 * avg_prev_7d)

                writer.writerow([
                    region_id,
                    icd_code,
                    dt.strftime("%Y-%m-%d"),
                    count,
                    round(avg_prev_7d, 2),
                    spike_flag,
                ])

    print(f"[mapreduce] Spikes output: {spikes_file}")


def run_mapreduce_pipeline(
    input_csv: str,
    mapped_file: str,
    shuffled_file: str,
    summary_file: str,
    spikes_file: str,
) -> None:
    mapper(input_csv, mapped_file)
    shuffle_sort(mapped_file, shuffled_file)
    reducer(shuffled_file, summary_file)
    detect_spikes(summary_file, spikes_file)


if __name__ == "__main__":
    run_mapreduce_pipeline(
        input_csv="data/sorted/sorted_visits.csv",
        mapped_file="data/sorted/mapped.csv",
        shuffled_file="data/sorted/shuffled.csv",
        summary_file="data/sorted/epidemic_summary.csv",
        spikes_file="data/sorted/spikes.csv",
    )