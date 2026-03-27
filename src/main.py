"""CLI entrypoint for HealthTech EHR algorithms demo."""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow running CLI both as module and direct script:
# python -m src.main
# python src/main.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.io_utils import format_size
from src.config import (
    DEFAULT_INDEX_PATH,
    DEFAULT_RAW_DUMP,
    DEFAULT_SORTED_DUMP,
    DEFAULT_WAL_DIR,
    MAPREDUCE_WORK_DIR,
    OUTPUTS_DIR,
    RUNS_DIR,
    ensure_project_dirs,
)
from src.data_generation.generator import generate_medical_dump
from src.external_sort.sorter import external_merge_sort
from src.external_sort.validator import validate_sorted_csv
from src.indexing.inverted_index import InvertedIndex, build_and_save_index
from src.mapreduce.pipeline import run_mapreduce_pipeline
from src.wal.wal import TelemetryRecord, TelemetryWAL


def _parse_sort_keys(raw: str) -> tuple[str, ...]:
    keys = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not keys:
        raise ValueError("sort keys cannot be empty")
    return keys


def _cmd_generate_data(args: argparse.Namespace) -> int:
    stats = generate_medical_dump(
        output_path=args.output,
        records=args.records,
        ram_limit_mb=args.ram_limit_mb,
        seed=args.seed,
    )
    print(f"Generated file: {stats.output_path}")
    print(f"Requested records: {stats.requested_records}")
    print(f"Generated records: {stats.generated_records}")
    print(f"Adjusted for RAM ratio: {stats.was_adjusted_for_ram}")
    print(f"File size: {format_size(stats.file_size_bytes)}")
    return 0


def _cmd_external_sort(args: argparse.Namespace) -> int:
    sort_keys = _parse_sort_keys(args.sort_keys)
    stats = external_merge_sort(
        input_csv=args.input,
        output_csv=args.output,
        runs_dir=args.runs_dir,
        sort_keys=sort_keys,
        ram_limit_mb=args.ram_limit_mb,
        rows_per_chunk=args.rows_per_chunk,
        cleanup_runs=not args.keep_runs,
    )

    print(f"Input: {stats.input_path}")
    print(f"Output: {stats.output_path}")
    print(f"Rows: {stats.total_rows}")
    print(f"Chunks: {stats.chunk_count}")
    print(f"Run files: {stats.run_files_count}")
    print(f"Duration: {stats.duration_seconds:.3f} s")
    print(f"Sorted validation: {stats.is_sorted}")
    return 0 if stats.is_sorted else 1


def _cmd_validate_sort(args: argparse.Namespace) -> int:
    sort_keys = _parse_sort_keys(args.sort_keys)
    is_sorted, checked_rows = validate_sorted_csv(args.input, sort_keys=sort_keys)
    print(f"File: {args.input}")
    print(f"Rows checked: {checked_rows}")
    print(f"Sorted: {is_sorted}")
    return 0 if is_sorted else 1


def _cmd_build_index(args: argparse.Namespace) -> int:
    _, stats = build_and_save_index(args.input, args.output)
    print(f"Index path: {args.output}")
    print(f"Term count: {stats.term_count}")
    print(f"Avg postings length: {stats.avg_postings_length:.2f}")
    print("Top terms:")
    for term, freq in stats.top_terms:
        print(f"  {term}: {freq}")
    return 0


def _cmd_search_index(args: argparse.Namespace) -> int:
    index = InvertedIndex.load(args.index)

    if args.term:
        results = index.search(args.term)
        print(f"Search term: {args.term}")
        print(f"Matches: {len(results)}")
        print(f"Patient IDs: {results}")
        return 0

    if args.and_terms:
        results = index.search_and(args.and_terms)
        print(f"AND terms: {args.and_terms}")
        print(f"Matches: {len(results)}")
        print(f"Patient IDs: {results}")
        return 0

    raise ValueError("Specify either --term or --and-terms.")


def _generate_demo_telemetry_record(rng: random.Random, offset_seconds: int) -> TelemetryRecord:
    timestamp = (datetime.now() + timedelta(seconds=offset_seconds)).isoformat(timespec="seconds")
    patient_id = str(rng.randint(1, 100_000))
    device_id = f"ICU-{rng.randint(1, 999):03d}"
    spo2 = rng.randint(86, 100)
    pulse_rate = rng.randint(45, 140)
    return TelemetryRecord(
        timestamp=timestamp,
        patient_id=patient_id,
        device_id=device_id,
        spo2=spo2,
        pulse_rate=pulse_rate,
    )


def _cmd_write_wal_demo(args: argparse.Namespace) -> int:
    wal = TelemetryWAL(
        wal_dir=args.wal_dir,
        max_file_size_mb=args.max_file_size_mb,
        fsync_every=args.fsync_every,
    )
    rng = random.Random(args.seed)

    for i in range(args.count):
        wal.append(_generate_demo_telemetry_record(rng=rng, offset_seconds=i))

    print(f"WAL directory: {args.wal_dir}")
    print(f"Records appended: {args.count}")
    print(f"Active segment: {wal.active_file}")
    return 0


