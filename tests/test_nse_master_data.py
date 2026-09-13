"""
Unit tests — nse_master_data.py, using the real data/nifty500_master.csv
shipped in the repo (this IS the data the app will actually load, so
testing against it directly, not a fixture copy, is the point).
"""
import csv
import pytest

import config
import nse_master_data as nmd


@pytest.fixture(autouse=True)
def _clear_cache():
    nmd.load_master_data.cache_clear()
    yield
    nmd.load_master_data.cache_clear()


def test_loads_500_rows():
    data = nmd.load_master_data()
    assert len(data) == 500


def test_matches_config_nifty_500_map_exactly():
    """The whole point of this file existing separately from config.py:
    it must describe the SAME 500 symbols, or sector/listing filters
    would silently apply to the wrong universe. This is the regression
    test that would catch that drift."""
    diff = nmd.check_consistency_with_config(config.NIFTY_500_MAP.keys())
    assert diff["only_in_master"] == []
    assert diff["only_in_config"] == []


def test_sector_list_has_no_duplicates_and_is_sorted():
    sectors = nmd.sector_list()
    assert sectors == sorted(set(sectors))
    assert len(sectors) > 0


def test_known_symbol_lookup():
    # TCS is a Nifty 500 constituent with a long listing history — a
    # stable sentinel that won't change across data refreshes.
    sector = nmd.get_sector("TCS")
    listing_date = nmd.get_listing_date("TCS")
    assert sector is not None
    assert listing_date is not None
    assert listing_date.year < 2020  # TCS has been listed for decades


def test_unknown_symbol_returns_none():
    assert nmd.get_sector("NOTAREALSYMBOL") is None
    assert nmd.get_listing_date("NOTAREALSYMBOL") is None
    assert nmd.days_listed("NOTAREALSYMBOL") is None


def test_days_listed_is_positive_for_known_symbol():
    assert nmd.days_listed("TCS") > 0


def test_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(nmd, "_DATA_FILE", tmp_path / "does_not_exist.csv")
    nmd.load_master_data.cache_clear()
    with pytest.raises(nmd.MasterDataError):
        nmd.load_master_data()


def test_malformed_file_missing_column_raises(tmp_path, monkeypatch):
    bad_file = tmp_path / "bad.csv"
    with open(bad_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "sector"])  # missing listing_date
        writer.writeheader()
        writer.writerow({"symbol": "X", "sector": "IT"})
    monkeypatch.setattr(nmd, "_DATA_FILE", bad_file)
    nmd.load_master_data.cache_clear()
    with pytest.raises(nmd.MasterDataError):
        nmd.load_master_data()


def test_malformed_date_raises(tmp_path, monkeypatch):
    bad_file = tmp_path / "bad_date.csv"
    with open(bad_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "sector", "listing_date"])
        writer.writeheader()
        writer.writerow({"symbol": "X", "sector": "IT", "listing_date": "not-a-date"})
    monkeypatch.setattr(nmd, "_DATA_FILE", bad_file)
    nmd.load_master_data.cache_clear()
    with pytest.raises(nmd.MasterDataError):
        nmd.load_master_data()
