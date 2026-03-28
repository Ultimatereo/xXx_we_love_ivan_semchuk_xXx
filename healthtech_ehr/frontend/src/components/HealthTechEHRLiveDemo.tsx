import { useEffect, useState } from 'react';

type VisitRow = {
  patient_id: string;
  region_id: string;
  visit_date: string;
  icd_10_code: string;
  doctor_notes: string;
};

type WalEvent = {
  timestamp: string;
  patient_id: string;
  device_id: string;
  spo2: number;
  pulse: number;
  resp_rate: number;
};

type SpikeRecord = {
  region_id: string;
  icd_10_code: string;
  visit_date: string;
  cases_count: number;
  avg_prev_7d: number;
  spike_flag: boolean;
};

type RunPreview = {
  name: string;
  rows: Array<Pick<VisitRow, 'patient_id' | 'region_id' | 'visit_date' | 'icd_10_code'>>;
};

type TopTerm = {
  term: string;
  count: number;
};

type DiagnosisWrite = {
  timestamp: string;
  patient_id: string;
  diagnosis: string;
};

type Snapshot = {
  version: number;
  split_brain: boolean;
  run_files: RunPreview[];
  merged_rows: VisitRow[];
  wal_events: WalEvent[];
  spikes: SpikeRecord[];
  top_terms: TopTerm[];
  diagnosis_log: DiagnosisWrite[];
  totals: {
    sampled_visits: number;
    wal_events: number;
  };
};

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function readJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

const fmt = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

