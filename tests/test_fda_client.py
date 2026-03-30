"""Tests for FDA ingestion client."""

import pandas as pd

from src.ingestion.fda_client import GLP1_MILESTONES


def test_milestones_structure():
    """Curated milestones table has expected columns and non-empty rows."""
    assert isinstance(GLP1_MILESTONES, pd.DataFrame)
    assert len(GLP1_MILESTONES) >= 9
    for col in ("brand_name", "generic_name", "approval_date", "indication"):
        assert col in GLP1_MILESTONES.columns


def test_milestones_dates_are_datetime():
    assert pd.api.types.is_datetime64_any_dtype(GLP1_MILESTONES["approval_date"])


def test_milestones_sorted():
    dates = GLP1_MILESTONES["approval_date"].tolist()
    assert dates == sorted(dates)


def test_key_drugs_present():
    brands = set(GLP1_MILESTONES["brand_name"].str.lower())
    for expected in ("ozempic", "wegovy", "mounjaro", "zepbound"):
        assert expected in brands, f"{expected} missing from milestones"
