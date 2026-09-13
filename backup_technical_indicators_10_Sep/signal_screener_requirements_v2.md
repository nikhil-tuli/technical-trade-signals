# Trade Signal Screener — Requirements Document

**Status:** All open items resolved, including tech stack and signal-persistence approach. Ready for development.
**Last updated:** 25 Aug 2026 (tech stack + live-compute persistence + fixed Universe added)

**Purpose:** Give a trader a single-place directional view per stock, based on a defined, rules-based confirmation logic. The tool surfaces qualifying setups and shows supporting context — it does **not** auto-decide trade entry or position size. Final judgment rests with the trader's own wisdom and experience.

**How to read this document:** Section 2 defines what makes a signal appear at all (hard gates). Section 3 defines what's shown alongside a signal for context (never gates). Section 4 is the full parameter reference, split by Trade Type. Later sections cover the table, persistence, filters, and technical/infra notes. Section 9 is the authoritative phase list — if something isn't in v1, it's explicitly named in v2 rather than silently missing.

---

## 1. Universe & Scope

- **Universe: fixed to a hardcoded Nifty 100 symbol → company-name map** (provided list, ~100 tickers). No Nifty 500 option, no custom/user-defined list — this was considered (see prior drafts) and explicitly dropped. The Universe input is a single fixed value, not a multi-option dropdown, unless a future version adds more universes.
- Data granularity: Daily candles
- Data source: yfinance (consistent with existing backtester)
- **Trade Type is the primary mode switch for the whole screener** — see Section 4. Default on load: **Short-term**.

---

## 2. Signal Qualification Logic (Hard Gates — a row only appears if ALL of these pass)

This is a strict AND chain. Points 1–4 below correspond to the original logic's points 1–4. There is deliberately **no partial-match / soft-scoring version of these four** — a setup either clears all four or it does not appear.

### Gate 1 — Candlestick Pattern Strength

Each pattern has its own defined rule, including a required prior-trend precondition. A pattern only qualifies if that precondition is also met (e.g., a Hammer only counts if it forms after a downtrend).

| Pattern | Direction | Required prior trend | Core shape rule |
|---|---|---|---|
| Marubozu (Bullish/Bearish) | Either | None | Shadow ≤ shadow tolerance % of candle range |
| Hammer | Bullish | Downtrend | Small body near candle top; lower shadow ≥ 2x body; minimal upper shadow |
| Shooting Star | Bearish | Uptrend | Small body near candle bottom; upper shadow ≥ 2x body; minimal lower shadow |
| Bullish Engulfing | Bullish | Downtrend | Current green body fully engulfs prior red body |
| Bearish Engulfing | Bearish | Uptrend | Current red body fully engulfs prior green body |
| Morning Star | Bullish | Downtrend | 3-candle: long red → small-body gap-down → long green closing into candle-1 body |
| Evening Star | Bearish | Uptrend | 3-candle: long green → small-body gap-up → long red closing into candle-1 body |

- "Prior trend" here is a **short, pattern-qualification-only lookback** (see Section 4 for the exact candle count — this is distinct from Primary Trend in Gate/Section 3.1, which uses a moving average).
- **All pattern-specific thresholds (shadow tolerance %, engulfing overlap rule, star-pattern body/gap rules, etc.) are fixed system parameters, shown to the trader via the candlestick pattern definitions info button (Section 7) — none of these are exposed as user-editable filters.** This includes shadow tolerance, which was considered as a standalone filter and deliberately removed for that reason (see Section 7).
- **Multiple patterns on the same candle:** if a candle legitimately qualifies for more than one pattern (typically a multi-candle pattern like Morning Star overlapping with a 2-candle Bullish Engulfing resolving on the same day), **both are shown as separate rows.** No priority/precedence logic — trader decides which is more relevant. True shape-contradictory double-matches (e.g., a candle qualifying as both a bullish and bearish pattern) should not occur if pattern rules are correctly implemented; if seen, treat as a logic bug, not an expected case.

### Gate 2 — Volume Confirmation

- Volume on signal day ≥ X-day moving average of volume.
- X = **10 days** (fixed default; user-configurable in UI, see Section 6).

### Gate 3 — Support & Resistance Alignment

