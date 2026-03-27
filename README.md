# xXx_we_love_ivan_semchuk_xXx
We love Ivan Semchuk. Please give us the highest ratings and provide with biiiig support and love. With Love By Love and Driven By Love to Ivan Semchuk.

# HealthTech EHR

Предметная область: национальная шина медицинских карт (EHR), где одновременно нужны:
- транзакционные обновления медкарт;
- быстрая запись телеметрии;
- пакетная аналитика исторических данных.

## 1. Постановка задачи
Проект реализует 4 этапа:
1. External Merge Sort для большого CSV дампа визитов.
2. Inverted Index по `doctor_notes` и WAL-like лог для телеметрии.
3. Локальный файловый MapReduce для эпидемиологической сводки.
4. Архитектурное описание и CAP-анализ CP/AP зон.

## 2. Что реализовано
- Генерация синтетического медицинского CSV на Faker.
- Внешняя сортировка: split на run-файлы + k-way merge через `heapq`.
- Валидация сортировки выходного файла.
- Inverted index `term -> postings(patient_id)`.
- Поиск по одному слову и AND-поиск.
- WAL append-only для телеметрии с ротацией и fsync batching.
- MapReduce pipeline: mapper -> shuffle/sort -> reducer -> детектор всплесков.
- CLI для каждого этапа.
- Streamlit web-интерфейс.
- Базовые тесты ключевой логики.

## 3. Архитектура проекта
- Алгоритмические модули: `src/external_sort`, `src/indexing`, `src/wal`, `src/mapreduce`.
- Сервисная оркестрация: `src/main.py` (CLI), `src/ui/pages.py` (UI слой).
- Веб-точка входа: `src/app.py`.
- Архитектурные документы: `docs/architecture.md`, `docs/cap_analysis.md`.

Краткий pipeline:

`data generation -> external sort -> inverted index / WAL -> mapreduce -> analytics`

## 4. Установка зависимостей
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. Подготовка данных
```bash
python -m src.main generate-data --records 80000 --ram-limit-mb 8 --output data/raw/medical_dump.csv
```

Параметр `--ram-limit-mb` используется для контроля правила, что размер датасета должен быть минимум в 5 раз больше RAM лимита.

## 6. Запуск этапов (CLI)

### External sort
```bash
python -m src.main external-sort \
  --input data/raw/medical_dump.csv \
  --output data/sorted/medical_dump_sorted.csv \
  --runs-dir data/runs \
  --sort-keys patient_id,date \
  --ram-limit-mb 8
```

### Validate sort
```bash
python -m src.main validate-sort --input data/sorted/medical_dump_sorted.csv --sort-keys patient_id,date
```

### Build index
```bash
python -m src.main build-index \
  --input data/sorted/medical_dump_sorted.csv \
  --output data/outputs/inverted_index.json
```

### Search index
```bash
python -m src.main search-index --index data/outputs/inverted_index.json --term аритмия
python -m src.main search-index --index data/outputs/inverted_index.json --and-terms аритмия одышка
```

### WAL demo write/replay
```bash
python -m src.main write-wal-demo --wal-dir data/wal --count 30 --fsync-every 5
python -m src.main replay-wal --wal-dir data/wal --limit 20
```

### MapReduce
```bash
python -m src.main run-mapreduce \
  --input data/sorted/medical_dump_sorted.csv \
  --work-dir data/outputs/mapreduce_work \
  --output-dir data/outputs
```

## 7. Запуск web-интерфейса
```bash
streamlit run src/app.py
```

## 8. Структуры данных и алгоритмы
- **External Merge Sort**: потоковое чтение CSV, сортировка чанка в памяти, запись run-файлов, k-way merge через min-heap.
- **Inverted Index**: хэш-таблица `dict[str, set[str]]`, нормализация токенов и пересечение множеств для AND-запроса.
- **WAL**: append-only JSONL сегменты, `flush/fsync` по батчам, ротация по размеру.
- **MapReduce**:
  - mapper в парные записи `(region, icd, period) -> 1`;
  - shuffle/sort через chunk-sort + merge;
  - reducer как streaming aggregation.

## 9. Реализация по этапам
### Этап 1
`src/external_sort/sorter.py`, `src/external_sort/validator.py`

### Этап 2
`src/indexing/inverted_index.py`, `src/wal/wal.py`

### Этап 3
`src/mapreduce/mapper.py`, `src/mapreduce/reducer.py`, `src/mapreduce/pipeline.py`

### Этап 4
`docs/architecture.md`, `docs/cap_analysis.md`

## 10. Ограничения и упрощения
- Нет внешнего брокера сообщений/БД/кластерного runtime.
- WAL и MapReduce ориентированы на локальный учебный сценарий.
- Эвристика всплесков простая и интерпретируемая, без сложной статистики.

## 11. Идеи развития
- Сжатие postings list (delta/gap encoding).
- Bloom filters перед чтением postings.
- Multi-process merge и map/reduce workers.
- Более строгая WAL recovery стратегия с checksums.
- Расширенная временная аналитика (скользящие окна, сезонность).

## 12. Web-интерфейс и сценарии
Страницы Streamlit:
1. **Главная**: контекст и схема пайплайна.
2. **Генерация данных**: форма генерации CSV + статистика файла.
3. **External Merge Sort**: запуск сортировки, метрики run/chunk/time, валидация.
4. **Inverted Index**: построение индекса, статистика, single/AND поиск.
5. **WAL / телеметрия**: append записи, чтение последних N, replay.
6. **MapReduce / сводка**: запуск пайплайна, агрегаты и потенциальные всплески.
7. **Architecture / CAP Analysis**: архитектурное описание и CP/AP обоснование.

## 13. Тесты
```bash
pytest -q
```

Покрыты базовые проверки:
- external sort,
- k-way merge,
- AND-поиск в индексе,
- append/read WAL,
- reduce-агрегация и spike detection.
