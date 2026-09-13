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
  / 90 / 180 / 252 trading days. Shown side by side so you can see
  whether a move is accelerating or fading.
- **Volatility %** — the standard deviation of **day-to-day % price
  changes** over the trailing {MOMENTUM_LOOKBACK_MONTHS}-month window (not annualized — the
  raw daily std dev over that window, not scaled by √252 the way
  "annualized volatility" usually is). Shown on its own so you can judge
  "how choppy" in its own right and set the Max volatility % filter with
  a real number in mind. Ret/vol below uses an annualized version of
  this same figure, not this raw number, so the two won't look like a
  simple ratio of each other at a glance.
- **Return/volatility ratio (Ret/vol)** — 12-month return % ÷
  *annualized* volatility (Volatility % scaled up to a yearly figure).
  Annualizing the denominator puts this on the same scale as a standard
  Sharpe-style ratio, so familiar rules of thumb apply directly: below
  ~0.5 is weak, ~1.0 is decent, ~1.5-2.0 is good, above ~2.0 is strong.
  Treat these as a rough compass, not a hard cutoff — comparing stocks
  within this table against each other is more reliable than comparing
  any single stock against these bands in isolation. It answers "how
  bumpy was the ride to get this return" — a stock that moved steadily
  up every day scores higher than one that reached the same return
  through sharp swings up and down.
- **Hit rate** — % of trading days in the 12-month window that closed
  higher than the day before. A simple, intuitive read on consistency.
- **Volume participation** — the last {MOMENTUM_VOLUME_RECENT_DAYS}-day average volume as a % of
  the {MOMENTUM_VOLUME_BASELINE_DAYS_DEFAULT}-day average (both configurable — the column header updates
  to show whichever baseline you've picked). Above 100% means
  recent trading activity is running above the stock's own norm; below
  100% means it's quieter than usual. Shown for context — it does not
  filter the table.
- **Avg daily turnover ₹cr ({MOMENTUM_LIQUIDITY_LOOKBACK_DAYS}d)** — average of (Close price × Volume)
  over the trailing {MOMENTUM_LIQUIDITY_LOOKBACK_DAYS} trading days, in ₹ crore — this is the
  actual rupee value traded per day on average, not just share count,
  so it captures both price and volume together. Same figure the Min
  avg daily turnover filter checks against.
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
- **Trend** — price must be above its N-day moving average (you pick the
  period: 30/60/90/180/252, default {MOMENTUM_DMA_DEFAULT}-day). This is a single
  condition — no slope check, unlike the Signal Screener's Primary Trend.
  The actual price and DMA value used are visible as columns in the table.
- **Sector** — NSE's sector classification, from the dropdown.
- **Listing period** — minimum months since the stock listed (default {MOMENTUM_MIN_LISTING_MONTHS_DEFAULT}
  months) — filters out very recently listed names prone to IPO-pop
  volatility. The actual listing date is shown in the table, sourced
  from NSE data manually fetched on {MOMENTUM_MASTER_DATA_ASOF} (not live).
- **Min avg daily turnover ₹cr ({MOMENTUM_LIQUIDITY_LOOKBACK_DAYS}d)** — an eligibility gate: a stock
  below this simply doesn't appear, regardless of how strong its
  momentum looks — the concern is whether you could actually trade it
  at size, not whether the number is impressive. Same wording as the
  matching table column, just with a "Min" threshold applied.
- **Min price ₹** — excludes anything below the price you set. Default 0
  = disabled, every stock shown regardless of price.
- **Max volatility % (12mo)** — caps how choppy a stock's daily returns
  can be over the trailing 12 months, using the same Volatility %
  definition as the column above. Default 0 = disabled, no cap. Set this
  using the actual Volatility % values you see in the table as a guide.
- **Volume baseline (N, days)** — sets N in the "{MOMENTUM_VOLUME_RECENT_DAYS}-day volume as % of
  N-day volume" column above — doesn't filter anything itself, just
  changes what that column measures against.

---

## Drill-down

- Click any row to expand a candlestick + volume chart for that stock,
  for visual context only — it isn't part of the ranking or filtering
  logic.

---

## What this tool does NOT do (v1)

- No composite/weighted score — you sort by whichever column matters to
  you, there's no single blended "momentum score." Sector-relative
  momentum (Vs sector 12mo returns) is shown as its own column rather
  than folded into a single score, same reasoning.
- No ASM/GSM/surveillance-list exclusion yet — a stock under exchange
  surveillance can still appear here. Cross-check manually for now:
    - ASM list: [nseindia.com/reports/asm](https://www.nseindia.com/reports/asm) (Download CSV button)
    - GSM list: [nseindia.com/reports/gsm](https://www.nseindia.com/reports/gsm) (Download CSV button)
    - Daily consolidated surveillance file (all flags, not just ASM/GSM): [nseindia.com/all-reports](https://www.nseindia.com/all-reports)
- No portfolio construction, position sizing, or trade execution — this
  is a ranking table, not a strategy.
""")