- Full method defined in Section 4.
- A qualifying S/R zone (3+ touch, correctly spaced — see Section 4) must exist near the trade's stop-loss, within the configured max % distance.
- **If no qualifying S/R zone exists at all for a stock, it is excluded entirely** — no row shown. This is a hard exclusion, not a soft warning, and applies regardless of how well Gates 1–2 were satisfied.

### Gate 4 — Reward-to-Risk Ratio

- Calculated only if Gates 1–3 pass.
- **Entry price:** previous session's closing price (the price at which the pattern was confirmed). This is a **reference price, not a tradeable fill** — see Section 6.4 for exact UI label wording.
- **Stop-loss:** nearest qualifying S/R zone in the direction of risk (method in Section 4).
- **Target:** nearest qualifying S/R zone in the trade direction beyond entry (same method, same section).
- **R:R = (Target − Entry) / (Entry − Stop-loss)**, sign-adjusted for direction.
- Minimum R:R = **2.0** (fixed default; user-configurable). Setups below threshold are excluded.

---

## 3. Contextual Layers (Shown for every signal — never gate whether a row appears)

These correspond to the original logic's points 5–6. They inform the trader's judgment; they do not filter the table.

### 3.1 Primary Trend

- **Basis:** Moving average, period depends on Trade Type (see Section 4) — **20 MA for Short-term, 50 MA for Long-term**.
- **Up:** Close > MA, and MA slope is rising over a lookback window (MA today > MA ~10–15 days ago).
- **Down:** Close < MA, and MA slope is falling over the same lookback.
- **Sideways:** Price-vs-MA relationship has flipped (crossed) **more than once in the last 10 candles**.
- Displayed as a single label (Up / Down / Sideways); underlying MA value, slope, and flip count available in Details.
- **Out of scope for v1:** higher-high/higher-low/lower-high/lower-low structural confirmation as a secondary check. See Section 9 (v2).

### 3.2 Structural Note (chart patterns — double top/bottom, flags, range breakout)

- **Out of scope for v1 entirely.** Acknowledged as the least algorithmically rigorous part of the original logic (no standard, universally agreed definition the way candlestick patterns or MAs have). See Section 9 (v2).

### 3.3 Indicator Confluence

- Indicators: MACD, RSI, Supertrend, Aroon.
- Standard/default parameter settings for each, **same regardless of Trade Type** in v1 (e.g., RSI-14). Trade-Type-scaled indicator periods are a v2 item (Section 9).
- Each evaluated independently for directional agreement with the signal (confirming / not confirming).
- Displayed as a count at row level (e.g., "3/4 confirming"), individual readings available in Details.
- **Important caveat to preserve in UI copy:** these four indicators are all price-derived and therefore correlated — "N/4 confirming" is not N independent opinions. Avoid UI language that overstates this as strong independent validation.
- No auto position-sizing. Any "consider larger size" language is advisory text only, never a computed value.

---

## 4. Trade Type — Parameter Reference (the single mode switch)

**Trade Type is a top-level dropdown (Short-term / Long-term) that silently sets every parameter below.** The user does not tune these individually — selecting Trade Type cascades into all of them. This keeps the screener internally consistent and avoids the user having to understand/set 6+ interdependent parameters by hand.

| Parameter | Short-term | Long-term | Notes |
|---|---|---|---|
| S/R lookback window | 3–6 months | 12–18 months | Longer window naturally squeezes/reveals broader clusters |
| Fractal width (swing detection) | 5 candles either side | 10 candles either side | Standard convention scales with lookback; matches typical swing-trading practice |
| Min. time separation between counted S/R touches | 7 trading days | 15 trading days | Touches within this gap collapse into one touch. Note: proportionally stricter on short-term due to smaller window — see flag below |
| S/R zone tolerance/buffer | 0.75% of price | 0.75% of price | Same for both — kept constant rather than adding a second scaling parameter |
| Primary Trend MA | 20 MA | 50 MA | Section 3.1 |
| Candlestick "prior trend" lookback (Gate 1) | 7 candles | 15 candles | Kept consistent with the scaling pattern of other parameters |
| Confluence indicator periods (Section 3.3) | Same for both in v1 | Same for both in v1 | v2 item — see Section 9 |

