"""Sort key building helpers."""

from __future__ import annotations

from typing import Callable

KeyCaster = Callable[[str], object]


KEY_CASTERS: dict[str, KeyCaster] = {
    "patient_id": int,
    "region_id": int,
    "date": str,
    "icd_10_code": str,
}


def _cast_value(field: str, value: str) -> object:
    caster = KEY_CASTERS.get(field, str)
    try:
        return caster(value)
    except ValueError:
        return value


def build_sort_key(row: dict[str, str], sort_keys: tuple[str, ...]) -> tuple[object, ...]:
    """Build a comparable tuple for sorting and merge heap ordering."""
    return tuple(_cast_value(field, row[field]) for field in sort_keys)
