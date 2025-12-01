import requests
import json
import time
import threading
from datetime import datetime, time as dt_time
import pandas as pd
import yfinance as yf
from flask import Flask, render_template_string
import logging
import numpy as np
import streamlit as st

# ---------------- CONFIG ----------------
SYMBOL = "NIFTY"
OPTION_CHAIN_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}
LOOP_SECONDS = 15  # Increased refresh time for stability
YF_TICKER = "^NSEI"
ATM_PCR_UPPER = 1.2
ATM_PCR_LOWER = 0.8

# Market timings for NSE (9:15 AM to 3:30 PM IST)
MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)

# Setup logging
logging.basicConfig(filename="app.log", level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

app = Flask(__name__)

latest_signal = {"time": None, "signal": None, "reasons": []}
running = True

# ---------- Utility Functions ----------

def is_market_open():
    now = datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE

def get_nse_session():
    s = requests.Session()
    try:
        s.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
        time.sleep(0.3)
    except Exception as e:
        logging.error(f"Initial NSE session setup failed: {e}")
    return s

def safe_json_load(resp):
    try:
        return resp.json()
    except Exception:
        text = resp.text
        idx = text.rfind("}")
        if idx != -1:
            try:
                return json.loads(text[: idx + 1])
            except Exception as e:
                logging.error(f"JSON partial load failed: {e}")
                return None
        return None

def fetch_option_chain(session):
    tries = 0
    backoff = 1
    while tries < 5:
        try:
            r = session.get(OPTION_CHAIN_URL, headers=HEADERS, timeout=10)
            r.raise_for_status()
            return safe_json_load(r)
        except Exception as e:
            logging.warning(f"Fetch attempt {tries + 1} failed: {e}")
            tries += 1
            time.sleep(backoff)
            backoff *= 2
    logging.error("Failed to fetch option chain after retries")
    return None

def flatten_option_chain(json_data):
    if not json_data:
        return pd.DataFrame()

    rec = json_data.get("records", {})
    underlying = rec.get("underlyingValue", None)
    data = rec.get("data", [])
    rows = []

    for item in data:
        strike = item.get("strikePrice")
        ce = item.get("CE")
        pe = item.get("PE")

        if ce:
            rows.append({
                "side": "CE",
                "strike": strike,
                "oi": float(ce.get("openInterest", 0)),
                "coi": float(ce.get("changeinOpenInterest", 0)),
                "vol": float(ce.get("totalTradedVolume", 0)),
                "iv": float(ce.get("impliedVolatility", 0)) if ce.get("impliedVolatility") else 0,
                "underlying": underlying
            })
        if pe:
            rows.append({
                "side": "PE",
                "strike": strike,
                "oi": float(pe.get("openInterest", 0)),
                "coi": float(pe.get("changeinOpenInterest", 0)),
                "vol": float(pe.get("totalTradedVolume", 0)),
                "iv": float(pe.get("impliedVolatility", 0)) if pe.get("impliedVolatility") else 0,
                "underlying": underlying
            })

    return pd.DataFrame(rows)

def market_trend_last5():
    try:
        df = yf.download(YF_TICKER, period="1d", interval="1m", progress=False)
        if df.empty:
            return "NEUTRAL", df

        closes = df["Close"].values
        if len(closes) < 5:
            return "NEUTRAL", df

        last5 = closes[-5:]
        if all(last5[i] > last5[i - 1] for i in range(1, 5)):
            return "UP", df
        if all(last5[i] < last5[i - 1] for i in range(1, 5)):
            return "DOWN", df
        return "NEUTRAL", df
    except Exception as e:
        logging.error(f"Error in market_trend_last5: {e}")
        return "NEUTRAL", pd.DataFrame()

# Calculate RSI - helper function
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Simple support/resistance using pivot highs/lows
def find_support_resistance(prices, window=5):
    supports = []
    resistances = []
    for i in range(window, len(prices) - window):
        segment = prices[i-window:i+window+1]
        current = prices[i]
        if current == min(segment):
            supports.append(current)
        if current == max(segment):
            resistances.append(current)
    return supports, resistances

# Simple bullish engulfing pattern detector on last 2 candles
def is_bullish_engulfing(df):
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    # Prev candle bearish
    if prev['Close'] >= prev['Open']:
        return False
    # Current candle bullish and engulf prev
    if curr['Close'] > curr['Open'] and curr['Open'] < prev['Close'] and curr['Close'] > prev['Open']:
        return True
    return False

def compute_signal(df):
    if not is_market_open():
        return "MARKET CLOSED", ["Market is closed. Trading hours: 9:15 AM to 3:30 PM IST"]

    if df.empty:
        return "NO DATA", ["Option chain empty"]

    underlying = df["underlying"].dropna().unique()
    if len(underlying) == 0:
        return "NO DATA", ["Underlying missing"]

    underlying_val = underlying[0]
    atm = int(round(underlying_val / 50) * 50)

    atm_rows = df[df["strike"] == atm]
    if atm_rows.empty:
        return "NO DATA", [f"ATM {atm} missing"]

    ce = atm_rows[atm_rows["side"] == "CE"].iloc[0]
    pe = atm_rows[atm_rows["side"] == "PE"].iloc[0]

    reasons = [f"Underlying = {underlying_val}, ATM = {atm}"]

    # Volume fight
    if pe["vol"] > ce["vol"]:
        vol_side = "PE"
        reasons.append("PE Volume > CE Volume")
    elif ce["vol"] > pe["vol"]:
        vol_side = "CE"
        reasons.append("CE Volume > PE Volume")
    else:
        vol_side = "NEUTRAL"
        reasons.append("Volumes equal")

    # COI fight
    if pe["coi"] > ce["coi"]:
        oi_side = "PE"
        reasons.append("PE COI > CE COI")
    elif ce["coi"] > pe["coi"]:
        oi_side = "CE"
        reasons.append("CE COI > PE COI")
    else:
        oi_side = "NEUTRAL"
        reasons.append("COI equal")

    # PCR
    pcr = round(pe["oi"] / ce["oi"], 2) if ce["oi"] else 1.0
    reasons.append(f"PCR = {pcr}")

    if pcr > ATM_PCR_UPPER:
        pcr_side = "CE"
    elif pcr < ATM_PCR_LOWER:
        pcr_side = "PE"
    else:
        pcr_side = "NEUTRAL"

    # Trend & underlying data fetch
    trend, df_und = market_trend_last5()
    reasons.append(f"Trend = {trend}")

    # Calculate RSI
    rsi = calculate_rsi(df_und['Close'])
    latest_rsi = round(rsi.iloc[-1], 2) if not rsi.empty else None
    reasons.append(f"RSI(14) = {latest_rsi}")

    # Support and Resistance levels
    supports, resistances = find_support_resistance(df_und['Close'])
    reasons.append(f"Support levels (last): {supports[-3:] if supports else 'N/A'}")
    reasons.append(f"Resistance levels (last): {resistances[-3:] if resistances else 'N/A'}")

    # Bullish engulfing pattern detection
    bullish_engulf = is_bullish_engulfing(df_und)
    reasons.append(f"Bullish Engulfing Pattern: {'Yes' if bullish_engulf else 'No'}")

    votes = [vol_side, oi_side, pcr_side]
    if trend == "UP":
        votes.append("CE")
    elif trend == "DOWN":
        votes.append("PE")

    # Adding IV based decision
    iv_ce = ce["iv"]
    iv_pe = pe["iv"]
    reasons.append(f"IV CE = {iv_ce:.2f}, IV PE = {iv_pe:.2f}")

    # Example: if IV PE > IV CE by 10% or more, add PE vote (indicates higher fear)
    if iv_pe > iv_ce * 1.1:
        votes.append("PE")
        reasons.append("IV PE significantly higher than IV CE, added PE vote")
    elif iv_ce > iv_pe * 1.1:
        votes.append("CE")
        reasons.append("IV CE significantly higher than IV PE, added CE vote")

    ce_votes = votes.count("CE")
    pe_votes = votes.count("PE")

    reasons.append(f"Votes -> CE:{ce_votes}, PE:{pe_votes}")

    if ce_votes > pe_votes and ce_votes >= 2:
        return "BUY CE", reasons
    if pe_votes > ce_votes and pe_votes >= 2:
        return "BUY PE", reasons

    if bullish_engulf and trend == "UP":
        return "STRONG BUY CE (Bullish Engulfing)", reasons

    return "NO TRADE", reasons


def data_fetch_loop():
    global latest_signal
    session = get_nse_session()

    while running:
        try:
            json_data = fetch_option_chain(session)
            if json_data is None:
                session = get_nse_session()
                time.sleep(3)
                continue

            df = flatten_option_chain(json_data)
            signal, reasons = compute_signal(df)
            now = datetime.now().strftime("%H:%M:%S")

            latest_signal = {
                "time": now,
                "signal": signal,
                "reasons": reasons
            }
        except Exception as e:
            logging.error(f"Error in data fetch loop: {e}")

        time.sleep(LOOP_SECONDS)


@app.route("/")
def home():
    html = """
    <html>
        <head>
            <title>PRO NIFTY OPTION BUYING - Signal</title>
            <meta http-equiv="refresh" content="{{refresh}}">
            <style>
                * { box-sizing: border-box; }

                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 40px 20px;
                    color: #333;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    transition: background 0.8s ease;
                }

                /* Background colors for different signals */
                body.market-closed {
                    background: #f39c12; /* orange */
                    color: #fff;
                }
                body.no-trade {
                    background: #7f8c8d; /* gray */
                    color: #fff;
                }
                body.buy-ce {
                    background: #27ae60; /* green */
                    color: #fff;
                }
                body.buy-pe {
                    background: #c0392b; /* red */
                    color: #fff;
                }
                body.strong-buy {
                    background: #2980b9; /* blue */
                    color: #fff;
                }

                .container {
                    background: rgba(255,255,255,0.9);
                    padding: 30px 40px;
                    border-radius: 12px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.12);
                    max-width: 720px;
                    width: 100%;
                    text-align: center;
                    color: #333;
                }

                h1 {
                    font-weight: 700;
                    font-size: 2.6rem;
                    color: inherit;
                    margin-bottom: 15px;
                    letter-spacing: 1px;
                }

                .time {
                    font-size: 1rem;
                    color: inherit;
                    margin-bottom: 20px;
                    font-style: italic;
                }

                .signal {
                    font-size: 2.2rem;
                    font-weight: 900;
                    margin: 20px 0;
                    padding: 15px;
                    border-radius: 8px;
                    text-transform: uppercase;
                    letter-spacing: 2px;
                    user-select: none;
                    color: inherit;
                }

                /* Colors for signal text box */
                .buy-ce   { color: #27ae60; background: #ecf9f1; box-shadow: inset 0 0 8px rgba(39,174,96,0.3); }
                .buy-pe   { color: #c0392b; background: #fdecea; box-shadow: inset 0 0 8px rgba(192,57,43,0.3); }
                .no-trade { color: #7f8c8d; background: #f4f4f4; box-shadow: inset 0 0 8px rgba(150,150,150,0.25); }
                .strong-buy { color: #2980b9; background: #e8f4fd; box-shadow: inset 0 0 10px rgba(41,128,185,0.4); }

                .reasons-box {
                    text-align: left;
                    margin-top: 20px;
                    padding: 20px;
                    background: #fafafa;
                    border-radius: 10px;
                    box-shadow: 0 0 8px rgba(0,0,0,0.05);
                    color: #333;
                }

                .reasons-box ul {
                    padding-left: 20px;
                }

                .footer {
                    margin-top: 25px;
                    font-size: 0.8rem;
                    color: #888;
                }
            </style>
        </head>

        <body class="{{body_class}}">
            <div class="container">
                <h1>PRO NIFTY OPTION SIGNAL</h1>

                <div class="time">Last updated: {{time}}</div>

                <div class="signal {{cls}}">{{signal}}</div>

                <div class="reasons-box">
                    <h3>Reasons</h3>
                    <ul>
                        {% for r in reasons %}
                            <li>{{r}}</li>
                        {% endfor %}
                    </ul>
                </div>

                <div class="footer">Auto-refresh every {{refresh}} seconds</div>
            </div>
        </body>
    </html>
    """

    sig = latest_signal.get("signal", "")
    cls = "no-trade"
    body_class = "no-trade"

    if "MARKET CLOSED" in sig:
        body_class = "market-closed"
    elif "BUY CE" in sig:
        cls = "buy-ce"
        body_class = "buy-ce"
    elif "BUY PE" in sig:
        cls = "buy-pe"
        body_class = "buy-pe"
    elif "STRONG BUY CE" in sig:
        cls = "strong-buy"
        body_class = "strong-buy"
    elif sig == "NO TRADE" or sig == "NEUTRAL":
        body_class = "no-trade"
    else:
        # fallback to no-trade
        body_class = "no-trade"

    return render_template_string(
        html,
        time=latest_signal.get("time", "--:--:--"),
        signal=latest_signal.get("signal", "NO DATA"),
        reasons=latest_signal.get("reasons", []),
        cls=cls,
        body_class=body_class,
        refresh=LOOP_SECONDS
    )




if __name__ == "__main__":
    threading.Thread(target=data_fetch_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