**Known flag to monitor once live:** the 7-day minimum touch-separation on Short-term consumes a proportionally larger share of its (shorter) lookback window than 15 days does on Long-term. This may mean fewer Short-term stocks form a valid 3-touch zone than expected. If very few Short-term signals appear in practice, this is the first parameter to revisit (e.g., loosen to 5 days) — not the fractal width or buffer %.

### 4.1 Support & Resistance — Full Method (Varsity-aligned)

This is the sole S/R method for v1 — replaces earlier candidate methods (pivot points, DMA-as-level, round numbers, gap zones), which are not used standalone. Chosen for being self-contained, trader-recognized, and not needing other methods as scaffolding.

**Step 1 — Lookback window:** set by Trade Type (table above).

**Step 2 — Candidate zone detection:** identify local swing highs/lows (price action "ceilings," "floors," and sharp V-reversals) using fractal detection at the Trade-Type-specific width.

**Step 3 — Validation & spacing:**
- **3-touch rule:** cluster candidate swing points whose prices fall within the zone tolerance band (0.75%) of each other. A cluster only becomes a valid zone with **3 or more qualifying touches.**
- **Time separation:** touches must be spaced apart by at least the Trade-Type minimum (7 or 15 trading days). Touches closer together than this collapse into a single counted touch.

**Step 4 — Zone construction & classification:**
- Zone = price band spanning the clustered touches ± tolerance buffer (e.g., a cluster around ₹429 with 0.75% buffer ≈ ₹426–₹432).
- **Classification is dynamic, computed fresh every screening run** — not stored as a fixed label:
  - Current Market Price (CMP) above the zone → zone acts as **Support**.
  - CMP below the zone → zone acts as **Resistance**.
- **Stop-loss** = nearest qualifying zone in the direction of risk from entry.
- **Target** = nearest qualifying zone in the trade direction beyond entry (same "nearest," not "next major" — keeps R:R conservative and consistent rather than cherry-picked toward a distant, optimistic level).
- **If zero qualifying zones exist for a stock within the lookback window** → stock excluded entirely (Gate 3, Section 2).

---

## 5. Signal Persistence — Computed Live, Not Stored

**Decision: signal state (Active / Stopped out / Target hit) is computed fresh on every run, not persisted in a database.** A signal's existence and status are fully determined by historical OHLCV data — the candle where a pattern formed, the S/R zones derivable from price history at that point — so there is nothing that genuinely needs to be "remembered" across runs. Recomputing avoids state-drift risk (a stored signal referencing an old version of the S/R or pattern logic if that logic is ever changed/fixed later) and keeps the architecture simpler — no signals database, no write/reconciliation logic, consistent results for any user at any time since everything derives from the same current logic.

- **Active:** pattern formed within the lookback window (see below), and price hasn't yet closed beyond its stop-loss or target.
- **Stopped out / Target hit:** not shown — once resolved, a signal simply stops appearing in the next run's scan. No stored record, no history log (v2 item, see Section 9, if a log becomes wanted later).
- **Live-computation lookback: 30 trading days.** Each run scans the last 30 trading days for pattern formations and checks each one's current status against latest price.
- **Known trade-off, explicitly flagged:** a signal that formed more than 30 trading days ago and still hasn't hit stop or target will silently stop appearing, purely because it falls outside the scan window — not because anything invalidated it. This is functionally a soft, undocumented version of the "Expired" status concept that was deliberately dropped elsewhere in this document (Section 9, v2) — the difference is it's an implementation/performance boundary on the live-scan, not a labeled trader-facing status. Worth remembering this distinction if revisiting later, so it isn't mistaken for a design inconsistency.
- **No custom stock lists to persist** (Universe is fixed — Section 1), so no other persistence need currently exists. If any future feature needs storage, evaluate it on its own merits rather than reusing this decision as precedent.

---

## 6. Output Table

### 6.1 Columns

**Note:** there are 6 data columns, not 7 — Symbol and Pattern are combined into a single first column (ticker/name on one line, pattern name + date on the next), not two separate headers. An earlier mockup draft had a header/data misalignment from listing these as separate columns; corrected here.

