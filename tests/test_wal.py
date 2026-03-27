from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.wal.wal import TelemetryRecord, TelemetryWAL


def test_wal_append_and_read(tmp_path: Path) -> None:
    wal_dir = tmp_path / "wal"
    wal = TelemetryWAL(wal_dir=wal_dir, max_file_size_mb=1.0, fsync_every=1)

    r1 = TelemetryRecord(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        patient_id="501",
        device_id="ICU-001",
        spo2=97,
        pulse_rate=80,
    )
    r2 = TelemetryRecord(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        patient_id="502",
        device_id="ICU-002",
        spo2=94,
        pulse_rate=76,
    )

    wal.append(r1)
    wal.append(r2)

    records = wal.read_records()
    assert len(records) == 2
    assert records[0].patient_id == "501"
    assert records[1].device_id == "ICU-002"


def test_wal_validation(tmp_path: Path) -> None:
    wal_dir = tmp_path / "wal"
    wal = TelemetryWAL(wal_dir=wal_dir)

    bad_record = TelemetryRecord(
        timestamp="not-a-date",
        patient_id="100",
        device_id="ICU-007",
        spo2=98,
        pulse_rate=70,
    )

    try:
        wal.append(bad_record)
        assert False, "Expected ValueError"
    except ValueError:
        assert True
