"""Streamlit Cloud entry point — builds database if missing, then runs dashboard."""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

DB_PATH = Path(__file__).parent / "data" / "glp1_health.duckdb"

# Build database if it doesn't exist
if not DB_PATH.exists():
    import streamlit as st
    st.set_page_config(page_title="GLP-1 × Urban Health", layout="wide")
    st.title("🔄 Initializing Dashboard...")
    st.info("First-time setup: building DuckDB database from raw data. This takes ~2-3 minutes.")

    try:
        from src.transforms.staging import build_database
        with st.spinner("Building DuckDB analytical layer..."):
            build_database()
        st.success("✅ Database built successfully! Reloading dashboard...")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error building database: {e}")
        st.stop()

# Pass DB path to dashboard via env var so path resolution works regardless of how it's invoked
os.environ["DASHBOARD_DB_PATH"] = str(DB_PATH)

# Run the dashboard (exec shares this module's globals, so __file__ would be wrong;
# we use the env var above to pass the correct path)
exec(open(Path(__file__).parent / "dashboard" / "app.py").read())
