"""Streamlit pages that orchestrate project modules."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.common.io_utils import format_size
from src.config import (
    DEFAULT_INDEX_PATH,
    DEFAULT_RAW_DUMP,
    DEFAULT_SORTED_DUMP,
    DEFAULT_WAL_DIR,
    MAPREDUCE_WORK_DIR,
    OUTPUTS_DIR,
    PROJECT_ROOT,
    RUNS_DIR,
)
from src.data_generation.generator import generate_medical_dump
from src.external_sort.sorter import external_merge_sort
from src.external_sort.validator import validate_sorted_csv
from src.indexing.inverted_index import InvertedIndex, build_and_save_index
from src.mapreduce.pipeline import run_mapreduce_pipeline
from src.wal.wal import TelemetryRecord, TelemetryWAL


def _read_csv_rows(csv_path: Path, limit: int | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _existing_csv_candidates() -> list[Path]:
    candidates: list[Path] = []
    for root in (PROJECT_ROOT / "data").rglob("*.csv"):
        if root.is_file():
            candidates.append(root)
    return sorted(candidates)


def show_home_page() -> None:
    st.header("О проекте")
    st.markdown(
        """
Проект демонстрирует алгоритмы и структуры данных для национальной шины медкарт:
- внешняя сортировка больших CSV-дампов визитов;
- inverted index по полю doctor_notes;
- append-only WAL для потоковой телеметрии;
- локальный MapReduce для эпидемиологической сводки;
- архитектурный CAP-анализ для CP-зоны медкарт.
        """.strip()
    )

    st.subheader("Реализованные алгоритмы и структуры")
    st.markdown(
        """
