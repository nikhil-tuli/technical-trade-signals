"""
'How this works' content — rendered as a tab inside each screener page
(pages/0_Signal_Screener.py, pages/1_Momentum_Screener.py), not a
separate sidebar page. See those files for why (st.tabs vs st.navigation
state-persistence tradeoff).

Purely explanatory content, no logic. Hand-maintained in sync with the
actual current values in config.py — if a default or threshold changes
there, the matching text below needs a manual update or it will drift
out of sync and describe outdated behavior. Same caveat as the original
standalone How This Works page had; carried over, not introduced by
this refactor.
"""
import streamlit as st

from config import (
    MOMENTUM_DMA_DEFAULT,
    MOMENTUM_LIQUIDITY_LOOKBACK_DAYS,
    MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT,
    MOMENTUM_VOLUME_RECENT_DAYS,
    MOMENTUM_MIN_LISTING_MONTHS_DEFAULT,
    MOMENTUM_LOOKBACK_MONTHS,
    MOMENTUM_MASTER_DATA_ASOF,
    MOMENTUM_RISK_FREE_RATE_PCT,
    MOMENTUM_RISK_FREE_RATE_ASOF,
    MAX_CUSTOM_TICKERS,
)


def render_signal_explainer():
    st.markdown("""
## Purpose

- This tool looks for a small number of higher-conviction, less risk-prone
  setups — not every possible trade.
- A signal only appears once **4 hard checks** pass together; extra
  indicators are shown as context, not gates — final judgment is still
  yours.
- Settings (lookback windows, spacing, thresholds) automatically adjust
  based on whether you pick **Short-term** or **Long-term trade**.
- Source logic: Zerodha [Varsity's](https://zerodha.com/varsity/chapter/finale-helping-get-started/)
  technical analysis series — the source logic this tool is built around.

---

## The 4 Hard Filters
*(a signal only shows if all 4 pass)*

### a) Candlestick Pattern

| Pattern | Direction | Required prior trend | Core rule |
|---|---|---|---|
| Marubozu | Either | None | Almost no shadow — body fills nearly the full candle |
| Hammer | Bullish | Downtrend | Small body near the top, long lower shadow |
| Shooting Star | Bearish | Uptrend | Small body near the bottom, long upper shadow |
| Bullish Engulfing | Bullish | Downtrend | Green candle fully covers the prior red candle's body |
| Bearish Engulfing | Bearish | Uptrend | Red candle fully covers the prior green candle's body |
| Morning Star | Bullish | Downtrend | 3 candles: big fall, small pause, strong recovery |
| Evening Star | Bearish | Uptrend | 3 candles: big rise, small pause, strong fall |

"Prior trend" is checked over the last 7 candles (Short-term) or 15
candles (Long-term).

### b) Volume Confirmation

- The signal day's volume must be at or above its own recent average
  (default: 10-day average, editable).
- Confirms real participation behind the move, not a quiet, low-conviction
  candle.

### c) Support & Resistance Validation

- The tool looks back over recent price history (3–6 months Short-term,
  12–18 months Long-term) for price levels the stock has repeatedly
  reacted to.
- A level only counts if price touched it **3 or more times**, spaced at
  least 7 days (Short-term) or 15 days (Long-term) apart — this filters
  out coincidence and noise.
- Nearby touches (within 1% of each other) are grouped into one zone, not
  counted as separate levels.
- The stop-loss (set by the candlestick pattern itself) must sit close to
  one of these zones — within 4% by default, editable. If it doesn't, the
  setup is rejected outright.

### d) Reward:Risk

- Target = the near edge of the next Support/Resistance zone in the
  trade's direction.
- This target, measured against the stop-loss, must offer at least **2x
  reward for every 1x risked** (default, editable).

---

## Additional Info
*(shown for context — never filters)*

- **RSI (14-day)** — momentum gauge; traditionally above 70 = overbought,
  below 30 = oversold. Here, we just check if RSI is above 50 (bullish
  lean) or below 50 (bearish lean).
- **MACD (12/26 EMA)** — MACD line above its signal line = bullish; below
  = bearish.
- **Supertrend** — a trend line derived from price volatility; price above
  it = bullish, below it = bearish.
- **Aroon (14-day)** — measures how recently price hit a new high vs. a
  new low; more recent highs = bullish, more recent lows = bearish.
- Shown as "N/4 confirming" — how many of these four currently agree with
  the signal's direction.

---

## Primary Trend
*(also context, not a filter)*

- Based on a moving average — **20-day** in Short-term mode, **50-day** in
  Long-term mode.
- **Up** — price is currently above that moving average, **and** the
  average itself is higher today than it was **12 days ago**. Both
  conditions must hold — price being above the average alone isn't
  enough if the average itself is still falling.
- **Down** — the mirror case: price is below the moving average, **and**
  the average is lower today than it was 12 days ago.
- **Sideways** — price has crossed back and forth over the moving
  average more than once in the last 10 candles — a single crossing is
  just a trend starting, not sideways movement.
""")


