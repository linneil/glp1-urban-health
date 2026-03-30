"""Tests for DuckDB staging and mart layer (requires a built database)."""

from pathlib import Path

import duckdb
import pytest

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "glp1_health.duckdb"

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="DuckDB not built yet — run the pipeline first"
)


@pytest.fixture
def con():
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()


def test_staging_tables_exist(con):
    tables = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    for expected in ("stg_fda_approvals", "stg_clinical_trials", "stg_obesity_rates"):
        assert expected in tables, f"{expected} missing"


def test_mart_tables_exist(con):
    tables = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    for expected in ("mart_glp1_timeline", "mart_state_obesity", "mart_trial_density", "mart_correlation"):
        assert expected in tables, f"{expected} missing"


def test_obesity_rates_have_all_50_states(con):
    count = con.execute(
        "SELECT COUNT(DISTINCT state_abbr) FROM stg_obesity_rates "
        "WHERE state_abbr NOT IN ('US', 'DC')"
    ).fetchone()[0]
    assert count >= 49, f"Expected ≥49 states, got {count}"


def test_mart_correlation_has_data(con):
    rows = con.execute("SELECT COUNT(*) FROM mart_correlation").fetchone()[0]
    assert rows >= 40, f"Expected ≥40 states in correlation, got {rows}"


def test_mart_correlation_columns(con):
    cols = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'mart_correlation'"
        ).fetchall()
    }
    for expected in ("state_abbr", "pre_slope", "post_slope", "slope_change", "trial_count"):
        assert expected in cols, f"Column {expected} missing from mart_correlation"
