# Momentum Screener — Sector View (Final, as built)
**Status:** Implemented, tested, verified live. 91/91 tests passing.
**Supersedes:** sector_view_requirements.md (the pre-development draft — this reflects what actually shipped, including the one design change made during build).

---

## 1. Structure
- Third tab on the Momentum Screener page: **Screener | Sector View | How this works**.
- Sector View has its own "Generate sector view" button and its own Stock Universe selector — independent of the Screener tab's fetch, but sharing the same cache **by universe name**: picking the same universe (e.g. Nifty 500) in either tab reuses the other tab's already-fetched data; picking a different universe triggers its own fetch under its own cache key.

## 2. Table columns (as built — ₹-based avg/median dropped, per your call)
| Column | Definition |
|---|---|
| Sector | — |
| Avg 12mo returns % | Equal-weighted mean of `return_12mo_pct` across the sector's stocks |
| Med 12mo returns % | Median of the same — less sensitive to a few extreme performers |
| Avg 30d / 60d / 90d / 180d returns % | Mean of the corresponding per-stock column |
| Vs universe 12mo returns (pts) | Sector's avg 12mo return − average across the WHOLE fetched universe (all sectors), computed pre-filter |
| # of stocks | Count of stocks in this sector in the current universe |
| Stocks up (12mo) | "N (P%)" — count/% with a positive 12mo return, denominator = stocks with a computable value, not total sector size |
| Stocks > N-day DMA | "N (P%)" — same pattern, N = the Price Trend selector on this tab |
| Avg Sharpe ratio | Equal-weighted mean of per-stock Sharpe ratio |
| Avg Annual traded turnover ₹cr | Equal-weighted mean of per-stock annual traded turnover |
| Avg Relative Volume % | Equal-weighted mean of per-stock Relative Volume % (Option A, as decided) |

## 3. Filters
| Filter | Role |
|---|---|
| Stock Universe | Scope (Nifty 500 / Nifty 100 / Custom) |
| Sector | Eligibility — narrows which sector rows show |
| Min avg 12mo returns % | Eligibility, blank = no filter |
| Min Sharpe ratio | Eligibility, blank = no filter |
| Price Trend (N-day moving average) | **Parameter** — sets N for the breadth column only, doesn't remove sector rows |
| Relative Volume baseline (days) | **Parameter** — sets the denominator for Avg Relative Volume % only |

## 4. Explicitly stated in "How this works" (not just in this doc)
- **Equal-weighting is explicit**, not a silent default — stated in the tab caption and repeated in the "How this works" section.
- **Cap-weighting deferred**: would need a separate market-cap fetch (yfinance `.info`/`fast_info` — a heavier, less reliable call than the OHLCV history already pulled at 500-symbol scale). Documented, not silently approximated.
- **Cross-sectional dispersion deferred** (spread of returns *across* a sector's stocks at one point in time — different from a single stock's own volatility over time).
- **No drill-down from a sector row into its stocks yet** — noted as a natural next question, not built.

## 5. One implementation-time design change from the original draft
The original draft assumed the Sector View might read the Screener tab's already-selected filter values. In practice, since Sector View needed its own independent Stock Universe control (per your confirmed filter list) and its own Price Trend / RVOL baseline parameters (which feed sector-level breadth/volume columns differently than the Screener tab's per-stock eligibility use), it was built with **fully independent widgets and its own fetch trigger**, sharing only the underlying cache (by universe name) and the fetch/cache *logic* (extracted into one shared function both tabs call, so the two can't drift into inconsistent caching behavior).

## 6. Testing
- 11 new unit tests for `build_sector_table()` / `apply_sector_filters()` — verified by hand-calculation first, including: `None`-sector exclusion from rows but inclusion in the universe average, median vs. mean divergence on skewed data, breadth denominators excluding missing values (not silently counting them as "not up"/"not above DMA"), empty-input handling.
- One new E2E test using real Nifty 500 symbols across two real sectors (confirmed against actual `nse_master_data.py` lookups, not assumed), checking the full fetch → aggregate → filter → sort → display pipeline.
- Live-verified via `streamlit.testing.v1.AppTest`: actual "Generate sector view" clicks, real multi-sector output inspected, empty-sector-data warning path confirmed, all three app entry points boot with zero exceptions.
- **Bug caught and fixed during this work, unrelated to Sector View itself:** the test suite failed 30/79 on a fresh clone due to pandas 3.0.2 (installed in the environment) having an off-by-one edge case in `pd.bdate_range(periods=N)`. This only affected the test fixture's synthetic-data generator, not production code — fixed by sizing arrays off the actual generated index length.

## Still open / deferred (unchanged from the pre-build discussion)
- Cap-weighted sector averages
- Cross-sectional dispersion metric
- Drill-down from sector row to constituent stocks
- US indices (separately discussed, on hold — not part of this scope)
