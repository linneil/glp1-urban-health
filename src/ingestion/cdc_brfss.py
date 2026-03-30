"""Download CDC BRFSS state-level obesity prevalence data.

BRFSS (Behavioral Risk Factor Surveillance System) provides self-reported
obesity rates (BMI >= 30) by US state, published annually.

Data source: CDC Chronic Disease Indicators API (Socrata).
"""

from pathlib import Path

import httpx
import pandas as pd

# CDC Socrata open-data endpoint for Nutrition, Physical Activity, and Obesity
# This dataset includes state-level adult obesity prevalence from BRFSS
SOCRATA_URL = "https://data.cdc.gov/resource/hn4x-zwk7.json"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def fetch_obesity_rates(limit: int = 50000) -> pd.DataFrame:
    """Fetch state-level adult obesity prevalence from CDC Socrata API.

    Filters to the 'Percent of adults aged 18 years and older who have obesity'
    indicator, overall (not stratified by age/race/gender subgroups).
    """
    params = {
        "$where": (
            "question='Percent of adults aged 18 years and older who have obesity'"
        ),
        "$select": "yearstart,locationabbr,locationdesc,data_value,sample_size,stratification1",
        "$order": "yearstart,locationabbr",
        "$limit": str(limit),
    }
    resp = httpx.get(SOCRATA_URL, params=params, timeout=60)
    resp.raise_for_status()

    df = pd.DataFrame(resp.json())
    if df.empty:
        print("  WARNING: CDC API returned no records")
        return df

    df = df.rename(
        columns={
            "yearstart": "year",
            "locationabbr": "state_abbr",
            "locationdesc": "state_name",
            "data_value": "obesity_pct",
            "sample_size": "sample_size",
            "stratification1": "stratification",
        }
    )
    # Keep only the "Total" (unstratified) rows for the main analysis
    df = df[df["stratification"] == "Total"].copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["obesity_pct"] = pd.to_numeric(df["obesity_pct"], errors="coerce")
    df["sample_size"] = pd.to_numeric(df["sample_size"], errors="coerce").astype("Int64")

    # Drop US territories for cleaner state-level analysis
    territories = {"GU", "PR", "VI", "AS", "MP"}
    df = df[~df["state_abbr"].isin(territories)]

    df = df.drop(columns=["stratification"]).reset_index(drop=True)
    return df


def save_raw() -> Path:
    """Fetch and persist obesity rate data to parquet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "cdc_obesity_rates.parquet"

    df = fetch_obesity_rates()
    df.to_parquet(out, index=False)
    print(f"  Saved {len(df)} state-year obesity records → {out}")
    return out


if __name__ == "__main__":
    save_raw()
