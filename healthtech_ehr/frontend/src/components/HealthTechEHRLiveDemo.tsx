import { useEffect, useMemo, useState } from 'react';

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
};

const mockVisits: VisitRow[] = [
  {
    patient_id: 'patient_100381',
    region_id: 'region_11',
    visit_date: '2026-02-16',
    icd_10_code: 'R06.0',
    doctor_notes: 'Наблюдаются аритмия и одышка. Рекомендовано наблюдение.',
  },
  {
    patient_id: 'patient_100882',
    region_id: 'region_11',
    visit_date: '2026-02-16',
    icd_10_code: 'J10',
    doctor_notes: 'Симптомы: кашель, температура. Назначено амбулаторное лечение.',
  },
  {
    patient_id: 'patient_100129',
    region_id: 'region_03',
    visit_date: '2026-02-17',
    icd_10_code: 'J10',
    doctor_notes: 'Зафиксированы слабость, озноб, температура. Требуется диагностика.',
  },
  {
    patient_id: 'patient_100444',
    region_id: 'region_03',
    visit_date: '2026-02-17',
    icd_10_code: 'J10',
    doctor_notes: 'Отмечены кашель, температура, одышка. Возможна госпитализация.',
  },
  {
    patient_id: 'patient_100381',
    region_id: 'region_11',
    visit_date: '2026-02-20',
    icd_10_code: 'I48',
    doctor_notes: 'Пациент жалуется на аритмия, одышка. Состояние средней тяжести.',
  },
  {
    patient_id: 'patient_100550',
    region_id: 'region_27',
    visit_date: '2026-02-21',
    icd_10_code: 'R05',
    doctor_notes: 'Наблюдаются кашель и слабость. Рекомендовано наблюдение.',
  },
  {
    patient_id: 'patient_100781',
    region_id: 'region_03',
    visit_date: '2026-02-21',
    icd_10_code: 'J10',
    doctor_notes: 'Отмечены температура, кашель, озноб. Возможна госпитализация.',
  },
  {
    patient_id: 'patient_100919',
    region_id: 'region_03',
    visit_date: '2026-02-21',
    icd_10_code: 'J10',
    doctor_notes: 'Симптомы: температура, кашель. Назначено амбулаторное лечение.',
  },
];

const mockWalSeed: WalEvent[] = [
  { timestamp: '2026-03-27T16:19:46.201Z', patient_id: 'patient_100000', device_id: 'ICU-0', spo2: 94, pulse: 75, resp_rate: 15 },
  { timestamp: '2026-03-27T16:19:46.225Z', patient_id: 'patient_100001', device_id: 'ICU-1', spo2: 95, pulse: 76, resp_rate: 16 },
  { timestamp: '2026-03-27T16:19:46.226Z', patient_id: 'patient_100002', device_id: 'ICU-2', spo2: 96, pulse: 77, resp_rate: 17 },
  { timestamp: '2026-03-27T16:19:46.226Z', patient_id: 'patient_100003', device_id: 'ICU-3', spo2: 94, pulse: 78, resp_rate: 18 },
];

const spikes: SpikeRecord[] = [
  { region_id: 'region_03', icd_10_code: 'J10', visit_date: '2026-02-17', cases_count: 2, avg_prev_7d: 0.75 },
  { region_id: 'region_03', icd_10_code: 'J10', visit_date: '2026-02-21', cases_count: 3, avg_prev_7d: 1.12 },
  { region_id: 'region_11', icd_10_code: 'I48', visit_date: '2026-02-20', cases_count: 1, avg_prev_7d: 0.33 },
];

const tokenize = (text: string) => (text.toLowerCase().match(/[а-яa-z0-9]+/g) ?? []);

const fmt = (ts: string) => new Date(ts).toLocaleTimeString('ru-RU', { hour12: false });

