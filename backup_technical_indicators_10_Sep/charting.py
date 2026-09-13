"""
Signal chart — candlestick + volume, with the 4 gates and Primary Trend
overlaid visually. Reuses data already fetched for screening (no new
network calls) — pure rendering, built fresh only for whichever table
row is currently selected in Details.
"""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

CHART_WINDOW_DAYS = 90  # trailing trading days from the most recent available candle (today)


def build_signal_chart(df: pd.DataFrame, sig) -> go.Figure:
    """
    df: the full OHLCV DataFrame already fetched for sig.symbol.
    sig: the Signal object (entry/stop_loss/target/direction/formation_date/
    pattern/primary_trend/details) — same object already used to render
    the text Details section, so the chart can never disagree with it.
    """
    d = sig.details
    is_bull = sig.direction == "bullish"

    ma_period = sig.primary_trend.get("ma_period") or 50
    vol_ma_period = d.get("volume_ma_period") or 10

    # Compute MAs on the FULL series first, then slice to the display
    # window — avoids NaN gaps at the start of the window that would
    # appear if the rolling average were computed only on the slice.
    ma_series = df["Close"].rolling(ma_period).mean()
    vol_ma_series = df["Volume"].rolling(vol_ma_period).mean()

    window = df.tail(CHART_WINDOW_DAYS).copy()
    window["MA"] = ma_series.reindex(window.index)
    window["VolMA"] = vol_ma_series.reindex(window.index)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.72, 0.28], vertical_spacing=0.03,
        specs=[[{"type": "candlestick"}], [{"type": "bar"}]],
    )

    # --- Gate 1: candlestick price action ---
    fig.add_trace(go.Candlestick(
        x=window.index, open=window["Open"], high=window["High"],
        low=window["Low"], close=window["Close"],
        name="Price", increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        showlegend=False,
    ), row=1, col=1)

    # --- Primary Trend overlay ---
    fig.add_trace(go.Scatter(
        x=window.index, y=window["MA"], mode="lines", name=f"{ma_period}-day MA",
        line=dict(color="#ffb020", width=1.6),
    ), row=1, col=1)

    # --- Gate 3: S/R zones. Validation zone is support for a bullish
    # trade (risk side below entry), resistance for bearish — mirrors
    # signal_engine's own risk_side logic exactly, so the chart never
    # contradicts what Details says.
    val_lower, val_upper = d.get("sr_validation_zone_lower"), d.get("sr_validation_zone_upper")
    tgt_lower, tgt_upper = d.get("sr_target_zone_lower"), d.get("sr_target_zone_upper")

    val_is_support = is_bull
    val_color = "#26a69a" if val_is_support else "#ef5350"
    val_label = "Support zone (SL validation)" if val_is_support else "Resistance zone (SL validation)"
    if val_lower is not None and val_upper is not None:
        fig.add_hrect(
            y0=val_lower, y1=val_upper, line_width=0, fillcolor=val_color, opacity=0.12, row=1, col=1,
            annotation_text=val_label,
            annotation_position="top left" if val_is_support else "bottom left",
            annotation_font_size=10, annotation_font_color=val_color,
        )

    tgt_is_support = not is_bull
    tgt_color = "#26a69a" if tgt_is_support else "#ef5350"
    tgt_label = "Support zone (Target)" if tgt_is_support else "Resistance zone (Target)"
    if tgt_lower is not None and tgt_upper is not None:
        fig.add_hrect(
            y0=tgt_lower, y1=tgt_upper, line_width=0, fillcolor=tgt_color, opacity=0.12, row=1, col=1,
            annotation_text=tgt_label,
            annotation_position="bottom left" if tgt_is_support else "top left",
            annotation_font_size=10, annotation_font_color=tgt_color,
        )

    # --- Gate 4 inputs: Entry / Stop-loss / Target lines ---
    fig.add_hline(
        y=sig.entry, line_dash="dot", line_color="#8a8f9c", line_width=1.4,
        annotation_text=f"Entry ₹{sig.entry}", annotation_position="right",
        annotation_font_size=11, row=1, col=1,
    )
    fig.add_hline(
        y=sig.stop_loss, line_dash="dash", line_color="#ef5350", line_width=1.6,
        annotation_text=f"Stop-loss ₹{sig.stop_loss}", annotation_position="right",
        annotation_font_size=11, annotation_font_color="#ef5350", row=1, col=1,
    )
    fig.add_hline(
        y=sig.target, line_dash="dash", line_color="#26a69a", line_width=1.6,
        annotation_text=f"Target ₹{sig.target}", annotation_position="right",
        annotation_font_size=11, annotation_font_color="#26a69a", row=1, col=1,
    )

    # --- Gate 1 marker: where the pattern actually formed ---
    if sig.formation_date in window.index:
        fig.add_annotation(
            x=sig.formation_date, y=window.loc[sig.formation_date, "High"] * 1.006,
            text=f"{sig.pattern}<br>(signal)", showarrow=True, arrowhead=2, ax=0, ay=-40,
            font=dict(size=11, color="#ef5350" if not is_bull else "#26a69a"), row=1, col=1,
        )

    # --- Gate 2: volume subplot, signal day highlighted ---
    vol_colors = ["#ef5350" if dt == sig.formation_date else "#4a4f5c" for dt in window.index]
    fig.add_trace(go.Bar(
        x=window.index, y=window["Volume"], marker_color=vol_colors, showlegend=False,
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=window.index, y=window["VolMA"], mode="lines", name=f"{vol_ma_period}-day Vol MA",
        line=dict(color="#ffb020", width=1.2, dash="dot"),
    ), row=2, col=1)

    fig.update_layout(
        title=dict(text=f"{sig.symbol} — {sig.pattern} ({sig.formation_date.strftime('%d %b %Y')})", font=dict(size=15)),
        height=560, template="plotly_dark",
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        margin=dict(l=10, r=90, t=45, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
    )
    fig.update_yaxes(title_text="Price (₹)", row=1, col=1, title_font_size=11)
    fig.update_yaxes(title_text="Volume", row=2, col=1, title_font_size=11)

    # Cap the volume axis instead of letting it auto-scale to the full
    # min-to-max range. A single outlier spike day (e.g. results, a
    # corporate action) can be many multiples of typical volume, which
    # otherwise crushes every normal day's bar into an unreadable sliver.
    # The 95th-percentile-based cap keeps normal days legible; a spike
    # bar still visibly reaches/exceeds the top of the chart rather than
    # being hidden, it just doesn't get to dictate the whole axis scale.
    vol_cap = window["Volume"].quantile(0.95) * 1.2
    vol_floor = window["Volume"].median() * 3
    fig.update_yaxes(range=[0, max(vol_cap, vol_floor)], row=2, col=1)

    return fig