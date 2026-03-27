"""Streamlit app entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure project root is importable when app is launched via:
# streamlit run src/app.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ensure_project_dirs
from src.ui.pages import (
    show_architecture_page,
    show_external_sort_page,
    show_generation_page,
    show_home_page,
    show_index_page,
    show_mapreduce_page,
    show_wal_page,
)


def main() -> None:
    """Render Streamlit app with sidebar navigation."""
    ensure_project_dirs()
    st.set_page_config(page_title="HealthTech EHR Algorithms Demo", layout="wide")

    st.title("HealthTech EHR: Algorithms and Data Structures")
    page = st.sidebar.radio(
        "Навигация",
        [
            "Главная",
            "Генерация данных",
            "External Merge Sort",
            "Inverted Index",
            "WAL / телеметрия",
            "MapReduce / сводка",
            "Architecture / CAP Analysis",
        ],
    )

    if page == "Главная":
        show_home_page()
    elif page == "Генерация данных":
        show_generation_page()
    elif page == "External Merge Sort":
        show_external_sort_page()
    elif page == "Inverted Index":
        show_index_page()
    elif page == "WAL / телеметрия":
        show_wal_page()
    elif page == "MapReduce / сводка":
        show_mapreduce_page()
    elif page == "Architecture / CAP Analysis":
        show_architecture_page()


if __name__ == "__main__":
    main()
