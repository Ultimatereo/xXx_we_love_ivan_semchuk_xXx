from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path


TOKEN_RE = re.compile(r"[а-яa-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def build_inverted_index(input_csv: str, output_index_file: str) -> None:
    index: dict[str, set[str]] = defaultdict(set)

    with open(input_csv, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        processed = 0

        for row in reader:
            patient_id = row["patient_id"]
            doctor_notes = row["doctor_notes"]

            for token in tokenize(doctor_notes):
                index[token].add(patient_id)

            processed += 1
            if processed % 500_000 == 0:
                print(f"[inverted_index] Processed rows: {processed}")

    serializable_index = {
        term: sorted(list(patient_ids))
        for term, patient_ids in index.items()
    }

    Path(output_index_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_index_file, "w", encoding="utf-8") as f:
        json.dump(serializable_index, f, ensure_ascii=False)

    print(f"[inverted_index] Saved index to: {output_index_file}")
    print(f"[inverted_index] Terms indexed: {len(serializable_index)}")


def load_index(index_file: str) -> dict[str, list[str]]:
    with open(index_file, "r", encoding="utf-8") as f:
        return json.load(f)


def search_single(index: dict[str, list[str]], term: str) -> list[str]:
    return index.get(term.lower(), [])


def search_and(index: dict[str, list[str]], terms: list[str]) -> list[str]:
    normalized_terms = [t.lower() for t in terms]
    postings = [set(index.get(term, [])) for term in normalized_terms]

    if not postings:
        return []

    result = postings[0]
    for posting in postings[1:]:
        result &= posting

    return sorted(result)


if __name__ == "__main__":
    index_file = "data/index/inverted_index.json"
    build_inverted_index("data/sorted/sorted_visits.csv", index_file)

    idx = load_index(index_file)

    print("[inverted_index] Search: аритмия")
    print(search_single(idx, "аритмия")[:10])

    print("[inverted_index] Search: аритмия AND одышка")
    print(search_and(idx, ["аритмия", "одышка"])[:10])