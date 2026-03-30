"""Fetch GLP-1 receptor agonist drug approval records from OpenFDA."""

from pathlib import Path

import httpx
import pandas as pd

BASE_URL = "https://api.fda.gov/drug/drugsfda.json"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# GLP-1 receptor agonist generic names approved for obesity or T2D
GLP1_GENERICS = [
    "semaglutide",
    "liraglutide",
    "tirzepatide",
    "dulaglutide",
    "exenatide",
]

# Curated milestone approvals (FDA first-approval dates for key indications)
GLP1_MILESTONES = pd.DataFrame(
    [
        ("Byetta", "exenatide", "2005-04-28", "T2D"),
        ("Victoza", "liraglutide", "2010-01-25", "T2D"),
        ("Trulicity", "dulaglutide", "2014-09-18", "T2D"),
        ("Saxenda", "liraglutide", "2014-12-23", "Obesity"),
        ("Ozempic", "semaglutide", "2017-12-05", "T2D"),
        ("Rybelsus", "semaglutide", "2019-09-20", "T2D (oral)"),
        ("Wegovy", "semaglutide", "2021-06-04", "Obesity"),
        ("Mounjaro", "tirzepatide", "2022-05-13", "T2D"),
        ("Zepbound", "tirzepatide", "2023-11-08", "Obesity"),
    ],
    columns=["brand_name", "generic_name", "approval_date", "indication"],
)
GLP1_MILESTONES["approval_date"] = pd.to_datetime(GLP1_MILESTONES["approval_date"])


def fetch_fda_approvals() -> pd.DataFrame:
    """Query OpenFDA for GLP-1 drug approval records.

    Returns a DataFrame with brand name, generic name, approval date,
    sponsor, and application number.
    """
    records = []
    for generic in GLP1_GENERICS:
        search = f'openfda.generic_name:"{generic}"'
        params = {"search": search, "limit": 100}
        resp = httpx.get(BASE_URL, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  WARNING: OpenFDA returned {resp.status_code} for {generic}")
            continue
        data = resp.json()
        for result in data.get("results", []):
            brand = (
                result.get("openfda", {}).get("brand_name", [""])[0]
                if result.get("openfda")
                else ""
            )
            sponsor = result.get("sponsor_name", "")
            app_no = result.get("application_number", "")
            for submission in result.get("submissions", []):
                if submission.get("submission_type") == "ORIG":
                    records.append(
                        {
                            "generic_name": generic,
                            "brand_name": brand,
                            "sponsor": sponsor,
                            "application_number": app_no,
                            "approval_date": submission.get("submission_status_date"),
                            "submission_type": submission.get("submission_type"),
                        }
                    )
    df = pd.DataFrame(records)
    if not df.empty:
        df["approval_date"] = pd.to_datetime(df["approval_date"], format="%Y%m%d", errors="coerce")
        df = df.sort_values("approval_date").reset_index(drop=True)
    return df


def save_raw() -> Path:
    """Fetch and persist FDA approval data to parquet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "fda_glp1_approvals.parquet"

    df_api = fetch_fda_approvals()
    # Merge API results with curated milestones to ensure completeness
    df = pd.concat([GLP1_MILESTONES, df_api], ignore_index=True)
    df = df.drop_duplicates(subset=["brand_name", "approval_date"], keep="first")
    df = df.sort_values("approval_date").reset_index(drop=True)

    df.to_parquet(out, index=False)
    print(f"  Saved {len(df)} FDA approval records → {out}")
    return out


if __name__ == "__main__":
    save_raw()
