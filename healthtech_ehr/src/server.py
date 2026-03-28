from __future__ import annotations

import csv
import json
import queue
import random
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, asdict
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from external_sort import row_sort_key
from wal_logger import append_monitor_event, read_last_n_events


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
RAW_VISITS_FILE = DATA_DIR / "raw" / "visits.csv"
RUNS_DIR = DATA_DIR / "runs"
SPIKES_FILE = DATA_DIR / "sorted" / "spikes.csv"
WAL_FILE = DATA_DIR / "wal" / "icu_monitor.jsonl"

REGION_IDS = [f"region_{i:02d}" for i in range(1, 31)]
ICD_CODES = ["I48", "R06.0", "J10", "J06.9", "R50.9", "R05", "I10", "E11"]
SYMPTOMS = [
    "arrhythmia",
    "dyspnea",
    "cough",
    "fever",
    "weakness",
    "chills",
    "headache",
    "nausea",
    "tachycardia",
    "chest pain",
]
NOTES_TEMPLATES = [
    "Patient reports {s1} and {s2}. Monitoring continues.",
    "Observed {s1}, {s2}, and {s3}. Additional diagnostics recommended.",
    "Symptoms include {s1} and {s2}. Outpatient treatment started.",
    "Stable but notable {s1} with {s2}. Follow-up visit scheduled.",
]
TOKEN_RE = __import__("re").compile(r"[a-z0-9]+")


@dataclass
class VisitRow:
    patient_id: str
    region_id: str
    visit_date: str
    icd_10_code: str
    doctor_notes: str


@dataclass
class WalEvent:
    timestamp: str
    patient_id: str
    device_id: str
    spo2: int
    pulse: int
    resp_rate: int


@dataclass
class SpikeRecord:
    region_id: str
    icd_10_code: str
    visit_date: str
    cases_count: int
    avg_prev_7d: float
    spike_flag: bool


@dataclass
class DiagnosisWrite:
    timestamp: str
    patient_id: str
    diagnosis: str