def _cmd_replay_wal(args: argparse.Namespace) -> int:
    wal = TelemetryWAL(wal_dir=args.wal_dir)
    records = wal.read_records(limit=args.limit)
    print(f"WAL directory: {args.wal_dir}")
    print(f"Records read: {len(records)}")
    for record in records:
        print(record)
    return 0


def _cmd_run_mapreduce(args: argparse.Namespace) -> int:
    result = run_mapreduce_pipeline(
        input_csv=args.input,
        work_dir=args.work_dir,
        output_dir=args.output_dir,
        spike_factor=args.spike_factor,
        min_current_count=args.min_current_count,
        min_previous_mean=args.min_previous_mean,
    )

    summary = {
        "mapped_records": result.mapped_records,
        "shuffle_chunks": result.shuffle_chunks,
        "period_groups": result.period_groups,
        "total_groups": result.total_groups,
        "spikes_count": result.spikes_count,
        "duration_seconds": round(result.duration_seconds, 3),
        "totals_path": str(result.totals_path),
        "spikes_path": str(result.spikes_path),
        "report_path": str(result.report_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser with all project commands."""
    parser = argparse.ArgumentParser(
        prog="ehr-cli",
        description="Algorithms and data structures demo for national EHR bus",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate-data", help="Generate synthetic medical CSV dump")
    gen.add_argument("--output", type=Path, default=DEFAULT_RAW_DUMP)
    gen.add_argument("--records", type=int, default=60_000)
    gen.add_argument("--ram-limit-mb", type=int, default=8)
    gen.add_argument("--seed", type=int, default=42)
    gen.set_defaults(func=_cmd_generate_data)

    sort_cmd = subparsers.add_parser("external-sort", help="Run external merge sort")
    sort_cmd.add_argument("--input", type=Path, default=DEFAULT_RAW_DUMP)
    sort_cmd.add_argument("--output", type=Path, default=DEFAULT_SORTED_DUMP)
    sort_cmd.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    sort_cmd.add_argument("--sort-keys", type=str, default="patient_id,date")
    sort_cmd.add_argument("--ram-limit-mb", type=int, default=8)
    sort_cmd.add_argument("--rows-per-chunk", type=int, default=None)
    sort_cmd.add_argument("--keep-runs", action="store_true")
    sort_cmd.set_defaults(func=_cmd_external_sort)

    validate_cmd = subparsers.add_parser("validate-sort", help="Validate sorted CSV")
    validate_cmd.add_argument("--input", type=Path, default=DEFAULT_SORTED_DUMP)
    validate_cmd.add_argument("--sort-keys", type=str, default="patient_id,date")
    validate_cmd.set_defaults(func=_cmd_validate_sort)

    build_idx = subparsers.add_parser("build-index", help="Build inverted index from CSV")
    build_idx.add_argument("--input", type=Path, default=DEFAULT_SORTED_DUMP)
    build_idx.add_argument("--output", type=Path, default=DEFAULT_INDEX_PATH)
    build_idx.set_defaults(func=_cmd_build_index)

    search_idx = subparsers.add_parser("search-index", help="Search inverted index")
    search_idx.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    search_idx.add_argument("--term", type=str, default=None)
    search_idx.add_argument("--and-terms", nargs="+", default=None)
    search_idx.set_defaults(func=_cmd_search_index)

    wal_write = subparsers.add_parser("write-wal-demo", help="Append demo telemetry records")
    wal_write.add_argument("--wal-dir", type=Path, default=DEFAULT_WAL_DIR)
    wal_write.add_argument("--count", type=int, default=25)
    wal_write.add_argument("--fsync-every", type=int, default=5)
    wal_write.add_argument("--max-file-size-mb", type=float, default=5.0)
    wal_write.add_argument("--seed", type=int, default=42)
    wal_write.set_defaults(func=_cmd_write_wal_demo)

    wal_replay = subparsers.add_parser("replay-wal", help="Replay telemetry WAL")
    wal_replay.add_argument("--wal-dir", type=Path, default=DEFAULT_WAL_DIR)
    wal_replay.add_argument("--limit", type=int, default=20)
    wal_replay.set_defaults(func=_cmd_replay_wal)

    mr = subparsers.add_parser("run-mapreduce", help="Run local mapreduce pipeline")
    mr.add_argument("--input", type=Path, default=DEFAULT_SORTED_DUMP)
    mr.add_argument("--work-dir", type=Path, default=MAPREDUCE_WORK_DIR)
    mr.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    mr.add_argument("--spike-factor", type=float, default=1.8)
    mr.add_argument("--min-current-count", type=int, default=8)
    mr.add_argument("--min-previous-mean", type=float, default=3.0)
    mr.set_defaults(func=_cmd_run_mapreduce)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute CLI command and return process exit code."""
    ensure_project_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
