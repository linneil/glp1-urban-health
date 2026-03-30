"""Streamlit Cloud entry point — builds database if missing, then runs dashboard."""

import os
from pathlib import Path

# Check if DuckDB database exists
DB_PATH = Path("data/glp1_health.duckdb")

if not DB_PATH.exists():
    import streamlit as st
    st.warning("⏳ First-time setup: building DuckDB database from raw data...")
    st.info("This takes ~2 minutes on first load. Subsequent loads will be instant.")

    # Build the database
    from src.transforms.staging import build_database
    build_database()

    st.success("✅ Database built! Reloading dashboard...")
    st.rerun()

# Now run the main dashboard
exec(open("dashboard/app.py").read())