class LiveEhrState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue[str]] = set()
        self._stop_event = threading.Event()

        self.split_brain = False
        self.recent_visits: deque[VisitRow] = deque(maxlen=18)
        self.wal_events: deque[WalEvent] = deque(maxlen=18)
        self.base_spikes: list[SpikeRecord] = []
        self.live_spikes: dict[tuple[str, str, str], SpikeRecord] = {}
        self.diagnosis_log: deque[DiagnosisWrite] = deque(maxlen=8)
        self.run_previews: list[dict[str, Any]] = []
        self.term_to_patients: dict[str, set[str]] = {}
        self.daily_counts: dict[tuple[str, str, str], int] = {}
        self.patient_counter = 120000
        self.version = 0

        self._load_initial_state()

        self._generator_thread = threading.Thread(
            target=self._generator_loop,
            name="ehr-live-generator",
            daemon=True,
        )
        self._generator_thread.start()

    def _load_initial_state(self) -> None:
        self.run_previews = self._load_run_previews(limit=4, rows_per_file=3)
        self.base_spikes = self._load_spike_rows(limit=6)
        self.wal_events.extend(self._load_wal_events(limit=10))

        for visit in self._seed_demo_visits():
            self._append_visit_locked(visit, persist=False, track_diagnosis=False)

        self.patient_counter = max(
            [self.patient_counter] + [self._extract_patient_number(v.patient_id) for v in self.recent_visits]
        )

    def _load_run_previews(self, limit: int, rows_per_file: int) -> list[dict[str, Any]]:
        previews: list[dict[str, Any]] = []
        for run_file in sorted(RUNS_DIR.glob("run_*.csv"))[:limit]:
            rows: list[dict[str, str]] = []
            with run_file.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    rows.append({
                        "patient_id": row["patient_id"],
                        "region_id": row["region_id"],
                        "visit_date": row["visit_date"],
                        "icd_10_code": row["icd_10_code"],
                    })
                    if len(rows) >= rows_per_file:
                        break
            previews.append({"name": run_file.stem, "rows": rows})
        return previews

    def _load_spike_rows(self, limit: int) -> list[SpikeRecord]:
        if not SPIKES_FILE.exists():
            return []

        rows: deque[SpikeRecord] = deque(maxlen=limit)
        with SPIKES_FILE.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(
                    SpikeRecord(
                        region_id=row["region_id"],
                        icd_10_code=row["icd_10_code"],
                        visit_date=row["visit_date"],
                        cases_count=int(row["cases_count"]),
                        avg_prev_7d=float(row["avg_prev_7d"]),
                        spike_flag=row["spike_flag"] == "1",
                    )
                )
        return list(rows)

    def _load_wal_events(self, limit: int) -> list[WalEvent]:
        return [WalEvent(**item) for item in read_last_n_events(str(WAL_FILE), n=limit)]

    def _seed_demo_visits(self) -> list[VisitRow]:
        today = datetime.now(UTC).date()
        return [
            VisitRow("patient_100381", "region_11", str(today - timedelta(days=2)), "I48", "Patient reports arrhythmia and dyspnea. Monitoring continues."),
            VisitRow("patient_100882", "region_11", str(today - timedelta(days=2)), "J10", "Symptoms include fever and cough. Outpatient treatment started."),
            VisitRow("patient_100129", "region_03", str(today - timedelta(days=1)), "J10", "Observed weakness, chills, and fever. Additional diagnostics recommended."),
            VisitRow("patient_100444", "region_03", str(today - timedelta(days=1)), "J10", "Stable but notable cough with dyspnea. Follow-up visit scheduled."),
            VisitRow("patient_100550", "region_27", str(today), "R05", "Patient reports cough and weakness. Monitoring continues."),
            VisitRow("patient_100781", "region_03", str(today), "J10", "Symptoms include fever and chills. Outpatient treatment started."),
        ]

    def _generator_loop(self) -> None:
        tick = 0
        while not self._stop_event.wait(1.5):
            wal_event = self._build_wal_event()
            with self._lock:
                self._append_wal_locked(wal_event, persist=True)
                if tick % 2 == 0:
                    visit = self._build_visit()
                    self._append_visit_locked(visit, persist=True, track_diagnosis=False)
                payload = self._snapshot_locked()
            self._broadcast(payload)
            tick += 1

    def _build_visit(self) -> VisitRow:
        patient_id = self._next_patient_id()
        symptoms = random.sample(SYMPTOMS, k=3)
        template = random.choice(NOTES_TEMPLATES)
        note = template.format(s1=symptoms[0], s2=symptoms[1], s3=symptoms[2])
        visit_date = str((datetime.now(UTC) - timedelta(days=random.randint(0, 3))).date())
        icd_code = random.choice(ICD_CODES)
        region_id = random.choice(REGION_IDS)
        return VisitRow(
            patient_id=patient_id,
            region_id=region_id,
            visit_date=visit_date,
            icd_10_code=icd_code,
            doctor_notes=note,
        )

    def _build_wal_event(self) -> WalEvent:
        last = self.wal_events[-1] if self.wal_events else None
        pulse = max(60, min(135, (last.pulse if last else 80) + random.choice([-2, -1, 1, 2])))
        spo2 = max(88, min(100, (last.spo2 if last else 95) + random.choice([-1, 0, 1])))
        resp_rate = max(10, min(24, (last.resp_rate if last else 16) + random.choice([-1, 0, 1])))
        return WalEvent(
            timestamp=datetime.now(UTC).isoformat(),
            patient_id=self._next_patient_id(),
            device_id=f"ICU-{random.randint(0, 3)}",
            spo2=spo2,
            pulse=pulse,
            resp_rate=resp_rate,
        )

    def _next_patient_id(self) -> str:
        self.patient_counter += 1
        return f"patient_{self.patient_counter}"

    def _extract_patient_number(self, patient_id: str) -> int:
        try:
            return int(patient_id.split("_", 1)[1])
        except (IndexError, ValueError):
            return 0

    def _append_visit_locked(self, visit: VisitRow, persist: bool, track_diagnosis: bool) -> None:
        self.recent_visits.append(visit)
        self._rebuild_search_index_locked()
        self._update_live_spike_locked(visit)
        self.version += 1

        if persist:
            self._persist_visit(visit)

        if track_diagnosis:
            self.diagnosis_log.append(
                DiagnosisWrite(
                    timestamp=datetime.now(UTC).isoformat(),
                    patient_id=visit.patient_id,
                    diagnosis=visit.doctor_notes,
                )
            )

    def _append_wal_locked(self, event: WalEvent, persist: bool) -> None:
        self.wal_events.append(event)
        self.version += 1
        if persist:
            append_monitor_event(
                wal_file=str(WAL_FILE),
                patient_id=event.patient_id,
                device_id=event.device_id,
                spo2=event.spo2,
                pulse=event.pulse,
                resp_rate=event.resp_rate,
                timestamp=event.timestamp,
            )

    def _persist_visit(self, visit: VisitRow) -> None:
        RAW_VISITS_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_exists = RAW_VISITS_FILE.exists()
        with RAW_VISITS_FILE.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["patient_id", "region_id", "visit_date", "icd_10_code", "doctor_notes"],
            )
            if not file_exists or RAW_VISITS_FILE.stat().st_size == 0:
                writer.writeheader()
            writer.writerow(asdict(visit))

    def _rebuild_search_index_locked(self) -> None:
        index: dict[str, set[str]] = {}
        for visit in self.recent_visits:
            for token in TOKEN_RE.findall(visit.doctor_notes.lower()):
                index.setdefault(token, set()).add(visit.patient_id)
        self.term_to_patients = index

    def _update_live_spike_locked(self, visit: VisitRow) -> None:
        key = (visit.region_id, visit.icd_10_code, visit.visit_date)
        self.daily_counts[key] = self.daily_counts.get(key, 0) + 1

        current_date = datetime.strptime(visit.visit_date, "%Y-%m-%d").date()
        previous_counts: list[int] = []
        for offset in range(1, 8):
            previous_date = str(current_date - timedelta(days=offset))
            prev_key = (visit.region_id, visit.icd_10_code, previous_date)
            if prev_key in self.daily_counts:
                previous_counts.append(self.daily_counts[prev_key])

        avg_prev_7d = sum(previous_counts) / len(previous_counts) if previous_counts else 0.0
        record = SpikeRecord(
            region_id=visit.region_id,
            icd_10_code=visit.icd_10_code,
            visit_date=visit.visit_date,
            cases_count=self.daily_counts[key],
            avg_prev_7d=round(avg_prev_7d, 2),
            spike_flag=avg_prev_7d > 0 and self.daily_counts[key] > 2 * avg_prev_7d,
        )
        self.live_spikes[key] = record

    def _snapshot_locked(self) -> dict[str, Any]:
        merged_rows = sorted((asdict(visit) for visit in self.recent_visits), key=row_sort_key)
        top_terms = sorted(
            ((term, len(patient_ids)) for term, patient_ids in self.term_to_patients.items()),
            key=lambda item: (-item[1], item[0]),
        )[:8]
        spikes = list(self.base_spikes) + list(self.live_spikes.values())
        spikes.sort(key=lambda item: (item.visit_date, item.region_id, item.icd_10_code), reverse=True)

        return {
            "version": self.version,
            "split_brain": self.split_brain,
            "run_files": self.run_previews,
            "merged_rows": merged_rows,
            "wal_events": [asdict(event) for event in self.wal_events],
            "spikes": [asdict(spike) for spike in spikes[:8]],
            "top_terms": [{"term": term, "count": count} for term, count in top_terms],
            "diagnosis_log": [asdict(item) for item in self.diagnosis_log],
            "totals": {
                "sampled_visits": len(self.recent_visits),
                "wal_events": len(self.wal_events),
            },
        }

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def search_patients(self, query: str) -> list[str]:
        tokens = TOKEN_RE.findall(query.lower())
        with self._lock:
            if not tokens:
                return []

            postings = [self.term_to_patients.get(token, set()) for token in tokens]
            if not postings:
                return []

            result = set(postings[0])
            for posting in postings[1:]:
                result &= posting
            return sorted(result)

    def set_split_brain(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            self.split_brain = enabled
            self.version += 1
            payload = self._snapshot_locked()
        self._broadcast(payload)
        return payload

    def write_diagnosis(self, diagnosis: str) -> dict[str, Any]:
        with self._lock:
            if self.split_brain:
                raise PermissionError("Writes are blocked while split-brain protection is active.")

            icd_code = diagnosis.split(":", 1)[0].strip() or random.choice(ICD_CODES)
            note = diagnosis.strip()
            visit = VisitRow(
                patient_id=self._next_patient_id(),
                region_id=random.choice(REGION_IDS),
                visit_date=str(datetime.now(UTC).date()),
                icd_10_code=icd_code,
                doctor_notes=note,
            )
            self._append_visit_locked(visit, persist=True, track_diagnosis=True)
            payload = self._snapshot_locked()

        self._broadcast(payload)
        return payload

    def register_subscriber(self) -> queue.Queue[str]:
        subscriber: queue.Queue[str] = queue.Queue(maxsize=8)
        with self._lock:
            self._subscribers.add(subscriber)
            subscriber.put_nowait(json.dumps(self._snapshot_locked()))
        return subscriber

    def unregister_subscriber(self, subscriber: queue.Queue[str]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def _broadcast(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload)
        with self._lock:
            stale: list[queue.Queue[str]] = []
            for subscriber in self._subscribers:
                try:
                    subscriber.put_nowait(message)
                except queue.Full:
                    stale.append(subscriber)
            for subscriber in stale:
                self._subscribers.discard(subscriber)


STATE = LiveEhrState()


class ApiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._write_json({"ok": True, "service": "healthtech-ehr"})
            return
        if parsed.path == "/api/bootstrap":
            self._write_json(STATE.get_snapshot())
            return
        if parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._write_json({"patients": STATE.search_patients(query)})
            return
        if parsed.path == "/api/stream":
            self._handle_stream()
            return
        self._write_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json_body()
        if parsed.path == "/api/cap":
            snapshot = STATE.set_split_brain(bool(payload.get("split_brain")))
            self._write_json(snapshot)
            return
        if parsed.path == "/api/diagnosis":
            diagnosis = str(payload.get("diagnosis", "")).strip()
            if not diagnosis:
                self._write_json({"error": "diagnosis is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                snapshot = STATE.write_diagnosis(diagnosis)
            except PermissionError as exc:
                self._write_json({"error": str(exc)}, status=HTTPStatus.SERVICE_UNAVAILABLE)
                return
            self._write_json(snapshot)
            return
        self._write_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length)
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def _handle_stream(self) -> None:
        subscriber = STATE.register_subscriber()
        self.send_response(HTTPStatus.OK)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                try:
                    message = subscriber.get(timeout=15)
                    payload = f"event: snapshot\ndata: {message}\n\n".encode("utf-8")
                except queue.Empty:
                    payload = b": keep-alive\n\n"
                self.wfile.write(payload)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            STATE.unregister_subscriber(subscriber)

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"[server] Listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
