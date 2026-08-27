"""
Config module — fixed Nifty 100 universe and Trade Type parameter presets.
Per requirements doc: Universe is hardcoded (no Nifty 500 / custom list).
Trade Type is the single cascading switch that sets every downstream parameter.
"""

# ---------------------------------------------------------------------------
# Universe (fixed — Section 1 of requirements doc)
# ---------------------------------------------------------------------------
NIFTY_100_MAP = {
    "HDFCBANK": "HDFC Bank Ltd.",
    "ICICIBANK": "ICICI Bank Ltd.",
    "RELIANCE": "Reliance Industries Ltd.",
    "BHARTIARTL": "Bharti Airtel Ltd.",
    "LT": "Larsen & Toubro Ltd.",
    "SBIN": "State Bank of India",
    "INFY": "Infosys Ltd.",
    "AXISBANK": "Axis Bank Ltd.",
    "M&M": "Mahindra & Mahindra Ltd.",
    "BAJFINANCE": "Bajaj Finance Ltd.",
    "KOTAKBANK": "Kotak Mahindra Bank Ltd.",
    "ITC": "ITC Ltd.",
    "ETERNAL": "Eternal Ltd. (Zomato)",
    "TCS": "Tata Consultancy Services Ltd.",
    "TITAN": "Titan Company Ltd.",
    "SUNPHARMA": "Sun Pharmaceutical Industries Ltd.",
    "HINDUNILVR": "Hindustan Unilever Ltd.",
    "MARUTI": "Maruti Suzuki India Ltd.",
    "NTPC": "NTPC Ltd.",
    "SHRIRAMFIN": "Shriram Finance Ltd.",
    "TATASTEEL": "Tata Steel Ltd.",
    "HINDALCO": "Hindalco Industries Ltd.",
    "BEL": "Bharat Electronics Ltd.",
    "HCLTECH": "HCL Technologies Ltd.",
    "ULTRACEMCO": "UltraTech Cement Ltd.",
    "BAJAJ-AUTO": "Bajaj Auto Ltd.",
    "ADANIPORTS": "Adani Ports & SEZ Ltd.",
    "GRASIM": "Grasim Industries Ltd.",
    "JSWSTEEL": "JSW Steel Ltd.",
    "POWERGRID": "Power Grid Corp of India Ltd.",
    "ASIANPAINT": "Asian Paints Ltd.",
    "BAJAJFINSV": "Bajaj Finserv Ltd.",
    "INDIGO": "InterGlobe Aviation Ltd. (IndiGo)",
    "EICHERMOT": "Eicher Motors Ltd.",
    "DIVISLAB": "Divi's Laboratories Ltd.",
    "NESTLEIND": "Nestle India Ltd.",
    "TVSMOTOR": "TVS Motor Company Ltd.",
    "TECHM": "Tech Mahindra Ltd.",
    "TMCV": "Tata Motors Commercial Vehicles Ltd.",
    "TRENT": "Trent Ltd.",
    "COALINDIA": "Coal India Ltd.",
    "HAL": "Hindustan Aeronautics Ltd.",
    "ONGC": "Oil & Natural Gas Corp Ltd.",
    "APOLLOHOSP": "Apollo Hospitals Enterprise Ltd.",
    "ADANIENT": "Adani Enterprises Ltd.",
    "ADANIPOWER": "Adani Power Ltd.",
    "CHOLAFIN": "Cholamandalam Investment & Fin Ltd.",
    "CIPLA": "Cipla Ltd.",
    "SBILIFE": "SBI Life Insurance Co. Ltd.",
    "JIOFIN": "Jio Financial Services Ltd.",
    "MOTHERSON": "Samvardhana Motherson Intl Ltd.",
    "TORNTPHARM": "Torrent Pharmaceuticals Ltd.",
    "MAXHEALTH": "Max Healthcare Institute Ltd.",
    "DRREDDY": "Dr. Reddy's Laboratories Ltd.",
    "CUMMINSIND": "Cummins India Ltd.",
    "TATACONSUM": "Tata Consumer Products Ltd.",
    "TMPV": "Tata Motors Passenger Vehicles Ltd.",
    "BRITANNIA": "Britannia Industries Ltd.",
    "DMART": "Avenue Supermarts Ltd. (DMart)",
    "INDHOTEL": "The Indian Hotels Co. Ltd.",
    "BPCL": "Bharat Petroleum Corp Ltd.",
    "TATAPOWER": "Tata Power Company Ltd.",
    "VBL": "Varun Beverages Ltd.",
    "CGPOWER": "CG Power & Industrial Solutions Ltd.",
    "HDFCLIFE": "HDFC Life Insurance Co. Ltd.",
    "PFC": "Power Finance Corporation Ltd.",
    "HDFCAMC": "HDFC Asset Management Co. Ltd.",
    "PIDILITIND": "Pidilite Industries Ltd.",
    "IOC": "Indian Oil Corporation Ltd.",
    "ADANIENSOL": "Adani Energy Solutions Ltd.",
    "WIPRO": "Wipro Ltd.",
    "BAJAJHLDNG": "Bajaj Holdings & Investment Ltd.",
    "SOLARINDS": "Solar Industries India Ltd.",
    "GAIL": "GAIL (India) Ltd.",
    "BANKBARODA": "Bank of Baroda",
    "VEDL": "Vedanta Ltd.",
    "UNITDSPR": "United Spirits Ltd.",
    "DLF": "DLF Ltd.",
    "CANBK": "Canara Bank",
    "ADANIGREEN": "Adani Green Energy Ltd.",
    "LTM": "LTIMindtree Ltd.",
    "BOSCHLTD": "Bosch Ltd.",
    "JINDALSTEL": "Jindal Steel & Power Ltd.",
    "PNB": "Punjab National Bank",
    "RECLTD": "REC Ltd.",
    "ABB": "ABB India Ltd.",
    "GODREJCP": "Godrej Consumer Products Ltd.",
    "UNIONBANK": "Union Bank of India",
    "LODHA": "Macrotech Developers Ltd. (Lodha)",
    "SIEMENS": "Siemens Ltd.",
    "SHREECEM": "Shree Cement Ltd.",
    "HYUNDAI": "Hyundai Motor India Ltd.",
    "MUTHOOTFIN": "Muthoot Finance Ltd.",
    "ENRIN": "Niva Bupa Health Insurance Ltd.",
    "ZYDUSLIFE": "Zydus Lifesciences Ltd.",
    "HINDZINC": "Hindustan Zinc Ltd.",
    "AMBUJACEM": "Ambuja Cements Ltd.",
    "MAZDOCK": "Mazagon Dock Shipbuilders Ltd.",
    "TATACAP": "Tata Capital Ltd.",
    "IRFC": "Indian Railway Finance Corp Ltd.",
}

