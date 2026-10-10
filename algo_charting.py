"""
Altair chart for the Algo Signals drill-down: candlestick + volume panel,
with the breakout candle, midpoint +/- tolerance band, breakout high,
prior-20 high and post-breakout peak marked.

Uses a quantitative bar-index x-axis (no gaps for weekends/holidays) with a
labelExpr that maps index -> DD-MM-YYYY.
"""
from __future__ import annotations

import altair as alt
import pandas as pd

from config import (
    ALGO_CHART_WINDOW, ALGO_PRICE_LOOKBACK, ALGO_MIDPOINT_TOLERANCE_PCT, ALGO_VOLUME_LOOKBACK,
    ALGO_VOLUME_MULTIPLIER,
)

UP, DOWN, AMBER, GREY, BLUE = "#26a69a", "#ef5350", "#f5a623", "#8a8f98", "#4c78a8"


def build_algo_chart(result: dict, window: int = ALGO_CHART_WINDOW, height: int = 380) -> alt.VConcatChart:
    full: pd.DataFrame = result["candles"]
    start = max(0, len(full) - window)
    d = full.iloc[start:].copy()
    # volume baseline computed on the full series so the window start isn't NaN
    avg_vol = full["Volume"].rolling(ALGO_VOLUME_LOOKBACK).mean().shift(1).iloc[start:]
    d["i"] = range(start, len(full))
    d["date"] = [x.strftime("%d-%m-%Y") for x in d.index]
    d["up"] = d["Close"] >= d["Open"]
    d["avg_vol"] = avg_vol.to_numpy()
    d["body_lo"] = d[["Open", "Close"]].min(axis=1)
    d["body_hi"] = d[["Open", "Close"]].max(axis=1)
    d["is_breakout"] = d["i"] == result["b_index"]
    d["vcolor"] = [AMBER if b else (UP if u else DOWN) for b, u in zip(d["is_breakout"], d["up"])]
    d = d.reset_index(drop=True)

    x0, x1 = int(d["i"].iloc[0]) - 1, int(d["i"].iloc[-1]) + 1
    labels = list(d["date"])
    label_expr = f"datum.value >= {start} && datum.value - {start} < {len(labels)} ? {labels!r}[datum.value - {start}] : ''"
    xscale = alt.Scale(domain=[x0, x1], nice=False, zero=False)
    x = alt.X("i:Q", scale=xscale,
              axis=alt.Axis(title=None, labelExpr=label_expr, labelAngle=-45, tickMinStep=1,
                            grid=False, values=list(range(start, len(full), max(1, len(d) // 10)))))
    color = alt.condition("datum.up", alt.value(UP), alt.value(DOWN))
    tip = [alt.Tooltip("date:N", title="Date"), alt.Tooltip("Open:Q", format=".2f"),
           alt.Tooltip("High:Q", format=".2f"), alt.Tooltip("Low:Q", format=".2f"),
           alt.Tooltip("Close:Q", format=".2f"), alt.Tooltip("Volume:Q", format=",.0f")]

    mid, hi = result["midpoint"], result["breakout_high"]
    tol = ALGO_MIDPOINT_TOLERANCE_PCT / 100
    ymin = float(min(d["Low"].min(), mid * (1 - tol)))
    ymax = float(max(d["High"].max(), hi, result["max_price_after"]))
    pad = (ymax - ymin) * 0.06
    yscale = alt.Scale(domain=[ymin - pad, ymax + pad], nice=False, zero=False)
    y = alt.Y("Low:Q", scale=yscale, axis=alt.Axis(title="Price (₹)", grid=True, gridOpacity=0.15))

    base = alt.Chart(d)
    wick = base.mark_rule().encode(x=x, y=y, y2="High:Q", color=color, tooltip=tip)
    body = base.mark_bar(size=6).encode(x=x, y=alt.Y("body_lo:Q", scale=yscale), y2="body_hi:Q", color=color, tooltip=tip)
    hl = base.transform_filter("datum.is_breakout").mark_bar(
        size=14, opacity=0.25, color=AMBER).encode(x=x, y=alt.Y("Low:Q", scale=yscale), y2="High:Q")

    band = alt.Chart(pd.DataFrame({"x0": [int(d["i"][d["is_breakout"]].iloc[0])], "x1": [x1],
                                   "lo": [mid * (1 - tol)], "hi": [mid * (1 + tol)]})
                     ).mark_rect(color=AMBER, opacity=0.18).encode(
        x=alt.X("x0:Q", scale=xscale), x2="x1:Q", y=alt.Y("lo:Q", scale=yscale), y2="hi:Q")

    def hline(val, label, col, dash, xpos, align="left", dy=-6):
        df = pd.DataFrame({"v": [val], "label": [label], "x": [xpos]})
        r = alt.Chart(df).mark_rule(color=col, strokeDash=dash, strokeWidth=1.2).encode(y=alt.Y("v:Q", scale=yscale))
        t = alt.Chart(df).mark_text(align=align, dx=4 if align == "left" else -4, dy=dy, fontSize=11, color=col).encode(
            x=alt.X("x:Q", scale=xscale), y=alt.Y("v:Q", scale=yscale), text="label:N")
        return r + t

    b_i = int(result["b_index"])
    layers = [
        band, hl, wick, body,
        hline(mid, f"Midpoint {mid:,.2f}", AMBER, [], x0 + 1, dy=-6),
        hline(hi, f"Breakout high {hi:,.2f}", BLUE, [4, 3], x0 + 1),
        hline(result["prev_high"], f"Prev {ALGO_PRICE_LOOKBACK}-high {result['prev_high']:,.2f}", GREY, [2, 3], x0 + 1, dy=12),
        hline(result["max_price_after"], f"Peak after {result['max_price_after']:,.2f}", GREY, [6, 3], x0 + 1),
        hline(result["current_price"], f"Now {result['current_price']:,.2f}", "#e0e0e0", [], x1, align="right", dy=12),
    ]
    price = alt.layer(*layers).properties(height=height)

    vol_color = alt.Color("vcolor:N", scale=None)
    vbase = alt.Chart(d)
    vbars = vbase.mark_bar(size=6, opacity=0.8).encode(
        x=x, y=alt.Y("Volume:Q", axis=alt.Axis(title="Volume", format="~s", grid=False)),
        color=vol_color, tooltip=tip)
    avg = vbase.mark_line(color=GREY, strokeDash=[4, 3]).encode(x=x, y="avg_vol:Q")
    thr_df = d.assign(thr=d["avg_vol"] * ALGO_VOLUME_MULTIPLIER)
    thr = alt.Chart(thr_df).mark_line(color=AMBER, strokeDash=[2, 2], opacity=0.7).encode(x=x, y="thr:Q")
    vol = alt.layer(vbars, avg, thr).properties(height=110)

    return alt.vconcat(price, vol, spacing=4).resolve_scale(x="shared").configure_view(strokeWidth=0)