| # | Column header | Content |
|---|---|---|
| 1 | Symbol | Ticker + company name, with pattern name + formation date shown beneath it in the same cell (this combined field is the default sort key, sorted by formation date) |
| 2 | Direction | Bullish / Bearish pill (derived from pattern — no separate direction filter needed) |
| 3 | Trade Levels | Grouped: Entry · Stop-loss · Target · R:R ratio, shown compactly in one column (e.g., "Entry ₹1130 · SL ₹1108 · Target ₹1186 (2.8x)") — avoids adding 3–4 separate columns while still surfacing actionable numbers directly, not just behind Details |
| 4 | Primary Trend | Up / Down / Sideways |
| 5 | Confluence | "N/4 confirming" + mini bar |
| 6 | *(blank header)* | Details expand/hover trigger — no column label needed |

### 6.2 Sorting

- **Default sort:** most recent pattern-formation date first.
- **All columns sortable** via standard header click — no separate sort control needed.

### 6.3 Details (on hover/expand)

Shows the evidence behind the row's verdict — this is where analytical depth lives, kept out of the main row to avoid clutter:
- Candle OHLC + shadow/body ratios that qualified the pattern, **and the prior-trend condition considered when qualifying it** (e.g., "downtrend confirmed over prior 7 candles" for a Hammer)
- Volume vs. its MA (actual ratio, not just pass/fail)
- Primary Trend detail: current MA value, slope direction, and (if Sideways) the flip count over the last 10 candles
- S/R zone used for stop-loss and target: the touch points, zone band, and method
- R:R breakdown: entry (ref.) / stop-loss / target values (same numbers as the Trade Levels column, shown with full precision/context here)
- Individual indicator readings: RSI value, MACD state, Supertrend direction, Aroon value

### 6.4 Entry price label (info section, static text)

> **Entry price shown is the previous session's closing price** — the price at which the pattern was confirmed, not a price you can still transact at. By the time you view this signal, the stock has already opened for a new session, so treat the entry as a reference point for your own analysis, not a fill price.

### 6.5 Exclusion visibility

- **Summary line above the results table**, e.g.: *"100 screened → 6 signals · 94 excluded (see breakdown)"*
- **A stock can fail more than one gate** (e.g., no candlestick pattern AND volume below MA on the same stock) — so per-reason counts are **not mutually exclusive** and will **not sum to the excluded total**. UI copy near the breakdown should say this explicitly (e.g., a small note: "a stock may appear in more than one category") so the numbers aren't misread as a clean partition.
- **Clicking "See breakdown" opens a per-stock table**, not just aggregate counts — this is the actual breakdown content: each excluded stock listed once, with **all** gates it failed shown as tags on that row (e.g., `INFY — No candlestick pattern, Volume below MA`). The top-level counts (e.g., "No candlestick pattern: 41") are a rollup of how many rows in this per-stock table carry that tag — useful for a quick scan, but the per-stock table is the source of truth once expanded.
- **Search box** (already planned in filters) surfaces a specific stock's exclusion reason(s) on demand as well — same underlying per-stock data as the breakdown table, just filtered to one symbol.

---

## 7. Filters / Input Panel

| Filter | Values | Default |
|---|---|---|
| Trade Type | Short-term / Long-term | **Short-term** |
| Universe | Fixed — hardcoded Nifty 100 list (not user-selectable) | Nifty 100 |
| Volume MA period | Numeric (days) | 10 |
| Min Reward:Risk | Numeric | 2.0 |
| Pattern types | All patterns / Bullish only / Bearish only | All patterns |
| Search Symbol/Company | Text (also surfaces exclusion reason if not a signal) | — |

**Removed / not included:**
- **"Signal direction" as a separate filter** — redundant with Pattern Types and the Direction column; dropped to avoid confusing users with two controls describing the same thing.
- **Reversal / Continuation grouping** in Pattern Types — dropped as unnecessary complexity for v1.
- **S/R proximity %, fractal width, touch-spacing, MA period as individually user-editable fields** — these are now all driven by the Trade Type selector (Section 4), not exposed as separate raw inputs, to keep the parameter set internally consistent and avoid the user having to understand 6+ interdependent numbers.
- **Marubozu shadow tolerance as a standalone filter** — removed. All candlestick-pattern-specific thresholds (shadow tolerance included) are fixed system parameters, documented for the trader via the pattern definitions info button, not tunable inputs. Exposing this one pattern's threshold while every other pattern's rules stayed fixed was inconsistent — either all pattern thresholds are editable or none are, and none are, for v1.

