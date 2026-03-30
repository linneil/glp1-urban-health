"""Statistical correlation analysis between GLP-1 trial density and obesity trends."""

from pathlib import Path

import duckdb
import pandas as pd
from scipy import stats

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "glp1_health.duckdb"


def load_correlation_data() -> pd.DataFrame:
    """Read the mart_correlation table from DuckDB."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("SELECT * FROM mart_correlation").fetchdf()
    con.close()
    return df


def compute_correlations(df: pd.DataFrame) -> dict:
    """Compute Pearson and Spearman correlations for key variable pairs."""
    results = {}

    pairs = [
        ("trial_count", "slope_change", "Trial density vs. obesity slope change"),
        ("trial_count", "post_avg_obesity", "Trial density vs. post-approval avg obesity"),
        ("avg_median_income", "slope_change", "Income vs. obesity slope change"),
        ("avg_insurance_rate", "slope_change", "Insurance rate vs. obesity slope change"),
    ]

    for x_col, y_col, label in pairs:
        valid = df[[x_col, y_col]].dropna()
        if len(valid) < 5:
            continue

        pearson_r, pearson_p = stats.pearsonr(valid[x_col], valid[y_col])
        spearman_r, spearman_p = stats.spearmanr(valid[x_col], valid[y_col])

        results[label] = {
            "n": len(valid),
            "pearson_r": round(pearson_r, 4),
            "pearson_p": round(pearson_p, 4),
            "spearman_r": round(spearman_r, 4),
            "spearman_p": round(spearman_p, 4),
        }

    return results


def run_analysis() -> dict:
    """Full analysis pipeline: load data, compute correlations, print summary."""
    df = load_correlation_data()
    results = compute_correlations(df)

    print("\n  Correlation Analysis Results")
    print("  " + "=" * 65)
    for label, vals in results.items():
        print(f"\n  {label}")
        print(f"    n = {vals['n']}")
        print(f"    Pearson  r = {vals['pearson_r']:+.4f}  (p = {vals['pearson_p']:.4f})")
        print(f"    Spearman ρ = {vals['spearman_r']:+.4f}  (p = {vals['spearman_p']:.4f})")

    return results


if __name__ == "__main__":
    run_analysis()
