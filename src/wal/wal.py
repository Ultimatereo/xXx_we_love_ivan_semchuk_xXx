"""Telemetry WAL implementation with append-only semantics."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from src.common.io_utils import ensure_dir


@dataclass(slots=True, frozen=True)
class TelemetryRecord:
    """One telemetry measurement event."""

    timestamp: str
    patient_id: str
    device_id: str
    spo2: int
    pulse_rate: int

    def validate(self) -> None:
        """Validate record fields for basic integrity."""
        if not self.patient_id:
            raise ValueError("patient_id must be non-empty")
        if not self.device_id:
            raise ValueError("device_id must be non-empty")

        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError as exc:
            raise ValueError("timestamp must be ISO-8601 compatible") from exc

        if not (0 <= int(self.spo2) <= 100):
            raise ValueError("spo2 must be in [0, 100]")
        if int(self.pulse_rate) <= 0:
            raise ValueError("pulse_rate must be positive")

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "TelemetryRecord":
        """Create and validate record from dictionary."""
        record = cls(
            timestamp=str(payload["timestamp"]),
            patient_id=str(payload["patient_id"]),
            device_id=str(payload["device_id"]),
            spo2=int(payload["spo2"]),
            pulse_rate=int(payload["pulse_rate"]),
        )
        record.validate()
        return record

    def to_line(self) -> str:
        """Serialize record as one JSON line."""
        return json.dumps(asdict(self), ensure_ascii=False)


class TelemetryWAL:
    """Append-only telemetry log with optional fsync batching and rotation."""

    def __init__(
        self,
        wal_dir: Path,
        max_file_size_mb: float = 5.0,
        fsync_every: int = 1,
    ) -> None:
        self.wal_dir = wal_dir
        ensure_dir(self.wal_dir)
        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)
        self.fsync_every = max(1, fsync_every)
        self._pending_since_fsync = 0
        self._active_file = self._get_or_create_active_file()

    @property
    def active_file(self) -> Path:
        """Return path to active WAL segment."""
        return self._active_file

    def _list_segments(self) -> list[Path]:
        return sorted(self.wal_dir.glob("wal_*.log"))

    def _segment_path(self, sequence: int) -> Path:
        return self.wal_dir / f"wal_{sequence:04d}.log"

    def _get_or_create_active_file(self) -> Path:
        segments = self._list_segments()
        if not segments:
            segment = self._segment_path(1)
            segment.touch()
            return segment

        last = segments[-1]
        if self.max_file_size_bytes <= 0 or last.stat().st_size < self.max_file_size_bytes:
            return last

        next_sequence = int(last.stem.split("_")[1]) + 1
        next_segment = self._segment_path(next_sequence)
        next_segment.touch()
        return next_segment

    def _maybe_rotate(self, incoming_bytes: int) -> None:
        if self.max_file_size_bytes <= 0:
            return

        current_size = self._active_file.stat().st_size
        if current_size + incoming_bytes <= self.max_file_size_bytes:
            return

        current_sequence = int(self._active_file.stem.split("_")[1])
        next_segment = self._segment_path(current_sequence + 1)
        next_segment.touch()
        self._active_file = next_segment
        self._pending_since_fsync = 0

    def append(self, record: TelemetryRecord) -> Path:
        """Append one telemetry record to active segment."""
        record.validate()
        line = f"{record.to_line()}\n"
        payload = line.encode("utf-8")
        self._maybe_rotate(len(payload))

        with self._active_file.open("ab") as wal_file:
            wal_file.write(payload)
            wal_file.flush()
            self._pending_since_fsync += 1

            if self._pending_since_fsync >= self.fsync_every:
                os.fsync(wal_file.fileno())
                self._pending_since_fsync = 0

        return self._active_file

    def append_dict(self, payload: dict[str, object]) -> Path:
        """Append one record represented as a dictionary."""
        return self.append(TelemetryRecord.from_dict(payload))

    def read_records(self, limit: int | None = None) -> list[TelemetryRecord]:
        """Read WAL records sequentially from all segments."""
        records: list[TelemetryRecord] = []

        for segment in self._list_segments():
            with segment.open("r", encoding="utf-8") as segment_file:
                for line_number, line in enumerate(segment_file, start=1):
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        payload = json.loads(text)
                        records.append(TelemetryRecord.from_dict(payload))
                    except (json.JSONDecodeError, KeyError, ValueError) as exc:
                        raise ValueError(
                            f"Invalid WAL line in {segment}:{line_number}: {exc}"
                        ) from exc

                    if limit is not None and len(records) >= limit:
                        return records

        return records
