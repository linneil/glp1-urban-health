"""Load raw parquet files into DuckDB staging tables and build mart layer."""

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "glp1_health.duckdb"
SCHEMA_SQL = PROJECT_ROOT / "src" / "db" / "schema.sql"


def build_database() -> Path:
    """Execute the full schema (staging + mart) against a fresh DuckDB file."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Read the schema file and resolve relative parquet paths to absolute
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    sql = sql.replace("data/raw/", str(PROJECT_ROOT / "data" / "raw") + "/")

    con = duckdb.connect(str(DB_PATH))
    try:
        # Execute each statement separately, skip on error for resilience
        for statement in sql.split(";"):
            # Strip comments-only lines from the start of each block
            lines = [
                line for line in statement.strip().splitlines()
                if line.strip() and not line.strip().startswith("--")
            ]
            statement = "\n".join(lines).strip()
            if not statement:
                continue
            try:
                con.execute(statement)
            except Exception as e:
                print(f"  WARNING: SQL statement failed — {e}")
                print(f"    Statement: {statement[:80]}...")
                continue
        # Summary
        tables = con.execute(
            "SELECT table_name, estimated_size "
            "FROM duckdb_tables() ORDER BY table_name"
        ).fetchall()
        print("\n  DuckDB tables built:")
        for name, size in tables:
            print(f"    {name:<30} {size:>8} rows")
    finally:
        con.close()

    print(f"\n  Database → {DB_PATH}")
    return DB_PATH


if __name__ == "__main__":
    build_database()