- External Merge Sort: chunk sort + k-way merge через min-heap.
- Inverted Index: `term -> postings list(patient_id)` с AND-поиском.
- WAL-like log: append-only сегменты, fsync batching, replay.
- MapReduce: mapper, shuffle/sort на локальных файлах, reducer, spike detection.
        """.strip()
    )

    st.subheader("Пайплайн")
    st.code(
        "Генерация данных -> External Sort -> Inverted Index / WAL -> MapReduce -> Аналитика",
        language="text",
    )


def show_generation_page() -> None:
    st.header("Генерация данных")

    with st.form("generation_form"):
        records = st.number_input("Количество записей", min_value=1_000, value=60_000, step=1_000)
        ram_limit_mb = st.number_input(
            "RAM лимит для проверки размера (MB)",
            min_value=1,
            value=8,
            step=1,
        )
        output_path = st.text_input("Путь выходного CSV", value=str(DEFAULT_RAW_DUMP))
        seed = st.number_input("Seed", min_value=0, value=42, step=1)
        submitted = st.form_submit_button("Сгенерировать данные")

    if submitted:
        output = Path(output_path)
        progress = st.progress(5)
        try:
            with st.spinner("Идет генерация CSV..."):
                stats = generate_medical_dump(
                    output_path=output,
                    records=int(records),
                    ram_limit_mb=int(ram_limit_mb),
                    seed=int(seed),
                )
            progress.progress(100)
            st.success("Генерация завершена.")
            st.write(f"Файл: `{stats.output_path}`")
            st.write(f"Запрошено записей: {stats.requested_records}")
            st.write(f"Создано записей: {stats.generated_records}")
            st.write(f"Размер файла: {format_size(stats.file_size_bytes)}")
            st.write(f"Автокоррекция под RAM-правило: {stats.was_adjusted_for_ram}")
        except Exception as exc:  # pragma: no cover - UI guard
            progress.progress(100)
            st.error(f"Ошибка генерации: {exc}")


def show_external_sort_page() -> None:
    st.header("External Merge Sort")

    with st.form("external_sort_form"):
        input_path = st.text_input("Входной CSV", value=str(DEFAULT_RAW_DUMP))
        output_path = st.text_input("Выходной CSV", value=str(DEFAULT_SORTED_DUMP))
        runs_path = st.text_input("Папка run-файлов", value=str(RUNS_DIR))
        sort_keys_raw = st.text_input("Ключи сортировки (через запятую)", value="patient_id,date")
        ram_limit_mb = st.number_input("RAM лимит (MB)", min_value=1, value=8, step=1)
        rows_per_chunk = st.number_input(
            "Rows per chunk (0 = авто)", min_value=0, value=0, step=1
        )
        keep_runs = st.checkbox("Сохранить run-файлы", value=False)
        submitted = st.form_submit_button("Запустить сортировку")

    if submitted:
        in_path = Path(input_path)
        if not in_path.exists():
            st.warning("Входной файл не найден. Сначала выполните генерацию данных.")
            return

        keys = tuple(key.strip() for key in sort_keys_raw.split(",") if key.strip())
        if not keys:
            st.error("Нужно указать хотя бы один ключ сортировки.")
            return

        try:
            with st.spinner("Выполняется внешняя сортировка..."):
                stats = external_merge_sort(
                    input_csv=in_path,
                    output_csv=Path(output_path),
                    runs_dir=Path(runs_path),
                    sort_keys=keys,
                    ram_limit_mb=int(ram_limit_mb),
                    rows_per_chunk=int(rows_per_chunk) if rows_per_chunk > 0 else None,
                    cleanup_runs=not keep_runs,
                )
            st.success("Сортировка завершена.")
            st.write(f"Run-файлов: {stats.run_files_count}")
            st.write(f"Чанков: {stats.chunk_count}")
            st.write(f"Строк: {stats.total_rows}")
            st.write(f"Время: {stats.duration_seconds:.3f} сек")
            st.write(f"Выход: `{stats.output_path}`")
            st.write(f"Проверка сортировки: {stats.is_sorted}")
        except Exception as exc:  # pragma: no cover - UI guard
            st.error(f"Ошибка сортировки: {exc}")

    st.subheader("Проверка готового отсортированного файла")
    check_path = st.text_input("Файл для валидации", value=str(DEFAULT_SORTED_DUMP))
    if st.button("Проверить сортировку"):
        path = Path(check_path)
        if not path.exists():
            st.warning("Файл для проверки не найден.")
        else:
            ok, rows = validate_sorted_csv(path)
            st.write(f"Результат: {ok}")
            st.write(f"Проверено строк: {rows}")


def show_index_page() -> None:
    st.header("Inverted Index")

    with st.form("index_build_form"):
        input_path = st.text_input("CSV для индексации", value=str(DEFAULT_SORTED_DUMP))
        index_path = st.text_input("Путь сохранения индекса", value=str(DEFAULT_INDEX_PATH))
        build_submitted = st.form_submit_button("Построить индекс")

    if build_submitted:
        source = Path(input_path)
        target = Path(index_path)
        if not source.exists():
            st.warning("CSV не найден. Сначала создайте данные и при необходимости отсортируйте их.")
        else:
            try:
                with st.spinner("Идет построение индекса..."):
                    _, stats = build_and_save_index(source, target)
                st.success("Индекс построен.")
                st.write(f"Терминов: {stats.term_count}")
                st.write(f"Средняя длина postings: {stats.avg_postings_length:.2f}")
                st.write(f"Индекс сохранен: `{target}`")
                if stats.top_terms:
                    top_rows = [{"term": t, "patients": c} for t, c in stats.top_terms]
                    st.table(top_rows)
            except Exception as exc:  # pragma: no cover - UI guard
                st.error(f"Ошибка индексации: {exc}")

    st.subheader("Поиск")
    default_index = Path(index_path) if "index_path" in locals() else DEFAULT_INDEX_PATH
    search_index_path = st.text_input("Файл индекса для поиска", value=str(default_index))

    if not Path(search_index_path).exists():
        st.info("Индекс еще не построен. Выполните сборку индекса на этой странице.")
        return

    index = InvertedIndex.load(Path(search_index_path))
    current_stats = index.stats()
    st.write(f"Текущий индекс: терминов {current_stats.term_count}")

    single_term = st.text_input("Поиск по одному слову", value="аритмия")
    if st.button("Искать по слову"):
        results = index.search(single_term)
        st.write(f"Найдено пациентов: {len(results)}")
        st.write(results[:200])

    and_terms_raw = st.text_input("AND-поиск (слова через запятую)", value="аритмия, одышка")
    if st.button("Искать AND"):
        and_terms = [term.strip() for term in and_terms_raw.split(",") if term.strip()]
        results = index.search_and(and_terms)
        st.write(f"Найдено пациентов: {len(results)}")
        st.write(results[:200])


def show_wal_page() -> None:
    st.header("WAL / Телеметрия")

    wal_dir_raw = st.text_input("Каталог WAL", value=str(DEFAULT_WAL_DIR))
    wal_dir = Path(wal_dir_raw)
    fsync_every = st.number_input("fsync каждые N записей", min_value=1, value=5, step=1)
    max_file_size_mb = st.number_input(
        "Ротация WAL сегмента (MB)", min_value=0.1, value=5.0, step=0.1
    )

    wal = TelemetryWAL(
        wal_dir=wal_dir,
        fsync_every=int(fsync_every),
        max_file_size_mb=float(max_file_size_mb),
    )

    st.write(f"Активный WAL-файл: `{wal.active_file}`")

    with st.form("wal_append_form"):
        timestamp = st.text_input(
            "timestamp (ISO)", value=datetime.now().isoformat(timespec="seconds")
        )
        patient_id = st.text_input("patient_id", value="1001")
        device_id = st.text_input("device_id", value="ICU-001")
        spo2 = st.number_input("spo2", min_value=0, max_value=100, value=97, step=1)
        pulse_rate = st.number_input("pulse_rate", min_value=1, max_value=250, value=78, step=1)
        append_submitted = st.form_submit_button("Записать в WAL")

    if append_submitted:
        try:
            record = TelemetryRecord(
                timestamp=timestamp,
                patient_id=patient_id,
                device_id=device_id,
                spo2=int(spo2),
                pulse_rate=int(pulse_rate),
            )
            path = wal.append(record)
            st.success(f"Запись добавлена. Сегмент: `{path}`")
        except Exception as exc:  # pragma: no cover - UI guard
            st.error(f"Ошибка записи в WAL: {exc}")

    st.subheader("Просмотр WAL")
    last_n = st.number_input("Показать последние N записей", min_value=1, value=20, step=1)
    if st.button("Прочитать WAL"):
        try:
            records = wal.read_records()
            if not records:
                st.info("WAL пока пуст. Добавьте записи через форму выше.")
            else:
                rows = [asdict(record) for record in records[-int(last_n) :]]
                st.table(rows)
                st.write(f"Всего записей: {len(records)}")
        except Exception as exc:  # pragma: no cover - UI guard
            st.error(f"Ошибка чтения WAL: {exc}")


def show_mapreduce_page() -> None:
    st.header("MapReduce / Эпидемиологическая сводка")

    with st.form("mapreduce_form"):
        candidates = _existing_csv_candidates()
        default_input = str(DEFAULT_SORTED_DUMP if DEFAULT_SORTED_DUMP.exists() else DEFAULT_RAW_DUMP)
        input_path = st.selectbox(
            "Входной CSV",
            options=[default_input] + [str(path) for path in candidates if str(path) != default_input],
        )
        work_dir = st.text_input("Рабочая директория shuffle", value=str(MAPREDUCE_WORK_DIR))
        output_dir = st.text_input("Директория результатов", value=str(OUTPUTS_DIR))
        spike_factor = st.slider("Spike factor", min_value=1.1, max_value=4.0, value=1.8, step=0.1)
        min_current_count = st.number_input(
            "Минимум случаев в текущем периоде", min_value=1, value=8, step=1
        )
        min_previous_mean = st.number_input(
            "Минимум среднего по прошлым периодам", min_value=0.0, value=3.0, step=0.5
        )
        submitted = st.form_submit_button("Запустить MapReduce")

    if submitted:
        source = Path(input_path)
        if not source.exists():
            st.warning("Входной файл не найден. Сначала подготовьте CSV в шагах выше.")
            return

        try:
            with st.spinner("Выполняется mapreduce pipeline..."):
                result = run_mapreduce_pipeline(
                    input_csv=source,
                    work_dir=Path(work_dir),
                    output_dir=Path(output_dir),
                    spike_factor=float(spike_factor),
                    min_current_count=int(min_current_count),
                    min_previous_mean=float(min_previous_mean),
                )
            st.success("MapReduce завершен.")
            st.write(f"Map records: {result.mapped_records}")
            st.write(f"Shuffle chunks: {result.shuffle_chunks}")
            st.write(f"Period groups: {result.period_groups}")
            st.write(f"Total groups: {result.total_groups}")
            st.write(f"Potential spikes: {result.spikes_count}")
            st.write(f"Duration: {result.duration_seconds:.3f} сек")

            totals_rows = _read_csv_rows(result.totals_path, limit=30)
            spikes_rows = _read_csv_rows(result.spikes_path, limit=30)

            st.subheader("Агрегаты по (region_id, icd_10_code)")
            if totals_rows:
                st.table(totals_rows)
            else:
                st.info("Нет агрегатов для отображения.")

            st.subheader("Потенциальные всплески")
            if spikes_rows:
                st.table(spikes_rows)
            else:
                st.info("Эвристика не обнаружила всплесков.")

            # Simple chart over top totals.
            if totals_rows:
                st.subheader("Топ-10 агрегатов")
                st.bar_chart([int(row["count"]) for row in totals_rows[:10]])
                st.caption("Порядок столбцов соответствует строкам в таблице агрегатов.")

            st.write(f"Totals CSV: `{result.totals_path}`")
            st.write(f"Spikes CSV: `{result.spikes_path}`")
        except Exception as exc:  # pragma: no cover - UI guard
            st.error(f"Ошибка mapreduce: {exc}")


def show_architecture_page() -> None:
    st.header("Architecture / CAP Analysis")

    architecture_doc = PROJECT_ROOT / "docs" / "architecture.md"
    cap_doc = PROJECT_ROOT / "docs" / "cap_analysis.md"

    if architecture_doc.exists():
        st.subheader("Архитектура")
        st.markdown(architecture_doc.read_text(encoding="utf-8"))
    else:
        st.info("Файл docs/architecture.md не найден.")

    if cap_doc.exists():
        st.subheader("CAP-анализ")
        st.markdown(cap_doc.read_text(encoding="utf-8"))
    else:
        st.info("Файл docs/cap_analysis.md не найден.")