**Info buttons (static reference content, not per-row):**
- Candlestick pattern definitions (table from Section 2, Gate 1)
- R:R / Trade Levels calculation methodology (Section 2, Gate 4 + Section 4.1)
- Entry price caveat (Section 6.4)

---

## 8. Technical / Infrastructure Notes

### 8.0 Tech stack

- **UI + app shell:** Streamlit (hosted on Streamlit Community Cloud).
- **Business logic:** plain Python modules — no separate backend service/API. Streamlit's Python process calls these modules directly; a standalone Flask/FastAPI backend was considered and dropped since nothing else needs to consume this logic independently.
- **Computation:** `pandas`/`numpy`, reusing/adapting existing candlestick, Supertrend, Aroon, and S/R (fractal) code already built for the NSE backtester rather than rewriting from scratch.
- **Data fetch:** `yfinance`, throttled sequential (Section 8.3).
- **Caching:** Streamlit's built-in `st.cache_data(ttl=...)` — process-level, shared across users, no external cache/DB service needed (Section 8.2).
- **No database.** Signal state is computed live (Section 5); Universe is a fixed hardcoded list (Section 1) with nothing to persist. Revisit only if a future feature genuinely needs storage.
- **Suggested module layout** (for planning, not final): `app.py` (UI), `config.py` (Nifty 100 map + Trade Type parameter presets), `data_fetch.py`, `patterns.py`, `support_resistance.py`, `indicators.py`, `signal_engine.py` (orchestrates the 4 gates + exclusion reasons).

### 8.1 Refresh model — not true real-time

- **Trigger-on-click ("Generate Signals" button), not continuous polling or refresh-on-every-parameter-change.** Changing a filter/parameter only updates pending UI state; no data fetch until the button is clicked.
- **Rationale:** yfinance is an unofficial, scraped data source with no published rate limit, but known to throttle/block aggressive request bursts from a single source. Screening ~100 stocks already means ~100+ requests per run — real-time/continuous refresh would multiply this risk without materially benefiting single-digit concurrent users.

### 8.2 Caching

- **Shared, server-side cache** (not per-user session) — since all users are likely screening the same universe, one fetch cycle serves everyone rather than duplicating fetches per session.
- **TTL:** 15–60 minutes. Daily-candle OHLCV data doesn't change intraday until the candle closes, so caching during market hours costs no meaningful accuracy.
- Signal *computation* (pattern/gate logic) can re-run cheaply against cached data on every "Generate Signals" click — only the raw data *fetch* is the expensive/rate-limit-sensitive part.

### 8.3 Fetch approach — decision: throttled sequential, not multi-ticker batch

Two options were weighed:

- **`yf.download()` with a full ticker list** — looks like a single "batch" call, but internally yfinance still fires one HTTP request per ticker; by default it does this **concurrently via threading** (`threads=True`). Concurrent requests from one source is exactly the pattern most likely to trigger Yahoo's throttling — it doesn't reduce request volume, it just fires the same ~100 requests faster and in parallel, which is *higher* rate-limit risk, not lower.
- **Individual/looped calls with `threads=False` and a small delay between each** — same total request count, but sequential and paced, which is the safer, more controllable pattern against an unofficial, unpublished-limit data source.

**Decision: throttled sequential fetch** (loop with `threads=False` + a small delay, e.g. 200–300ms, between requests) — this was already the leaning going in, and is confirmed as the right call: multi-ticker "batch" download doesn't actually reduce request count against yfinance, it only parallelizes it, which trades a lower rate-limit risk for a faster-but-riskier one. Given single-digit traffic, the extra time from sequential fetching is a non-issue (see 8.4 below on expected latency) — safety against getting blocked matters more here than shaving off fetch time.

### 8.4 Expected latency & progress indication

