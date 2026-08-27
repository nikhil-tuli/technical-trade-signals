# Signal Screener — Build Status

Companion to `signal_screener_requirements_v2.md`. Read that first for the
"why" behind every rule; this file tracks **build/test status only**.

## Files

| File | Status |
|---|---|
| `config.py` | Done — Nifty 100 map, Trade Type presets, all fixed parameters |
| `patterns.py` | Done — Gate 1 (7 candlestick patterns + prior-trend qualification) |
| `support_resistance.py` | Done — Varsity-aligned zone method (Section 4.1) |
| `indicators.py` | Done — RSI (Wilder), MACD, Supertrend, Aroon, Primary Trend |
| `data_fetch.py` | Done — throttled sequential yfinance fetch |
| `signal_engine.py` | Done — orchestrates Gates 1-4, 30-day live scan, exclusion reasons |
| `app.py` | Done — Streamlit UI shell, shared module-level TTL cache, progress bar |

## How this was tested so far

This sandbox's network allowlist does **not** include Yahoo Finance
(`finance.yahoo.com` / `query1/2.finance.yahoo.com`), so `data_fetch.py`
could not be tested against live data from here. **You ran it locally and
hit a real bug: `threads=False` was passed to `yf.Ticker.history()`, but
that parameter only exists on `yf.download()` — every fetch call raised
a TypeError, was silently caught, and the whole universe came back empty
("0 screened"). Fixed** — `threads` removed from the `.history()` call;
sequential throttling still comes from the plain for-loop + `time.sleep()`
in `fetch_universe()`, unchanged. Also hardened: fetch failures are no
longer swallowed silently — `fetch_history()`/`fetch_universe()` now
return the actual error per symbol, and `app.py` shows a failed-fetch
count + expandable error table, with a hard stop if everything fails
(so a "0 signals" result is never mistaken for "nothing qualified" when
it's actually "nothing was fetched").

Everything else (`patterns.py`, `support_resistance.py`, `indicators.py`,
`signal_engine.py`) was smoke-tested against synthetic OHLCV data engineered
in-sandbox (see chat transcript for the test scripts) — confirmed:
- Candlestick detection correctly matches/rejects based on shadow ratios and
  the prior-trend precondition (tested against a deliberately borderline
  case, which correctly resolved as "flat" rather than "down" at a -0.81%
  move against the 1% threshold — logic is working as specified, not buggy).
- Fractal swing detection + 3-touch clustering produces real zones from
  natural random-walk data.
- Primary Trend and Confluence checks compute without error.
- Full `screen_symbol()` pipeline runs end-to-end without crashing and
  produces sensible, traceable exclusion reasons.

**Not yet done: a full run against real Nifty 100 data.** First priority
next session — run `app.py` locally (`streamlit run app.py`) with real
network access to confirm the yfinance fetch, full-universe timing, and
real signal output look right.

## Known caveats / things to revisit

1. **`_prior_trend()` threshold (±1%) is a placeholder**, not something we
   explicitly agreed a number for in the requirements doc. Worth sanity
   checking against real data — may need loosening or tightening.
2. **Shared cache is a module-level Python dict**, not `st.cache_data` or an
   external store. This is correct per Section 8.2 (shared, not per-user)
   *for a single-process deployment*. If ever deployed with multiple worker
   processes (unlikely at this traffic level, but worth knowing), each
   process would keep its own cache and this stops being truly shared.
3. **`support_resistance.compute_sr_zones()` is called once per matched
   candle** inside the 30-day scan loop in `signal_engine.py` — functionally
   correct (avoids lookahead bias, since zones are computed only from data
   up to that candle) but potentially recomputes the same zones repeatedly
   across nearby candles. Fine at current universe size/traffic; worth
   profiling once real timing data exists (Section 8.4 estimated ~1-2 min
   for a full fetch — this adds to that, not yet measured).
4. **Gate 3 exclusion label doesn't currently distinguish** "zero S/R zones
   found at all" from "zones exist but not on the required side of price" —
   both report as "No valid S/R zone". Matches the requirements doc's
   exclusion category, but if finer-grained reasons become useful later,
   this is where to split it.
5. **`app.py`'s Details expander** shows raw values via `st.json` rather
   than the fully-styled Details panel from the mockup (candle shape,
   volume ratio, S/R touches, etc. — Section 6.3). Functionally complete,
   visually rough — worth revisiting once the core logic is confirmed
   against real data, so styling effort isn't spent before the numbers are
   validated.
6. **Not yet implemented:** none of the v2-deferred items (Section 9) —
   confirmed out of scope for this build pass, listed here only so it's
   not mistaken for an oversight.

## Logic rewrite — S/R now validates, doesn't set, the stop-loss

This was a genuine misalignment with the Varsity source material, caught in
review — not a bug in the original build, but the original design was wrong
relative to what was actually intended. Fixed across `patterns.py`,
`support_resistance.py`, `signal_engine.py`, `config.py`:

- **Stop-loss now comes from the candlestick pattern itself**
  (`patterns.compute_candle_stop_loss()`), not from the nearest S/R zone —
  e.g. below the low of a Bullish Marubozu, above the high of a Bearish
  Engulfing, lowest/highest point of the 3-candle patterns for Morning/
  Evening Star. A 0.3% buffer (`SL_BUFFER_PCT`) is applied beyond the raw
  candle price.
- **S/R only validates that stop-loss, it doesn't generate it.** The
  nearest qualifying zone on the risk side of entry (support for bullish,
  resistance for bearish — `support_resistance.nearest_zone()`) is checked
  for distance from the *candle-based SL*, not from entry price.
- **Distance check is candle-SL ↔ S/R zone**, not entry ↔ zone (this
  changed from the earlier build). Default cap still 4%
  (`SR_MAX_DISTANCE_PCT_DEFAULT`), user-editable in the UI.
- **No fallback to a farther zone if the nearest one fails the distance
  check** — reject the setup outright and move to the next candle/stock,
  matching Varsity's stated rule ("stop evaluating, move to next chart").
- **Target = the near edge of the nearest qualifying zone on the opposite
  side of entry** (`support_resistance.near_edge()`) — the first price
  level the trade would actually reach, not the zone's center or far edge.
- `support_resistance.classify_and_select()` was removed and replaced by
  two single-purpose functions (`nearest_zone()`, `near_edge()`), since the
  new logic needs independent lookups (risk side validated against
  candle-SL, reward side just needs nearest zone) rather than one combined
  "pick both sides" call.

## Custom ticker input (not persisted)

- New "Custom tickers (optional, comma-separated)" field in the input panel.
- If left blank, screens the fixed Nifty 100 list as before. If filled,
  **replaces** it for that run only (not saved across sessions or reruns —
  re-typed each time by design, per requirements discussion).
- Bare NSE symbols expected (e.g. `TCS, WIPRO`), auto-suffixed with `.NS`
  the same way the fixed list already is.
- Capped at 50 tickers (`MAX_CUSTOM_TICKERS` in `config.py`) — entering more
  shows an error and blocks the run until shortened.
- Invalid/unfetchable tickers surface through the **existing** fetch-failure
  mechanism (no separate validation step) — they show up in the "failed to
  fetch" expander with their actual error, same as any other fetch failure.
- Company name column just shows the ticker itself for custom entries (no
  name lookup — avoids an extra API call per ticker for a cosmetic detail).
- Custom-ticker runs **bypass the shared cache** entirely and always fetch
  fresh — the shared cache's whole point is one fetch serving everyone for
  the *same* fixed universe; a custom, per-request list doesn't fit that
  model and would risk one user's custom fetch being served (incorrectly)
  to another user requesting a different custom list under the same cache
  key. Treated as intentionally uncached rather than engineering around it.
- Custom tickers are tracked as a gating filter (like Trade Type, Volume MA,
  etc.) — changing the list requires clicking Generate Signals again, same
  as every other filter that affects what gets screened.

## UI cleanup pass (intuitiveness, not logic)

Pure front-end changes — no gate/pattern/S/R logic touched:

- **Sticky header** (title + tagline) via CSS `position: sticky` injected
  through `st.markdown(unsafe_allow_html=True)`. Best-effort: hardcodes a
  dark-theme background color and assumes current Streamlit DOM structure.
  **Revert this specific block if it breaks** on a Streamlit upgrade or in
  light theme — everything else in the app is independent of it.
- Tagline no longer says "Nifty 100" (misleading once custom tickers exist);
  now states the four checks in plain language.
- Removed the two info expanders (pattern definitions, R:R methodology) —
  content is being redesigned for a separate "How this works" page
  (planned, not yet built — see Section 9 v2 equivalent / next steps).
- 5 filters fit on one row now (shortened the S/R distance label).
- Trade Type explainer rewritten in plain language; the exact parameter
  numbers moved into a hover tooltip (`help=`) rather than the visible
  caption, so a first-time user isn't hit with 5 numbers up front.
- Data-refresh caption shortened and reworded (ordinal date, e.g. "26th Aug
  17:41 IST"), dropped the cache/TTL implementation detail from the
  visible text.
- Table legend line simplified; no longer enumerates "4 checks" explicitly.
- **"Confluence" column renamed to "TA Indicators"**, with a caption below
  the table explaining what it means (RSI/MACD/Supertrend/Aroon agreement
  count) and explicitly stating it's context, not a filter.
- **Details section rewritten from raw `st.json` to labeled sections** —
  metric cards for trade levels and indicator values, plain-language
  bullet points for pattern qualification and S/R validation, grouped
  under clear subheadings instead of a flat unlabeled JSON blob.

## Multi-page navigation — "How This Works"

- New `pages/1_How_This_Works.py` — Streamlit's native multi-page support:
  any `.py` file inside a `pages/` folder next to `app.py` automatically
  becomes a sidebar nav entry (the `1_` prefix controls its order; it
  doesn't show in the displayed title).
- **File placement matters**: `pages/` must sit in the same folder as
  `app.py` for Streamlit to detect it. If you keep `app.py` at
  `technical indicators/app.py`, this file must be at
  `technical indicators/pages/1_How_This_Works.py`.
- Content only, no logic — a plain-language explanation of the 4 hard
  filters, the 4 contextual indicators, and Primary Trend, written to
  match the actual current values in `config.py` (periods, defaults,
  Trade-Type-specific numbers). This is hand-maintained, not generated
  from the config — if a default or threshold changes in `config.py`,
  this page's text needs a matching manual update or it will drift out of
  sync and describe outdated behavior.
- Does **not** call `st.set_page_config()` — that can only be called once
  per app and `app.py` already does it; calling it again here would error.

## File structure change — fixed state not persisting across sidebar pages

**Problem:** after adding "How This Works" via `st.navigation`, filter
selections and screening results were being lost every time the user
switched to that page and back to "Signal Screener" — despite adding
explicit `key=` to every widget (which didn't fix it).

**Root cause (suspected and addressed):** the Signal Screener page was set
up as a **callable-based** page (`st.Page(main, ...)`, passing a Python
function), while "How This Works" was **file-based** (`st.Page("pages/1_...py")`,
passing a file path). Mixing these two page styles under `st.navigation`
is the likely cause — Streamlit can treat them asymmetrically for what
state survives a page switch.

**Fix:** the entire Signal Screener page was extracted out of `app.py`
into its own file, `pages/0_Signal_Screener.py`, so **both** pages are now
file-based, matching each other structurally:

- `app.py` is now a thin entry point only — `st.set_page_config()` and
  the `st.navigation([...])` setup, nothing else.
- `pages/0_Signal_Screener.py` contains all the actual screening logic
  (previously the `main()` function body in `app.py`) — internally still
  wrapped in a function (`_render_page()`) purely so its existing early
  `return` statements stay legal, then called unconditionally at the
  bottom of the file. This is NOT the same as the earlier callable-based
  setup: `st.Page` here still receives a file **path** string, not a
  function reference — the internal function wrapper is just an
  implementation detail invisible to `st.Page`.
- `pages/1_How_This_Works.py` is unchanged.

**File layout is now:**
```
technical indicators/
├── app.py                        (thin entry point)
├── config.py, patterns.py, support_resistance.py,
│   indicators.py, data_fetch.py, signal_engine.py  (unchanged)
└── pages/
    ├── 0_Signal_Screener.py      (NEW — main screener page content)
    └── 1_How_This_Works.py       (unchanged)
```

**Not yet confirmed fixed** — this is the most likely root cause based on
the callable-vs-file-based asymmetry, but hasn't been verified against a
real browser session with actual page-switching yet. If state still
doesn't persist after this change, the next thing to check is whether
`st.session_state` itself is being cleared by something else entirely
(e.g. a Streamlit version-specific quirk), which would need a different
fix — a plain session_state debug print (`st.write(st.session_state)`)
right at the top of `pages/0_Signal_Screener.py` would confirm whether
the dict itself survives the page switch or not.

## Details view — from generic to fully descriptive

Previously the Details panel showed generic labels ("Required prior trend:
down") without the actual computed numbers behind them. Rewrote across
4 files to surface real values:

- **`patterns.py`** — new `compute_candle_stop_loss_detailed()` returns
  both the raw (pre-buffer) candle price and the final buffered SL,
  instead of just the buffered value. `compute_candle_stop_loss()` kept
  as a thin wrapper for backward compat.
- **`indicators.py`** — `primary_trend()` now also returns `close_now`,
  `ma_then` (the MA value at the slope-comparison point), `ma_period`,
  `slope_lookback_days`, `sideways_flip_window` — everything needed to
  explain *why* the trend is Up/Down/Sideways with actual numbers, not
  just the final label.
- **`signal_engine.py`** — `Signal.details` now also captures: actual
  prior-trend date range (start/end dates + day count, only when the
  pattern has a prior-trend requirement — omitted entirely for patterns
  like Marubozu that don't need one), actual volume figures (not just
  the ratio), the raw pre-buffer SL price, and the full lower/upper band
  for both the stop-loss-validation zone and the target zone (not just
  their touch counts).
- **`pages/0_Signal_Screener.py`** — Details view rewritten to use all of
  this: "{Symbol} Trade Levels" header, a full R:R calculation shown with
  actual numbers plugged in, S/R validation described as "nearest
  [support/resistance] zone ₹X–₹Y band (N touches), Z% from the
  stop-loss", and Primary Trend explained with the actual price/MA
  values and, for Sideways, the actual flip count over the actual window.

## Details view — four further enhancements

Building on the earlier Details rewrite, added:

1. **Thresholds shown alongside results** — R:R now shows "(minimum
   required: Xx)" and the S/R distance line shows "(max allowed: Y%)",
   using the actual `min_rr`/`max_sr_distance_pct` values active for that
   run (`signal_engine.py` now stores these on `Signal.details` as
   `min_rr_threshold` / `max_sr_distance_threshold`).
2. **Volume MA period stated explicitly** — "10-day moving average" not
   just the resulting number (`volume_ma_period` added to details).
3. **Zone freshness** — each S/R zone (both the stop-loss-validation zone
   and the target zone) now shows its most recent touch date, e.g. "3
   touches, most recently on 12 Aug" (`SRZone.touch_dates` was already
   tracked internally; `max(touch_dates)` now surfaced as
   `sr_validation_last_touch` / `sr_target_last_touch`).
4. **Active-status one-liner** — a caption right under the trade-level
   metrics: "Signal formed on {date}, still Active — price hasn't closed
   beyond the stop-loss (₹X) or target (₹Y) since." Ties the Details view
   back to the live-persistence logic (Section 5) explicitly, since
   nothing before this stated that the row could disappear once resolved.

**Determinism confirmed** — grepped the full codebase for any use of
`random`/`uuid`/`shuffle`: none found in the actual app files (only in
throwaway test scripts used during development, never shipped). Given
the same market data and the same filter settings, output is identical
across every run and every user — the shared cache (`st.cache_resource`)
additionally guarantees all users see the same data within a cache
window. The only thing that legitimately changes output is genuinely new
market data on a new trading day, which is correct behavior, not
non-determinism.

## Fixed bugs (log, for context if similar issues resurface)

- **yfinance `threads` param crash** — `Ticker.history()` doesn't accept a
  `threads` kwarg (that's only valid on `yf.download()`); passing it caused
  every single fetch to fail silently, showing as "0 screened" with no
  visible error. Fixed by removing the param; sequential throttling still
  works via the plain for-loop + `time.sleep()` in `fetch_universe()`.
  Also hardened: fetch failures are no longer swallowed — errors are now
  returned per-symbol and shown in the UI, so a whole-universe failure is
  never mistaken for "nothing qualified."
- **Cache appeared to never hit / refetched every run** — the shared cache
  was a plain module-level dict in `app.py`. Streamlit reruns the *entire
  script* top-to-bottom on every widget interaction (not just button
  clicks), which resets plain top-level variables in the main script file
  every time — so the "cache" was silently empty on every rerun. Fixed by
  switching to `st.cache_resource`, which is the actual Streamlit primitive
  for an object that persists across reruns and is shared across all users.
- **Selecting a different stock in the Details dropdown reset the whole
  page back to "click Generate Signals"** — same root cause as above: any
  widget interaction reruns the script, and the code only checked "was the
  button just clicked" to decide whether to show results, so any other
  interaction (Details dropdown, search box) looked like "button not
  clicked" and bailed out. Fixed with `st.session_state["has_run"]` plus
  storing the inputs used for the last actual click in
  `st.session_state["screen_inputs"]` — results (and the ability to browse
  Details) now persist across any rerun; only clicking **Generate Signals**
  again triggers a fresh screen using the current widget values.

## Next steps (in order)

1. **Re-run `streamlit run app.py` with the fixed `data_fetch.py`** and confirm
   real fetches succeed and symbols populate (should no longer show "0 screened").
2. Once real signals appear, sanity-check them against a stock or two by eye.
3. Time a full-universe fetch to check the Section 8.4 latency estimate.
4. Polish the Details view to match the mockup's styled panel.
5. Only after 1-4: consider v2 items from the requirements doc.