NSE_SUFFIX = ".NS"


def yf_symbol(nse_symbol: str) -> str:
    """Convert an NSE ticker (e.g. 'INFY') to its yfinance symbol ('INFY.NS')."""
    return f"{nse_symbol}{NSE_SUFFIX}"


# ---------------------------------------------------------------------------
# Trade Type parameter presets (Section 4 of requirements doc)
# Trade Type is the ONLY user-facing switch — every value below is derived
# from it, never individually exposed as a raw filter.
# ---------------------------------------------------------------------------
TRADE_TYPE_PARAMS = {
    "short_term": {
        "label": "Short-term",
        "sr_lookback_months": 4,          # 3-6 months -> default mid-point
        "sr_lookback_days": 90,           # approx trading days for 4 months
        "fractal_width": 5,               # candles either side
        "min_touch_separation_days": 7,
        "primary_trend_ma": 20,
        "pattern_prior_trend_lookback": 7,  # candles
    },
    "long_term": {
        "label": "Long-term",
        "sr_lookback_months": 15,         # 12-18 months -> default mid-point
        "sr_lookback_days": 320,          # approx trading days for 15 months
        "fractal_width": 10,
        "min_touch_separation_days": 15,
        "primary_trend_ma": 50,
        "pattern_prior_trend_lookback": 15,
    },
}

DEFAULT_TRADE_TYPE = "short_term"

# ---------------------------------------------------------------------------
# Parameters constant regardless of Trade Type
# ---------------------------------------------------------------------------
SR_ZONE_TOLERANCE_PCT = 1.0            # zone buffer, % of price (was 0.75%, widened)
SR_MAX_DISTANCE_PCT_DEFAULT = 4.0      # max allowed % gap between candle-SL and nearest S/R zone, user-editable
SL_BUFFER_PCT = 0.3                    # buffer beyond the candle low/high used for the actual stop-loss
MAX_CUSTOM_TICKERS = 50                # cap on user-entered custom ticker list, not persisted across sessions
VOLUME_MA_PERIOD_DEFAULT = 10          # days, user-configurable in UI
MIN_RR_DEFAULT = 2.0                   # user-configurable in UI
MARUBOZU_SHADOW_TOLERANCE_PCT = 7.0    # fixed system parameter, NOT a UI filter
TREND_SLOPE_LOOKBACK_DAYS = 12         # for MA slope up/down check
SIDEWAYS_FLIP_WINDOW = 10              # candles checked for MA-crossing flips
SIGNAL_SCAN_LOOKBACK_DAYS = 30         # live-computed signal scan window (Section 5)

# Indicator periods — same for both Trade Types in v1 (Section 3.3 / Section 9 v2 item)
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER = 10, 3
AROON_PERIOD = 14