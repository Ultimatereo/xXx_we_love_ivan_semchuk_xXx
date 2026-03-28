# xXx_we_love_ivan_semchuk_xXx

Учебный мини-проект про инженерные паттерны для медданных:
- редкие транзакционные обновления EHR,
- потоковая телеметрия реанимаций,
- аналитика по большим историческим дампам.

## Что реализовано

1. **Генерация CSV-дампа** визитов пациентов (`Faker`) с объёмом > RAM лимита ×5.
2. **External Merge Sort**: разбивка на run-файлы + merge через min-heap.
3. **Inverted Index** по `doctor_notes` для быстрых AND-запросов (например, `аритмия + одышка`).
4. **Append-only WAL** для событий пульсоксиметров ICU.
5. **MapReduce pipeline** для сводок и поиска всплесков по `(region_id, icd_10_code)`.
6. **Frontend-демо**: интерактивная визуализация всех этапов + CAP/CP split-brain симулятор.

---

## Структура

- `healthtech_ehr/src/` — Python пайплайн (генерация, сортировка, индекс, WAL, MapReduce).
- `healthtech_ehr/frontend/` — React + Vite демо-интерфейс для презентации решения.

---

## Запуск backend-пайплайна

> Требования: Python 3.11+

```bash
cd healthtech_ehr
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

Что появится после запуска:
- `src/data/runs/*.csv` — промежуточные sorted run-файлы,
- `src/data/sorted/sorted_visits.csv` — итоговый отсортированный дамп,
- `src/data/index/inverted_index.json` — индекс по симптомам,
- `src/data/wal/icu_monitor.jsonl` — append-only лог мониторов,
- `src/data/sorted/spikes.csv` — таблица всплесков.

---

## Запуск frontend-демо

> Требования: Node.js 20+

```bash
cd healthtech_ehr/frontend
npm install
npm run dev
```

Откройте `http://localhost:5173`.

### Сценарий демонстрации (5–7 минут)

1. **External Sort**
   - Поиграйте ползунком `Chunk size`.
   - Нажмите `Смоделировать Merge через Min-Heap` и покажите, как меняется структура run-файлов и общий merge.

2. **Inverted Index + WAL**
   - Введите запрос `аритмия одышка`.
   - Покажите пересечение множеств пациентов (AND-поиск).
   - Обратите внимание на live WAL stream с последовательной записью ICU-событий.

3. **MapReduce**
   - Покажите таблицу агрегатов и флаги всплесков (`🔥`) по гриппу.

4. **CAP / CP**
   - Включите `Симулировать partition между DC-A и DC-B`.
   - Кнопка записи диагноза перейдёт в `HTTP 503 • Write denied (CP guard)`.
   - Это наглядно объясняет, почему в EHR при split-brain мы жертвуем availability ради консистентности.

---

## Сборка frontend

```bash
cd healthtech_ehr/frontend
npm run build
npm run preview
```

pip install -r requirements.txt
## Презентация (LaTeX Beamer)

Подготовлена презентация по итогам выполнения ТЗ в ветке `Ultimatereo`:

- `presentation/ultimatereo_presentation.tex`

Сборка (пример):

```bash
cd presentation
pdflatex ultimatereo_presentation.tex
# при необходимости повторить 2 раза для стабилизации ссылок/верстки
```
