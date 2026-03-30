"""One-command pipeline: ingest all sources → build DuckDB → run analysis."""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    start = time.time()
    print("=" * 60)
    print("GLP-1 × Urban Health — Data Pipeline")
    print("=" * 60)

    # Step 1: Ingest raw data from APIs
    sources = [
        ("1/4", "FDA GLP-1 approval data", "src.ingestion.fda_client"),
        ("2/4", "ClinicalTrials.gov data", "src.ingestion.clinicaltrials"),
        ("3/4", "CDC BRFSS obesity rates", "src.ingestion.cdc_brfss"),
        ("4/4", "Census ACS demographics", "src.ingestion.census_client"),
    ]
    for step, label, module_path in sources:
        print(f"\n[{step}] Fetching {label}...")
        try:
            mod = __import__(module_path, fromlist=["save_raw"])
            mod.save_raw()
        except Exception as e:
            print(f"  ERROR: {label} failed — {e}")
            print(f"  Continuing with remaining sources...")

    # Step 2: Build DuckDB staging + mart layer
    print("\n[5/5] Building DuckDB analytical layer...")
    from src.transforms.staging import build_database
    build_database()

    # Step 3: Run correlation analysis
    print("\n[6/6] Running correlation analysis...")
    try:
        from src.analysis.correlation import run_analysis
        run_analysis()
    except Exception as e:
        print(f"  WARNING: Correlation analysis skipped — {e}")

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"Pipeline complete in {elapsed:.1f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
