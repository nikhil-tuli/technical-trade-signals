"""
'How This Works' — a separate sidebar page (Streamlit multi-page app).
Any .py file inside pages/ automatically becomes a sidebar nav entry
alongside the main app.py ("Signal Screener"). Purely explanatory content,
no logic — kept in sync by hand with the actual gate/config values in
config.py, patterns.py, support_resistance.py, indicators.py.

IMPORTANT: do not call st.set_page_config() here — it can only be called
once per app, and app.py already does it. Calling it again will error.
"""
import streamlit as st

st.title("How This Works")

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