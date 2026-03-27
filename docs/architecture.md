# Architecture Overview

## Context
Национальная шина медкарт объединяет три разных профиля нагрузки:
1. Транзакционные обновления медкарт из поликлиник.
2. Потоковую телеметрию из реанимаций.
3. Пакетную аналитику по историческим архивам.

## Logical Components
- `Data Generation`: синтетический генератор CSV-дампа визитов на Faker.
- `External Sort Service`: nightly сортировка большого CSV, который не помещается в RAM.
- `Index Service`: inverted index по `doctor_notes` для быстрого поиска пациентов по симптомам.
- `Telemetry WAL`: append-only журнал показаний мониторов, ориентированный на последовательную запись.
- `MapReduce Analytics`: локальный map/shuffle/reduce pipeline для агрегатов и поиска всплесков.
- `UI Layer`: Streamlit-интерфейс, использующий те же сервисные модули, что и CLI.

## Data Flow
1. Генератор создает дамп визитов в `data/raw/medical_dump.csv`.
2. External sort разбивает файл на sorted run-файлы и выполняет k-way merge.
3. По отсортированному или исходному CSV строится inverted index.
4. Телеметрия пишется в WAL сегменты в `data/wal/`.
5. MapReduce читает CSV, выполняет shuffle/sort и формирует сводки:
   - `summary_totals.csv`
   - `period_aggregates.csv`
   - `spikes.csv`
6. Streamlit показывает результаты и метрики каждого этапа.

## Data Structures and Algorithms
- External sort:
  - `list[dict]` для chunk в памяти.
  - `heapq` для k-way merge run-файлов.
  - Последовательный I/O по run-файлам.
- Inverted index:
  - `dict[str, set[str]]` как postings store.
  - `set` intersection для AND-запроса.
- WAL:
  - append-only JSONL-сегменты `wal_XXXX.log`.
  - ротация по размеру файла.
- MapReduce:
  - map в TSV-пары,
  - chunk-sort для shuffle,
  - merge sorted chunks,
  - streaming reduce с накоплением текущего ключа.

## Operational Notes
- Проект не использует тяжелые внешние системы (Kafka/Spark/DBMS).
- Все этапы запускаются локально и повторяемы через CLI.
- Для учебных целей акцент сделан на прозрачной реализации базовых алгоритмов.
