import requests
import json
import time
import pytz
from datetime import datetime, time as dt_time
import pandas as pd
import yfinance as yf
import logging
import numpy as np
import streamlit as st

# ---------------- STREAMLIT UI ----------------

hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
st.set_page_config(page_title="NIFTY SIGNAL BOT — LIVE", layout="wide")

# ---------------- TIMEZONE SETUP ----------------

IST = pytz.timezone("Asia/Kolkata")

def get_ist_time():
    """Return current IST datetime"""
    return datetime.now(IST)

# ---------------- MARKET TIME CHECK ----------------

MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)

def is_market_open():
    now = get_ist_time()
    current_time = now.time()

    # Weekday check (Mon–Fri)
    if now.weekday() >= 5:
        return False

    # Time range check
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


# ---------------- SHOW MARKET STATUS ----------------
st.title("📈 NIFTY OPTION SIGNAL BOT (IST Time Enabled)")

current_ist = get_ist_time().strftime("%Y-%m-%d %H:%M:%S")
st.subheader(f"🕒 Current IST Time: **{current_ist}**")

if is_market_open():
    st.success("🟢 MARKET OPEN — Live Signals Active")
else:
    st.error("🔴 MARKET CLOSED — Signals Paused")


# ---------------- YOUR EXISTING CODE CONTINUES BELOW ----------------
# Kuch bhi delete nahi kiya… yahan se niche aapka pura code as it is rahega.
