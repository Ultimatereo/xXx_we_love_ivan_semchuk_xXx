from __future__ import annotations

from generate_dump import generate_dump
from external_sort import external_merge_sort
from inverted_index import build_inverted_index
from wal_logger import append_monitor_event, read_last_n_events
from mapreduce_epidemic import run_mapreduce_pipeline


def run_all() -> None:
    # 1. Generate dump
    generate_dump(
        output_file="data/raw/visits.csv",
        ram_limit_mb=50,
        multiplier=5,
    )

    # 2. External sort
    external_merge_sort(
        input_file="data/raw/visits.csv",
        runs_dir="data/runs",
        output_file="data/sorted/sorted_visits.csv",
        chunk_size=100_000,
    )

    # 3. Inverted index
    build_inverted_index(
        input_csv="data/sorted/sorted_visits.csv",
        output_index_file="data/index/inverted_index.json",
    )

    # 4. WAL demo
    wal_file = "data/wal/icu_monitor.jsonl"
    for i in range(50):
        append_monitor_event(
            wal_file=wal_file,
            patient_id=f"patient_{100000 + i}",
            device_id=f"ICU-{i % 4}",
            spo2=94 + (i % 3),
            pulse=75 + i,
            resp_rate=15 + (i % 4),
        )

    print("[main] Last 5 WAL events:")
    for event in read_last_n_events(wal_file, n=5):
        print(event)

    # 5. MapReduce
    run_mapreduce_pipeline(
        input_csv="data/sorted/sorted_visits.csv",
        mapped_file="data/sorted/mapped.csv",
        shuffled_file="data/sorted/shuffled.csv",
        summary_file="data/sorted/epidemic_summary.csv",
        spikes_file="data/sorted/spikes.csv",
    )


if __name__ == "__main__":
    run_all()