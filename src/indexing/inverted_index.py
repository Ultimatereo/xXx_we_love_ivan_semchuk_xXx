"""Inverted index for medical notes search."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from src.common.io_utils import ensure_dir
from src.indexing.tokenizer import tokenize


@dataclass(slots=True)
class IndexStats:
    """High-level index statistics."""

    term_count: int
    avg_postings_length: float
    top_terms: list[tuple[str, int]]


class InvertedIndex:
    """A simple term -> patient_id postings index."""

    def __init__(self) -> None:
        self.postings: dict[str, set[str]] = defaultdict(set)

    def add_document(self, patient_id: str, text: str) -> None:
        """Add one doctor's note to the index."""
        for token in set(tokenize(text)):
            self.postings[token].add(str(patient_id))

    @staticmethod
    def _patient_sort_key(patient_id: str) -> tuple[int, str] | tuple[float, str]:
        if patient_id.isdigit():
            return int(patient_id), patient_id
        return float("inf"), patient_id

    def search(self, term: str) -> list[str]:
        """Search by one term and return sorted patient IDs."""
        normalized = tokenize(term)
        if not normalized:
            return []
        token = normalized[0]
        patients = self.postings.get(token, set())
        return sorted(patients, key=self._patient_sort_key)

    def search_and(self, terms: list[str]) -> list[str]:
        """Search by conjunction of terms (AND)."""
        normalized_terms: list[str] = []
        for term in terms:
            tokens = tokenize(term)
            if tokens:
                normalized_terms.append(tokens[0])
        if not normalized_terms:
            return []

        postings_lists = [self.postings.get(term, set()) for term in normalized_terms]
        if not postings_lists:
            return []

        intersection = set.intersection(*postings_lists)
        return sorted(intersection, key=self._patient_sort_key)

    def stats(self, top_k: int = 10) -> IndexStats:
        """Compute index-level statistics for diagnostics and UI."""
        term_count = len(self.postings)
        if term_count == 0:
            return IndexStats(term_count=0, avg_postings_length=0.0, top_terms=[])

        lengths = [len(postings) for postings in self.postings.values()]
        avg_len = sum(lengths) / term_count
        top_terms = sorted(
            ((term, len(postings)) for term, postings in self.postings.items()),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]

        return IndexStats(
            term_count=term_count,
            avg_postings_length=avg_len,
            top_terms=top_terms,
        )

    def save(self, output_path: Path) -> None:
        """Persist index to JSON."""
        ensure_dir(output_path.parent)
        serializable = {
            term: sorted(patient_ids, key=self._patient_sort_key)
            for term, patient_ids in self.postings.items()
        }
        with output_path.open("w", encoding="utf-8") as index_file:
            json.dump(serializable, index_file, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, input_path: Path) -> "InvertedIndex":
        """Load index from JSON."""
        with input_path.open("r", encoding="utf-8") as index_file:
            payload = json.load(index_file)

        index = cls()
        for term, patient_ids in payload.items():
            index.postings[term] = set(str(pid) for pid in patient_ids)
        return index


def build_index_from_csv(
    input_csv: Path,
    note_field: str = "doctor_notes",
    patient_field: str = "patient_id",
) -> InvertedIndex:
    """Build inverted index over CSV notes field."""
    index = InvertedIndex()
    with input_csv.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            index.add_document(str(row[patient_field]), row[note_field])
    return index


def build_and_save_index(input_csv: Path, output_path: Path) -> tuple[InvertedIndex, IndexStats]:
    """Build index from CSV and save it to disk."""
    index = build_index_from_csv(input_csv)
    stats = index.stats()
    index.save(output_path)
    return index, stats
