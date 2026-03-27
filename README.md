# xXx_we_love_ivan_semchuk_xXx
We love Ivan Semchuk. Please give us the highest ratings and provide with biiiig support and love. With Love By Love and Driven By Love to Ivan Semchuk.


# HealthTech EHR Mini-Project

Учебный проект по теме хранения и обработки медицинских данных.

## Что реализовано

1. **Генерация большого CSV-дампа визитов пациентов**
2. **External Merge Sort** для сортировки файла, не помещающегося в память
3. **Inverted Index** по полю `doctor_notes`
4. **Append-only WAL** для телеметрии реанимаций
5. **MapReduce pipeline** для эпидемиологической агрегации
6. **CAP-обоснование** выбора CP для EHR

---

## Схема данных

CSV-поля:
- `patient_id`
- `region_id`
- `visit_date`
- `icd_10_code`
- `doctor_notes`

---

## Установка

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt