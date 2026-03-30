"""Fetch GLP-1-related clinical trials from ClinicalTrials.gov API v2."""

from pathlib import Path

import httpx
import pandas as pd

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# Search for GLP-1 RA drugs used for obesity/diabetes
QUERY = "semaglutide OR tirzepatide OR liraglutide OR dulaglutide OR exenatide"
CONDITION_FILTER = "obesity OR overweight OR type 2 diabetes"


def fetch_trials(max_pages: int = 20) -> pd.DataFrame:
    """Page through ClinicalTrials.gov v2 API and return a flat DataFrame.

    Each row represents one trial with its locations expanded to US states.
    """
    all_studies: list[dict] = []
    page_token: str | None = None

    for page in range(max_pages):
        params: dict = {
            "query.term": QUERY,
            "query.cond": CONDITION_FILTER,
            "filter.geo": "distance(39.8,-98.6,3000km)",
            "countTotal": "true",
            "pageSize": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = httpx.get(
                BASE_URL,
                params=params,
                timeout=30,
                follow_redirects=True,
            )
        except httpx.HTTPError as e:
            print(f"  WARNING: ClinicalTrials.gov request failed on page {page}: {e}")
            break
        if resp.status_code == 403:
            print("  INFO: ClinicalTrials.gov returned 403 — trying urllib fallback...")
            return _fetch_trials_urllib(max_pages)
        if resp.status_code != 200:
            print(f"  WARNING: ClinicalTrials.gov returned {resp.status_code} on page {page}")
            break

        body = resp.json()
        studies = body.get("studies", [])
        if not studies:
            break
        all_studies.extend(studies)
        print(f"    page {page}: fetched {len(studies)} studies (total: {len(all_studies)})")

        page_token = body.get("nextPageToken")
        if not page_token:
            break

    return _flatten(all_studies)


def _fetch_trials_urllib(max_pages: int = 20) -> pd.DataFrame:
    """Fallback fetcher using urllib (bypasses httpx encoding issues)."""
    import json
    import urllib.request
    import urllib.parse

    all_studies: list[dict] = []
    page_token: str | None = None

    # Fetch each GLP-1 drug separately to avoid complex query encoding issues
    drugs = ["semaglutide", "tirzepatide", "liraglutide", "dulaglutide", "exenatide"]
    conditions = ["obesity", "type 2 diabetes"]

    for drug in drugs:
        for condition in conditions:
            page_token = None
            for page in range(max_pages):
                params = {
                    "query.term": drug,
                    "query.cond": condition,
                    "countTotal": "true",
                    "pageSize": "50",
                }
                if page_token:
                    params["pageToken"] = page_token

                url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
                try:
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        body = json.loads(resp.read())
                except Exception as e:
                    print(f"  WARNING: urllib failed for {drug}/{condition} page {page}: {e}")
                    break

                studies = body.get("studies", [])
                if not studies:
                    break
                all_studies.extend(studies)

                page_token = body.get("nextPageToken")
                if not page_token:
                    break

            print(f"    {drug} × {condition}: {len(all_studies)} cumulative records")

    # Deduplicate by NCT ID
    seen: set[str] = set()
    unique: list[dict] = []
    for s in all_studies:
        nct = s.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "")
        if nct and nct not in seen:
            seen.add(nct)
            unique.append(s)
    print(f"    Deduplicated: {len(unique)} unique trials")

    return _flatten(unique)


def _flatten(studies: list[dict]) -> pd.DataFrame:
    """Flatten nested study JSON into one row per study-location pair."""
    rows = []
    for study in studies:
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        locations = (
            proto.get("contactsLocationsModule", {}).get("locations", [])
        )

        base = {
            "nct_id": ident.get("nctId"),
            "title": ident.get("briefTitle"),
            "status": status.get("overallStatus"),
            "start_date": status.get("startDateStruct", {}).get("date"),
            "completion_date": status.get("completionDateStruct", {}).get("date"),
            "phase": ", ".join(design.get("phases", [])),
            "enrollment": design.get("enrollmentInfo", {}).get("count"),
        }

        us_locations = [
            loc for loc in locations if loc.get("country", "").upper() == "UNITED STATES"
        ]
        if us_locations:
            for loc in us_locations:
                rows.append(
                    {
                        **base,
                        "state": loc.get("state", ""),
                        "city": loc.get("city", ""),
                        "facility": loc.get("facility", ""),
                    }
                )
        else:
            rows.append({**base, "state": "", "city": "", "facility": ""})

    df = pd.DataFrame(rows)
    for col in ("start_date", "completion_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def save_raw() -> Path:
    """Fetch and persist clinical trial data to parquet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "clinicaltrials_glp1.parquet"

    df = fetch_trials()
    df.to_parquet(out, index=False)
    print(f"  Saved {len(df)} trial-location records → {out}")
    return out


if __name__ == "__main__":
    save_raw()