def render_momentum_explainer():
    st.markdown(f"""
**Inspiration for this tool:**
- [youtube.com/watch?v=eMuGV8t3ejo](https://www.youtube.com/watch?v=eMuGV8t3ejo)
- [youtube.com/watch?v=HZ2IoyMvSCM](https://www.youtube.com/watch?v=HZ2IoyMvSCM)

---

## Purpose

- Ranks the selected stock universe (Nifty 500, Nifty 100, or your own
  Custom list) by momentum — **not** a gated pattern screen like the
  Signal Screener. Nothing is filtered out for you by default beyond
  what you set below; you sort and read the table yourself. Daily
  **adjusted** close (splits/dividends already accounted for).
- Uses both relative momentum (sector-wise comparison) and absolute
  momentum (returns and % returns over multiple time periods), while
  factoring in volatility, traded volume, liquidity, and company
  turnover alongside the return numbers themselves — not returns in
  isolation.
- Sector comes from NSE's own Industry classification, manually
  refreshed from NSE's public data on {MOMENTUM_MASTER_DATA_ASOF} — not fetched live.
- Informational only — this tool doesn't recommend trades, it surfaces
  numbers so you can decide.

---

## Momentum columns

- **Current price**, **52-week high**, and **N-day DMA** — shown side by
  side. 52-week high uses the highest daily High over the trailing 252
  trading days (~52 weeks); for a stock listed less than 252 trading
  days ago, it's effectively an all-time high instead. The DMA is the
  same moving average used by the trend filter below, so you can see
  how close a stock is to its own trend line, not just pass/fail.
- **12-month returns** — ₹ and % change over the trailing {MOMENTUM_LOOKBACK_MONTHS} months,
  shown as two separate columns. An "exclude last month" toggle drops
  the most recent ~21 trading days from the window — useful since very
  recent moves tend to partially reverse (a well-known momentum-investing
  pattern). This uses **252 trading days** (12 months × 21 trading
  days/month) — roughly a calendar year once weekends/holidays are
  excluded.
- **Sector avg 12mo returns %** and **Vs sector 12mo returns (pts)** —
  relative momentum. The first is the average 12mo return across every
  stock in the same sector, computed from the full fetched universe
  before any filters are applied (so it's the sector's real average, not
  biased by whichever stocks happened to survive other filters). The
  second is this stock's own 12mo return minus that sector average, in
  percentage points — positive means it's outperforming its sector,
  negative means it's lagging. This is the "is this stock leading or
  lagging its peers" question, separate from whether it's up in
  absolute terms. Blank for Custom tickers with no known sector.
- **N-day returns** — % change in close price over the trailing 30 / 60
  / 90 / 180 trading days. Shown side by side so you can see whether a
  move is accelerating or fading. (A 252-day version was dropped — it's
  numerically identical to 12-month returns whenever "exclude last
  month" is off, so it was a redundant column.)
- **Sharpe ratio** — (12-month return % − risk-free rate) ÷ annualized
  volatility. Risk-free rate assumed: {MOMENTUM_RISK_FREE_RATE_PCT:g}% (≈India's 91-day T-bill, as of
  {MOMENTUM_RISK_FREE_RATE_ASOF} — a manually-set value, not fetched live). Rough compass:
  below ~0.5 is weak, ~1.0 is decent, ~1.5-2.0 is good, above ~2.0 is
  strong — not a hard rule, comparing stocks within this table matters
  more than comparing any single one against these bands in isolation.
- **Stdev of returns % (252d)** — standard deviation of day-to-day %
  price changes over a FIXED trailing 252-trading-day window — always
  this window, unaffected by the "exclude last month" toggle (that
  toggle only shifts the 12-month return figures, not this).
- **Ulcer Index (252d)** — captures depth AND duration of declines over
  the trailing 252 days, not just how big the swings are: each day's %
  drawdown from its own running high, squared, averaged, then
  square-rooted. A slow grinding slide scores high here even with low
  day-to-day volatility, which Stdev of returns alone wouldn't catch.
  Lower is better; 0 means no drawdown at all in the window.
- **1Y Max Drawdown %** — the single largest peak-to-trough decline over
  the trailing 252 trading days, shown as a negative number (closer to
  0 is better).
- **RSQ** — R² (0 to 1) of a linear regression of log(price) against
  time, over the SAME N-day window as the "N-day lookback" filter below
  (the column header updates to show whichever N you've picked). Higher
  = a smoother, more consistent trend; lower = choppier, less
  directional. This is trend QUALITY, not direction or size — a smooth
  downtrend and a smooth uptrend can both score high.
- **Hit rate** — % of trading days in the 12-month window that closed
  higher than the day before. A simple, intuitive read on consistency.
- **Relative Volume %** — the last {MOMENTUM_VOLUME_RECENT_DAYS}-day AVERAGE volume as a % of
  the {MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT}-day average (both configurable — the column header updates
  to show whichever baseline you've picked). The numerator is
  deliberately a {MOMENTUM_VOLUME_RECENT_DAYS}-day average, not a single day's volume, so this is a
  smoothed version of the "Relative Volume" concept traders commonly
  use, not a literal today-vs-average snapshot. Above 100% means recent
  activity is running above the stock's own norm; below 100% means it's
  quieter than usual. Shown for context — it does not filter the table.
- **Annual traded turnover ₹cr** — the ACTUAL trailing {MOMENTUM_LIQUIDITY_LOOKBACK_DAYS}-trading-day
  SUM (not average) of daily traded value (Close price × Volume), in
  ₹ crore — a real year of turnover, not a projection from a shorter
  window. Same figure the Min annual traded turnover filter checks
  against.
- **Listing date** — when the stock started trading, shown as the last
  column for reference alongside the listing-period filter below. From
  NSE data manually fetched on {MOMENTUM_MASTER_DATA_ASOF} — not live.

Table opens sorted by 12-month return, but every column header is
click-to-sort — no separate sort control needed.

---

## Filters

- **Stock Universe** — Nifty 500 (default), Nifty 100, or Custom (your
  own comma-separated ticker list, same rules as the Signal Screener's
  Custom mode: max {MAX_CUSTOM_TICKERS} tickers, not saved between sessions, always
  fetched fresh rather than using the shared daily cache). Sector and
  Listing period filters are unavailable for Custom, since that
  reference data only covers the Nifty 500 universe.
- **N-day lookback — DMA trend filter & RSQ** — sets N for two things
  at once: the moving-average trend filter (price must be above its
  N-day DMA — a single condition, no slope check, unlike the Signal
  Screener's Primary Trend) AND the RSQ trend-quality column's
  regression window above. Options: 30/60/90/180/252, default {MOMENTUM_DMA_DEFAULT}-day.
  The actual price, DMA value, and RSQ used are all visible as columns
  in the table.
- **Sector** — NSE's sector classification, from the dropdown.
- **Listing period** — minimum months since the stock listed (default {MOMENTUM_MIN_LISTING_MONTHS_DEFAULT}
  months) — filters out very recently listed names prone to IPO-pop
  volatility. The actual listing date is shown in the table, sourced
  from NSE data manually fetched on {MOMENTUM_MASTER_DATA_ASOF} (not live).
- **Min annual traded turnover ₹cr** — an eligibility gate: a stock
  below this simply doesn't appear, regardless of how strong its
  momentum looks — the concern is whether you could actually trade it
  at size, not whether the number is impressive. Same wording and
  methodology as the matching table column, just with a "Min" threshold
  applied.
- **Min last closed price ₹** — excludes anything below the price you
  set. Blank = disabled, every stock shown regardless of price.
- **Min Sharpe ratio** — excludes stocks below this Sharpe ratio (see
  the column above for the exact formula and the assumed risk-free
  rate). Blank = disabled. Note: since blank is how this filter is
  disabled, a threshold of exactly 0.0 (return exactly matching the
  risk-free rate) IS still settable — type 0 explicitly rather than
  leaving the box empty.
- **Relative Volume baseline (days)** — sets the denominator (N-day
  average volume) for the "Relative Volume %" column above — doesn't
  filter anything itself, just changes what that column measures
  against. The numerator stays fixed at a {MOMENTUM_VOLUME_RECENT_DAYS}-day average.

---

## Drill-down

- Click any row to expand a candlestick + volume chart for that stock,
  for visual context only — it isn't part of the ranking or filtering
  logic. (Sector View has no drill-down — there's no single time series
  to chart for a sector.)

---

## Sector View

- A second tab: same fetched data, aggregated to one row per sector
  instead of one row per stock — "which sectors are leading or lagging,
  and is that broad-based or a few names carrying it."
- **All sector figures are EQUAL-WEIGHTED** — a plain average across the
  sector's stocks, the same as holding an equal ₹ amount in every stock
  in that sector. **Not weighted by market cap.** A cap-weighted version
  (closer to how a real sector index behaves) would need a separate
  market-cap fetch and is deliberately not built — see "What this tool
  does NOT do" below.
- Computed over the FULL fetched universe, before this tab's own
  filters are applied — same principle as the stock-level sector
  columns above, so a sector's numbers reflect the sector as a whole.
- **Avg / Med 12mo returns %** — mean and median 12mo return across the
  sector's stocks. They answer different questions: the average is
  what an equal-weighted basket of the sector would have returned; the
  median is what the *typical* stock did, less swayed by a few extreme
  performers. Only %-based versions are shown — averaging raw ₹ returns
  across stocks trading at very different price levels isn't a fair
  comparison, so that version was deliberately left out.
- **Vs universe 12mo returns (pts)** — this sector's average 12mo
  return minus the average across the whole fetched universe (every
  sector combined), in percentage points.
- **Stocks up (12mo)** and **Stocks > N-day DMA** — breadth: how many
  of the sector's stocks are actually participating, not just the
  average. A sector can show a strong average return carried by a
  handful of big movers while most of its stocks lag — these two
  columns are how you'd catch that. Both shown as "count (%)", and the
  % is of stocks with a computable value for that metric, not the
  sector's total stock count.
- **Avg Sharpe ratio, Avg Annual traded turnover, Avg Relative Volume %**
  — the equal-weighted mean of the same per-stock columns from the
  Screener tab, one level up.
- Custom universes with only a few hand-picked tickers will show most
  sectors with just 1-2 stocks — check "# of stocks" before reading
  much into a thin sector's numbers.

---

## What this tool does NOT do (v1)

- No composite/weighted score — you sort by whichever column matters to
  you, there's no single blended "momentum score." Sector-relative
  momentum (Vs sector 12mo returns) is shown as its own column rather
  than folded into a single score, same reasoning.
- No cap-weighted sector averages — Sector View is equal-weighted only
  (see above). Cap-weighting would need a separate market-cap fetch
  (yfinance's `.info`/`fast_info`, not part of the OHLCV history
  already being pulled) — feasible, but a meaningfully slower and less
  reliable call at full-universe scale, so deferred rather than bundled
  in silently.
- No cross-sectional dispersion measure (how spread out returns are
  *across* a sector's stocks at a point in time, as opposed to one
  stock's own volatility over time) — considered, deferred.
- No drill-down from a sector row into its constituent stocks yet.
- No ASM/GSM/surveillance-list exclusion yet — a stock under exchange
  surveillance can still appear here. Cross-check manually for now:
    - ASM list: [nseindia.com/reports/asm](https://www.nseindia.com/reports/asm) (Download CSV button)
    - GSM list: [nseindia.com/reports/gsm](https://www.nseindia.com/reports/gsm) (Download CSV button)
    - Daily consolidated surveillance file (all flags, not just ASM/GSM): [nseindia.com/all-reports](https://www.nseindia.com/all-reports)
- No portfolio construction, position sizing, or trade execution — this
  is a ranking table, not a strategy.
""")
