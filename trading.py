import requests
import json
import time
from datetime import datetime, time as dt_time
import pandas as pd
import yfinance as yf
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
LOOP_SECONDS = 15  # refresh time
YF_TICKER = "^NSEI"
ATM_PCR_UPPER = 1.2
ATM_PCR_LOWER = 0.8

MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)

logging.basicConfig(filename="app.log", level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# ---------------- STREAMLIT SETUP ----------------
st.set_page_config(page_title="PRO NIFTY OPTION SIGNAL", layout="wide")
st.title("PRO NIFTY OPTION SIGNAL")

# Placeholder for auto-refresh
placeholder = st.empty()

# ---------- UTILITY FUNCTIONS ----------
# Copy all your previous utility functions here
# Example: is_market_open, get_nse_session, safe_json_load, fetch_option_chain, flatten_option_chain, market_trend_last5, calculate_rsi, find_support_resistance, is_bullish_engulfing, compute_signal
# (All logic unchanged from your original Flask code)

# ---------------- SESSION ----------------
session = requests.Session()
try:
    session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
    time.sleep(0.3)
except Exception as e:
    logging.error(f"NSE session init failed: {e}")

# ---------------- MAIN LOOP ----------------
while True:
    try:
        json_data = fetch_option_chain(session)
        df = flatten_option_chain(json_data)
        signal, reasons = compute_signal(df)
        now = datetime.now().strftime("%H:%M:%S")

        # Determine color for Streamlit display (matches your Flask background)
        if "MARKET CLOSED" in signal:
            color = "#f39c12"  # orange
        elif "BUY CE" in signal:
            color = "#27ae60"  # green
        elif "BUY PE" in signal:
            color = "#c0392b"  # red
        elif "STRONG BUY CE" in signal:
            color = "#2980b9"  # blue
        else:
            color = "#7f8c8d"  # gray / no-trade

        with placeholder.container():
            st.markdown(f"<h2 style='color:{color}'>Last updated: {now}</h2>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='color:{color}'>{signal}</h1>", unsafe_allow_html=True)
            st.subheader("Reasons")
            for r in reasons:
                st.write(f"- {r}")
            st.info(f"Auto-refresh every {LOOP_SECONDS} seconds")

    except Exception as e:
        st.error(f"Error fetching data: {e}")

    time.sleep(LOOP_SECONDS)
