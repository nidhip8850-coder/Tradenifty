import requests
import json
import time
from datetime import datetime, time as dt_time
import pandas as pd
import yfinance as yf
import logging
import numpy as np
import streamlit as st
import pytz

hide_streamlit_style = """
    <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
# -----------------------------------

st.title("My Clean Streamlit App")
st.write("Header / Footer removed successfully!")

# ---------------- CONFIG ----------------
SYMBOL = "NIFTY"
OPTION_CHAIN_URL = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}
LOOP_SECONDS = 15  # refresh time
YF_TICKER = "^NSEI"
ATM_PCR_UPPER = 1.2
ATM_PCR_LOWER = 0.8

MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)

logging.basicConfig(filename="app.log", level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s'))

# ---------------- STREAMLIT SETUP ----------------
st.set_page_config(page_title="PRO NIFTY OPTION SIGNAL", layout="wide")
st.title("PRO NIFTY OPTION SIGNAL")
placeholder = st.empty()

# ---------- FIXED MARKET TIME FUNCTION ----------
def is_market_open():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    current_time = now.time()

    # Sat/Sun closed
    if now.weekday() >= 5:
        return False

    # Time check
    return MARKET_OPEN <= current_time <= MARKET_CLOSE

# ---------- OTHER FUNCTIONS (unchanged) ----------
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

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

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

def is_bullish_engulfing(df):
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    if prev['Close'] >= prev['Open']:
        return False
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

    # Volume
    if pe["vol"] > ce["vol"]:
        vol_side = "PE"
        reasons.append("PE Volume > CE Volume")
    elif ce["vol"] > pe["vol"]:
        vol_side = "CE"
        reasons.append("CE Volume > PE Volume")
    else:
        vol_side = "NEUTRAL"
        reasons.append("Volumes equal")

    # COI
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

    # Trend
    trend, df_und = market_trend_last5()
    reasons.append(f"Trend = {trend}")

    # RSI
    rsi = calculate_rsi(df_und['Close'])
    latest_rsi = round(rsi.iloc[-1], 2) if not rsi.empty else None
    reasons.append(f"RSI(14) = {latest_rsi}")

    # S/R
    supports, resistances = find_support_resistance(df_und['Close'])
    reasons.append(f"Support levels (last): {supports[-3:] if supports else 'N/A'}")
    reasons.append(f"Resistance levels (last): {resistances[-3:] if resistances else 'N/A'}")

    # Pattern
    bullish_engulf = is_bullish_engulfing(df_und)
    reasons.append(f"Bullish Engulfing Pattern: {'Yes' if bullish_engulf else 'No'}")

    # Votes
    votes = [vol_side, oi_side, pcr_side]

    if trend == "UP":
        votes.append("CE")
    elif trend == "DOWN":
        votes.append("PE")

    iv_ce = ce["iv"]
    iv_pe = pe["iv"]
    reasons.append(f"IV CE = {iv_ce:.2f}, IV PE = {iv_pe:.2f}")

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

# ---------------- SESSION ----------------
session = get_nse_session()

# ---------------- MAIN LOOP ----------------
while True:
    try:
        json_data = fetch_option_chain(session)
        df = flatten_option_chain(json_data)
        signal, reasons = compute_signal(df)
        now = datetime.now().strftime("%H:%M:%S")

        if "MARKET CLOSED" in signal:
            color = "#f39c12"
        elif "BUY CE" in signal:
            color = "#27ae60"
        elif "BUY PE" in signal:
            color = "#c0392b"
        elif "STRONG BUY CE" in signal:
            color = "#2980b9"
        else:
            color = "#7f8c8d"

        with placeholder.container():
            st.markdown(f"<h2 style='color:{color}'>Last updated: {now}</h2>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='color:{color}'>{signal}</h1>", unsafe_allow_html=True)
            st.subheader("Reasons")
            for r in reasons:
                st.write(f"- {r}")
            st.info(f"Auto-refresh every {LOOP_SECONDS} seconds")

    except Exception as e:
        with placeholder.container():
            st.error(f"Error fetching data: {e}")

    time.sleep(LOOP_SECONDS)
