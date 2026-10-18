# Technical Trade Signals

Three NSE stock screeners in one Streamlit app: candlestick signals, momentum ranking and breakout retests. All rules-based and transparent.

**App:** https://technical-trade-signals.streamlit.app/

> New here? Open the **How This Works** page in the app sidebar. It explains every rule, filter and formula in plain language.

## The 3 Apps

### 1. Signal Screener
Candlestick setups confirmed by volume, support/resistance and reward-to-risk.
- Shows a signal only when all 4 filters pass: pattern → volume → S/R zone → R:R ≥ 2
- 7 patterns: Marubozu, Hammer, Shooting Star, Bullish/Bearish Engulfing, Morning/Evening Star
- Inspired by Zerodha Varsity's technical analysis series
- Gives entry, stop-loss and target for each signal, plus trend and indicator context (RSI, MACD, Supertrend, Aroon)
- Short-term or Long-term mode

### 2. Momentum Screener
Ranks stocks by momentum. No pattern gating, no recommendations.
- Universe: Nifty 500, Nifty 100 or custom tickers
- Metrics: 12-month and 30/60/90/180-day returns, Sharpe, Ulcer Index, max drawdown, RSQ, hit rate, relative volume, turnover
- Compares each stock with its sector, plus a **Sector View** tab
- Filters: DMA trend, sector, listing age, turnover, price, Sharpe

### 3. Breakout Retest Screener
Finds high-volume breakouts that have pulled back to retest the breakout candle's midpoint.
- Breakout: green candle, volume spike, close above recent highs
- Retest: new high after breakout, and price back near the candle midpoint
- Setups expire after a fixed number of candles

For exact rules and parameters, see **How This Works** in the app.

## Tech Stack

- **UI:** Streamlit
- **Logic:** Python (pandas, numpy)
- **Data:** yfinance
- **Charts:** Plotly, Altair
- No database or separate backend

## Setup

```bash
git clone https://github.com/nikhil-tuli/technical-trade-signals.git
cd technical-trade-signals
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. No API keys needed.

## Usage

1. Pick an app from the sidebar.
2. Set filters (or enter custom tickers, e.g. `TCS, WIPRO`).
3. Run the screen and click a row for details.

| App | Example input | Example output |
| --- | --- | --- |
| Signal Screener | Short-term, Min R:R 2.0 | `Entry ₹1130 · SL ₹1108 · Target ₹1186 (2.8x)` (illustrative) |
| Momentum Screener | Nifty 500, 90-day DMA, Sector: Banks | Ranked table by 12-month return, with Sharpe and vs-sector gap |
| Breakout Retest | Nifty 100 | Stocks retesting a recent breakout candle's midpoint |

## Data and Sources

- **Prices:** Yahoo Finance via `yfinance`, daily candles, NSE symbols
- **Universe:** Nifty 100, Nifty 500 (Momentum and Breakout Retest) or custom tickers
- **Sector and listing dates:** from NSE data, refreshed manually (the as-of date is shown in the app)
- **Risk-free rate:** set manually (about the 91-day T-bill)
- **Refresh:** daily data is cached and refreshed after market close. Custom tickers are always fetched fresh
- **Limits:**
  - End-of-day only, not real-time
  - Yahoo is unofficial and may throttle or fail
  - Sector and listing filters are unavailable for custom tickers
  - Breakout Retest does not drop a setup if price closes below the breakout low. Check the chart before acting

## Disclaimer

For education and research only. Not investment advice. Do your own analysis before trading.

## More

- Signal Screener design rules: [`signal_screener_requirements_v2.md`](signal_screener_requirements_v2.md)