export function HealthTechEHRLiveDemo() {
  const [chunkSize, setChunkSize] = useState(3);
  const [mergeTick, setMergeTick] = useState(0);
  const [query, setQuery] = useState('аритмия одышка');
  const [isSplitBrain, setIsSplitBrain] = useState(false);
  const [diagnosisDraft, setDiagnosisDraft] = useState('I48: Фибрилляция предсердий');
  const [walEvents, setWalEvents] = useState<WalEvent[]>(mockWalSeed);

  const runFiles = useMemo(() => {
    const chunks: VisitRow[][] = [];
    for (let i = 0; i < mockVisits.length; i += chunkSize) {
      const batch = mockVisits.slice(i, i + chunkSize).sort((a, b) =>
        [a.region_id, a.icd_10_code, a.visit_date, a.patient_id].join('|').localeCompare(
          [b.region_id, b.icd_10_code, b.visit_date, b.patient_id].join('|'),
          'ru',
        ),
      );
      chunks.push(batch);
    }
    return chunks;
  }, [chunkSize]);

  const mergedRows = useMemo(() => {
    const allRows = runFiles.flat();
    return allRows.sort((a, b) =>
      [a.region_id, a.icd_10_code, a.visit_date, a.patient_id].join('|').localeCompare(
        [b.region_id, b.icd_10_code, b.visit_date, b.patient_id].join('|'),
        'ru',
      ),
    );
  }, [runFiles, mergeTick]);

  const invertedIndex = useMemo(() => {
    const index = new Map<string, Set<string>>();
    for (const row of mergedRows) {
      for (const token of tokenize(row.doctor_notes)) {
        if (!index.has(token)) {
          index.set(token, new Set());
        }
        index.get(token)!.add(row.patient_id);
      }
    }
    return index;
  }, [mergedRows]);

  const queryTokens = query
    .split(/\s+/)
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean);

  const foundPatients = useMemo(() => {
    if (!queryTokens.length) return [];

    const postings = queryTokens.map((t) => invertedIndex.get(t) ?? new Set<string>());
    if (!postings.length) return [];

    let result = new Set(postings[0]);
    for (const posting of postings.slice(1)) {
      result = new Set([...result].filter((p) => posting.has(p)));
    }

    return [...result].sort();
  }, [queryTokens, invertedIndex]);

  useEffect(() => {
    const timer = setInterval(() => {
      const last = walEvents[walEvents.length - 1];
      const nextPulse = Math.max(60, Math.min(130, (last?.pulse ?? 80) + (Math.random() > 0.5 ? 1 : -1)));
      const nextSpo2 = Math.max(88, Math.min(100, (last?.spo2 ?? 95) + (Math.random() > 0.6 ? 1 : -1)));
      const nextResp = Math.max(10, Math.min(24, (last?.resp_rate ?? 16) + (Math.random() > 0.6 ? 1 : -1)));

      const event: WalEvent = {
        timestamp: new Date().toISOString(),
        patient_id: `patient_${100000 + Math.floor(Math.random() * 9000)}`,
        device_id: `ICU-${Math.floor(Math.random() * 4)}`,
        spo2: nextSpo2,
        pulse: nextPulse,
        resp_rate: nextResp,
      };

      setWalEvents((prev) => [...prev.slice(-15), event]);
    }, 1300);

    return () => clearInterval(timer);
  }, [walEvents]);

  const topTerms = useMemo(
    () => [...invertedIndex.entries()].sort((a, b) => b[1].size - a[1].size).slice(0, 6),
    [invertedIndex],
  );

  return (
    <main className="page">
      <header className="hero">
        <p className="eyebrow">HealthTech EHR • Interactive Playground</p>
        <h1>От дампа поликлиник до детектора эпидемий</h1>
        <p>
          Живая визуализация External Sort, Inverted Index, WAL и MapReduce с CAP-сценарием split-brain для EHR (режим CP).
        </p>
      </header>

      <section className="grid two">
        <article className="card">
          <h2>Этап 1 — External Merge Sort</h2>
          <label>
            Chunk size (строк в run-файле): <strong>{chunkSize}</strong>
            <input type="range" min={2} max={5} value={chunkSize} onChange={(e) => setChunkSize(Number(e.target.value))} />
          </label>
          <button onClick={() => setMergeTick((x) => x + 1)}>Смоделировать Merge через Min-Heap</button>
          <div className="runs">
            {runFiles.map((run, i) => (
              <div key={i} className="run">
                <h4>run_{String(i + 1).padStart(4, '0')}</h4>
                {run.map((row) => (
                  <p key={`${row.patient_id}-${row.visit_date}`}>{row.region_id} • {row.icd_10_code} • {row.patient_id}</p>
                ))}
              </div>
            ))}
          </div>
          <p className="muted">Merged rows: {mergedRows.length}. Sequential merge минимизирует random I/O на больших дампах.</p>
        </article>

        <article className="card">
          <h2>Этап 2 — Inverted Index + WAL</h2>
          <label>
            Поиск по notes (AND):
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="аритмия одышка" />
          </label>
          <p>
            Найдено пациентов: <strong>{foundPatients.length}</strong>
          </p>
          <div className="tags">{foundPatients.map((id) => <span key={id}>{id}</span>)}</div>

          <h3>Top terms</h3>
          <ul>
            {topTerms.map(([term, ids]) => (
              <li key={term}>{term}: {ids.size} пациентов</li>
            ))}
          </ul>

          <h3>WAL stream (append-only)</h3>
          <div className="wal">
            {walEvents.slice(-8).map((e) => (
              <div key={`${e.timestamp}-${e.patient_id}`} className="wal-row">
                <span>{fmt(e.timestamp)}</span>
                <span>{e.device_id}</span>
                <span>SpO₂ {e.spo2}%</span>
                <span>Pulse {e.pulse}</span>
                <span>RR {e.resp_rate}</span>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid two">
        <article className="card">
          <h2>Этап 3 — MapReduce эпидсводка</h2>
          <p className="muted">Mapper → (region_id, icd_10_code, visit_date, 1), Reducer суммирует cases_count.</p>
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
              {spikes.map((s) => (
                <tr key={`${s.region_id}-${s.icd_10_code}-${s.visit_date}`}>
                  <td>{s.region_id}</td>
                  <td>{s.icd_10_code}</td>
                  <td>{s.visit_date}</td>
                  <td>{s.cases_count}</td>
                  <td>{s.avg_prev_7d.toFixed(2)}</td>
                  <td>{s.cases_count > 2 * s.avg_prev_7d && s.avg_prev_7d > 0 ? '🔥' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>

        <article className="card cap">
          <h2>Этап 4 — CAP/CP и split-brain</h2>
          <label className="switch">
            <input type="checkbox" checked={isSplitBrain} onChange={() => setIsSplitBrain((v) => !v)} />
            <span>Симулировать partition между DC-A и DC-B</span>
          </label>

          <label>
            Диагноз для записи:
            <input value={diagnosisDraft} onChange={(e) => setDiagnosisDraft(e.target.value)} />
          </label>

          <button disabled={isSplitBrain} className={isSplitBrain ? 'danger' : 'ok'}>
            {isSplitBrain ? 'HTTP 503 • Write denied (CP guard)' : 'Записать диагноз'}
          </button>

          <p className="muted">
            В split-brain режим CP блокирует write, чтобы исключить double-write и конфликт версий в медкарте.
          </p>
        </article>
      </section>
    </main>
  );
}