export function HealthTechEHRLiveDemo() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [query, setQuery] = useState('arrhythmia dyspnea');
  const [foundPatients, setFoundPatients] = useState<string[]>([]);
  const [diagnosisDraft, setDiagnosisDraft] = useState('I48: Arrhythmia and dyspnea under observation');
  const [error, setError] = useState('');
  const [streamStatus, setStreamStatus] = useState<'connecting' | 'live' | 'offline'>('connecting');
  const [isSavingDiagnosis, setIsSavingDiagnosis] = useState(false);

  useEffect(() => {
    let isActive = true;

    readJson<Snapshot>(`${API_BASE}/api/bootstrap`)
      .then((data) => {
        if (isActive) {
          setSnapshot(data);
          setError('');
        }
      })
      .catch((err: Error) => {
        if (isActive) {
          setError(err.message);
          setStreamStatus('offline');
        }
      });

    const eventSource = new EventSource(`${API_BASE}/api/stream`);
    eventSource.addEventListener('open', () => {
      if (isActive) {
        setStreamStatus('live');
      }
    });

    eventSource.addEventListener('snapshot', (event) => {
      if (!isActive) return;
      const nextSnapshot = JSON.parse(event.data) as Snapshot;
      setSnapshot(nextSnapshot);
      setError('');
      setStreamStatus('live');
    });

    eventSource.addEventListener('error', () => {
      if (isActive) {
        setStreamStatus('offline');
      }
    });

    return () => {
      isActive = false;
      eventSource.close();
    };
  }, []);

  useEffect(() => {
    let isActive = true;

    readJson<{ patients: string[] }>(`${API_BASE}/api/search?q=${encodeURIComponent(query)}`)
      .then((data) => {
        if (isActive) {
          setFoundPatients(data.patients);
        }
      })
      .catch(() => {
        if (isActive) {
          setFoundPatients([]);
        }
      });

    return () => {
      isActive = false;
    };
  }, [query, snapshot?.version]);

  async function toggleSplitBrain() {
    if (!snapshot) return;
    try {
      const next = await readJson<Snapshot>(`${API_BASE}/api/cap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ split_brain: !snapshot.split_brain }),
      });
      setSnapshot(next);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update CAP mode');
    }
  }

  async function saveDiagnosis() {
    setIsSavingDiagnosis(true);
    try {
      const next = await readJson<Snapshot>(`${API_BASE}/api/diagnosis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ diagnosis: diagnosisDraft }),
      });
      setSnapshot(next);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save diagnosis');
    } finally {
      setIsSavingDiagnosis(false);
    }
  }

  if (!snapshot) {
    return (
      <main className="page">
        <section className="hero">
          <p className="eyebrow">HealthTech EHR • Live backend demo</p>
          <h1>Waiting for Python backend</h1>
          <p>{error || 'Loading initial state and opening live stream...'}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="hero">
        <div className="hero-topline">
          <p className="eyebrow">HealthTech EHR • Frontend + Python backend</p>
          <span className={`status-pill ${streamStatus}`}>{streamStatus}</span>
        </div>
        <h1>Live EHR pipeline with streaming telemetry and CAP write guard</h1>
        <p>
          The UI now reads live state from Python, listens over server-sent events, and shows new WAL/device activity and fresh visit records in real time.
        </p>
        {error ? <p className="error-banner">{error}</p> : null}
      </header>

      <section className="grid two">
        <article className="card">
          <h2>Stage 1 — External sort previews</h2>
          <p className="muted">
            Run files are read from Python-generated CSV output. Sampled visits in live memory: <strong>{snapshot.totals.sampled_visits}</strong>
          </p>
          <div className="runs">
            {snapshot.run_files.map((run) => (
              <div key={run.name} className="run">
                <h4>{run.name}</h4>
                {run.rows.map((row) => (
                  <p key={`${run.name}-${row.patient_id}`}>
                    {row.region_id} • {row.icd_10_code} • {row.patient_id}
                  </p>
                ))}
              </div>
            ))}
          </div>

          <h3>Latest merged rows</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>Region</th>
                  <th>Date</th>
                  <th>ICD-10</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.merged_rows.map((row) => (
                  <tr key={`${row.patient_id}-${row.visit_date}-${row.icd_10_code}`}>
                    <td>{row.patient_id}</td>
                    <td>{row.region_id}</td>
                    <td>{row.visit_date}</td>
                    <td>{row.icd_10_code}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card">
          <h2>Stage 2 — Inverted index + WAL</h2>
          <label>
            Search notes with AND semantics
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="arrhythmia dyspnea" />
          </label>
          <p>
            Matching patients: <strong>{foundPatients.length}</strong>
          </p>
          <div className="tags">
            {foundPatients.length ? foundPatients.map((id) => <span key={id}>{id}</span>) : <span>No match yet</span>}
          </div>

          <h3>Top terms</h3>
          <ul className="term-list">
            {snapshot.top_terms.map((term) => (
              <li key={term.term}>
                <span>{term.term}</span>
                <strong>{term.count}</strong>
              </li>
            ))}
          </ul>

          <h3>WAL stream</h3>
          <div className="wal">
            {snapshot.wal_events.map((event) => (
              <div key={`${event.timestamp}-${event.patient_id}`} className="wal-row">
                <span>{fmt(event.timestamp)}</span>
                <span>{event.device_id}</span>
                <span>SpO2 {event.spo2}%</span>
                <span>Pulse {event.pulse}</span>
                <span>RR {event.resp_rate}</span>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid two">
        <article className="card">
          <h2>Stage 3 — MapReduce spike summary</h2>
          <p className="muted">
            Historical spike rows come from Python CSV output, and live visits update the latest per-day counts on top.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Region</th>
                  <th>ICD-10</th>
                  <th>Date</th>
                  <th>Cases</th>
                  <th>Avg prev 7d</th>
                  <th>Spike</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.spikes.map((spike) => (
                  <tr key={`${spike.region_id}-${spike.icd_10_code}-${spike.visit_date}`}>
                    <td>{spike.region_id}</td>
                    <td>{spike.icd_10_code}</td>
                    <td>{spike.visit_date}</td>
                    <td>{spike.cases_count}</td>
                    <td>{spike.avg_prev_7d.toFixed(2)}</td>
                    <td>{spike.spike_flag ? 'HOT' : 'OK'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card cap">
          <h2>Stage 4 — CAP / split-brain write guard</h2>
          <label className="switch">
            <input type="checkbox" checked={snapshot.split_brain} onChange={toggleSplitBrain} />
            <span>Simulate partition between DC-A and DC-B</span>
          </label>

          <label>
            Diagnosis draft
            <input value={diagnosisDraft} onChange={(event) => setDiagnosisDraft(event.target.value)} />
          </label>

          <button onClick={saveDiagnosis} disabled={snapshot.split_brain || isSavingDiagnosis} className={snapshot.split_brain ? 'danger' : 'ok'}>
            {snapshot.split_brain ? 'HTTP 503 • Write denied' : isSavingDiagnosis ? 'Saving...' : 'Write diagnosis'}
          </button>

          <p className="muted">
            In CP mode the backend rejects writes during a partition to avoid conflicting versions of the same patient record.
          </p>

          <h3>Recent writes</h3>
          <div className="diagnosis-log">
            {snapshot.diagnosis_log.length ? (
              snapshot.diagnosis_log.map((entry) => (
                <div key={`${entry.timestamp}-${entry.patient_id}`} className="diagnosis-row">
                  <span>{fmt(entry.timestamp)}</span>
                  <span>{entry.patient_id}</span>
                  <span>{entry.diagnosis}</span>
                </div>
              ))
            ) : (
              <p className="muted">No manual writes yet.</p>
            )}
          </div>
        </article>
      </section>
    </main>
  );
}
