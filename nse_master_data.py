"""
Static NSE master data — sector and listing date for the Nifty 500 universe.

Deliberately does NOT store company names: config.NIFTY_500_MAP already
owns symbol -> company name (used by the Signal Screener's Nifty 500
option). Duplicating it here would create two sources of truth that can
drift apart. This module only adds the two things config.py doesn't
have: sector and listing date.

Source files (manual quarterly refresh, not live-fetched):
  - https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv
  - https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
Merged into data/nifty500_master.csv — re-run scripts/build_nifty500_master.py
(see bottom of this file for the merge logic, kept here for the next refresh)
to regenerate.

Single lookup point for sector/listing-date data — momentum_engine.py and
the momentum filters import from here, nothing else re-parses the CSV or
re-hardcodes a symbol/sector mapping.
"""

import csv
from datetime import date, datetime
from pathlib import Path
from functools import lru_cache

_DATA_FILE = Path(__file__).parent / "data" / "nifty500_master.csv"


class MasterDataError(Exception):
    """Raised when nifty500_master.csv is missing, malformed, or out of
    sync with config.NIFTY_500_MAP — fails loudly rather than silently
    screening a partial/wrong universe."""


@lru_cache(maxsize=1)
def load_master_data() -> dict:
    """Returns {symbol: {"sector": str, "listing_date": date}}"""
    if not _DATA_FILE.exists():
        raise MasterDataError(f"{_DATA_FILE} not found — see module docstring for source files")

    records = {}
    with open(_DATA_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing_cols = {"symbol", "sector", "listing_date"} - set(reader.fieldnames or [])
        if missing_cols:
            raise MasterDataError(f"{_DATA_FILE} missing column(s): {missing_cols}")
        for row in reader:
            try:
                listing_dt = datetime.strptime(row["listing_date"], "%Y-%m-%d").date()
            except ValueError as e:
                raise MasterDataError(f"Bad listing_date for {row.get('symbol')}: {e}")
            records[row["symbol"]] = {"sector": row["sector"], "listing_date": listing_dt}
    return records


def check_consistency_with_config(nifty_500_map_keys) -> dict:
    """
    Compares this file's symbols against config.NIFTY_500_MAP's keys.
    Returns {"only_in_master": [...], "only_in_config": [...]} — both
    empty means the two are in sync. Call this from a test, not at
    import time (import-time validation would crash the app on any
    future single-symbol drift instead of surfacing it as a test failure).
    """
    master_symbols = set(load_master_data().keys())
    config_symbols = set(nifty_500_map_keys)
    return {
        "only_in_master": sorted(master_symbols - config_symbols),
        "only_in_config": sorted(config_symbols - master_symbols),
    }


def get_sector(symbol: str) -> str | None:
    return load_master_data().get(symbol, {}).get("sector")


def get_listing_date(symbol: str) -> date | None:
    return load_master_data().get(symbol, {}).get("listing_date")


def days_listed(symbol: str, as_of: date | None = None) -> int | None:
    listed = get_listing_date(symbol)
    if listed is None:
        return None
    as_of = as_of or date.today()
    return (as_of - listed).days


def sector_list() -> list:
    """Distinct sectors, sorted, for the filter dropdown."""
    return sorted({v["sector"] for v in load_master_data().values()})


# ---------------------------------------------------------------------------
# Merge script — re-run when refreshing data/nifty500_master.csv from new
# NSE downloads. Not called at import time; kept here so the merge logic
# lives next to the data it produces, not lost in chat history.
#
# Usage: python nse_master_data.py path/to/ind_nifty500list.csv path/to/EQUITY_L.csv
# ---------------------------------------------------------------------------
def _rebuild_master_csv(nifty500_csv_path: str, equity_l_csv_path: str) -> None:
    sectors = {}
    with open(nifty500_csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sectors[row["Symbol"].strip()] = row["Industry"].strip()

    listing_dates = {}
    with open(equity_l_csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        for row in reader:
            listing_dates[row["SYMBOL"].strip()] = row["DATE OF LISTING"].strip()

    rows, skipped = [], []
    for sym, sector in sorted(sectors.items()):
        raw_date = listing_dates.get(sym)
        if not raw_date:
            skipped.append(sym)
            continue
        try:
            dt = datetime.strptime(raw_date, "%d-%b-%Y")
        except ValueError:
            skipped.append(sym)
            continue
        rows.append({"symbol": sym, "sector": sector, "listing_date": dt.strftime("%Y-%m-%d")})

    _DATA_FILE.parent.mkdir(exist_ok=True)
    with open(_DATA_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "sector", "listing_date"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {_DATA_FILE}. Skipped (no listing date match): {skipped}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python nse_master_data.py <ind_nifty500list.csv> <EQUITY_L.csv>")
        sys.exit(1)
    _rebuild_master_csv(sys.argv[1], sys.argv[2])