- **Rough estimate, cache-miss scenario (first run, or after TTL expiry):** ~100 symbols × (throttle delay + network round-trip, roughly 0.5–1 second combined per symbol) ≈ **roughly 1–2 minutes** for a full universe fetch. This is the only scenario where latency is meaningful — a cache-hit run (same TTL window, any user) should return in a second or two since it's just re-running signal logic on already-cached data.
- **The UI should not sit blank/frozen during a cache-miss fetch.** Recommended: a progress indicator showing live count (e.g., "Fetching 42/100…") with the results table area greyed out / showing a loading state until the fetch-and-compute cycle completes, rather than the button appearing to hang with no feedback.
- Once cached, subsequent "Generate Signals" clicks within the TTL window (parameter changes, different users) should feel near-instant — worth making this visible too, e.g. the "Data last refreshed" timestamp (8.5 below) not changing on a cache-hit run reassures the trader the tool is working correctly rather than silently failing to fetch.

### 8.5 Transparency

- Visible **"Data last refreshed: [timestamp]"** indicator in the UI — sets correct expectations that this is cache-refresh-cycle data, not tick-by-tick real-time.

---

## 9. Phasing

### v1 (this document's primary scope)

- Gates 1–4 (candlestick, volume, S/R, R:R) as hard filters, Trade-Type-parameterized
- Primary Trend (MA-based) and Indicator Confluence as contextual, non-gating display
- Varsity-aligned S/R method (Section 4.1) as the sole S/R source
- Trade Type as single mode switch (Short-term default)
- Universe fixed to hardcoded Nifty 100 list — no Nifty 500, no custom list
- Signal state computed live (30-day scan lookback), no database, no history log
- Output table with grouped Trade Levels column, sortable, Details expand
- Exclusion breakdown as a per-stock table (not just aggregate counts)
- Trigger-on-click refresh, shared cache, throttled sequential fetch, fetch-progress indicator
- Tech stack: Streamlit + plain Python modules, no separate backend, no DB (Section 8.0)

### v2 (explicitly deferred — not silently missing, revisit after v1 ships and is validated)

- **Structural pattern detection:** double/triple top-bottom, flags, range breakouts (Section 3.2)
- **Higher-high/higher-low trend confirmation** as a secondary check alongside the MA-based Primary Trend (Section 3.1)
- **Max holding window / "Expired" signal status**, and a resolved/closed signal history view (Section 5)
- **Trade-Type-scaled confluence indicator periods** (e.g., different RSI/MACD/Supertrend/Aroon settings for Short-term vs. Long-term) (Section 3.3)
- **Gap zones** as an additional S/R source
- **"Days active" column** for long-running signals, if table clutter becomes noticeable without an expiry mechanism
- Weekly timeframe option (currently daily-only)
- Pattern priority/precedence logic, if same-day multi-pattern rows turn out to be more frequent/confusing in practice than currently expected

---

## 10. Decisions Log (for future reference — why, not just what)

- **Nearest S/R zone (not highest-confluence-but-farther) chosen for stop/target** — prioritizes controlling actual trade risk over analytical elegance.
- **Entry = previous close, explicitly labeled non-tradeable** — avoids implying a fill price the trader can no longer act on, while keeping the calculation simple (no need to model next-day open behavior).
- **Trade Type as single cascading switch, not individually tunable parameters** — reduces cognitive load; avoids a trader having to understand 6+ interdependent numbers to use the tool sensibly.
- **Points 5–6 (trend, confluence) deliberately never gate the table** — this is a decision-support tool, not an auto-signal generator; final call stays with the trader's judgment, per the original design intent.
- **Chart/structural pattern detection deferred rather than shipped loosely-defined** — no standard, rigorous algorithmic definition exists for double-tops/flags the way it does for candlesticks or moving averages; shipping a shaky version was judged worse than deferring.
- **Signal state computed live rather than persisted in a database** — avoids state-drift risk (stored signals referencing outdated logic after a future fix/tweak) and keeps the architecture simpler; accepted trade-off is a bounded 30-day scan lookback, meaning very old unresolved signals silently age out of view (Section 5).
- **No separate backend service** — Streamlit's Python process calls business-logic modules directly; a standalone API was only worth it if something else needed to consume this logic independently, which isn't currently the case (Section 8.0).
- **Universe fixed to a single hardcoded Nifty 100 list, not user-selectable** — removes an entire category of open questions (custom-list input mechanism, validation, persistence, size limits) that would otherwise need solving for a feature not currently needed.
