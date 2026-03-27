from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any


def append_monitor_event(
    wal_file: str,
    patient_id: str,
    device_id: str,
    spo2: int,
    pulse: int,
    resp_rate: int,
    timestamp: str | None = None,
) -> None:
    Path(wal_file).parent.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": timestamp or datetime.utcnow().isoformat(),
        "patient_id": patient_id,
        "device_id": device_id,
        "spo2": spo2,
        "pulse": pulse,
        "resp_rate": resp_rate,
    }

    with open(wal_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_last_n_events(wal_file: str, n: int = 10) -> list[dict[str, Any]]:
    if not Path(wal_file).exists():
        return []

    buffer = deque(maxlen=n)
    with open(wal_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                buffer.append(json.loads(line))

    return list(buffer)


if __name__ == "__main__":
    wal_path = "data/wal/icu_monitor.jsonl"

    for i in range(20):
        append_monitor_event(
            wal_file=wal_path,
            patient_id=f"patient_{1000 + i}",
            device_id=f"ICU-{i % 3}",
            spo2=95 - (i % 4),
            pulse=80 + i,
            resp_rate=16 + (i % 5),
        )

    print("[wal_logger] Last 5 events:")
    for event in read_last_n_events(wal_path, n=5):
        print(event)