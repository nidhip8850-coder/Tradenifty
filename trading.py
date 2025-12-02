import streamlit as st
from datetime import datetime
import pytz
import random
import time

# ================== SETTINGS ==================
IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN  = (9, 15)
MARKET_CLOSE = (15, 30)


def is_market_open():
    now = datetime.now(IST)
    open_time  = now.replace(hour=MARKET_OPEN[0],  minute=MARKET_OPEN[1])
    close_time = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1])
    return open_time <= now <= close_time


def generate_signal():
    """Dummy signal generator"""
    signals = ["BUY CE", "BUY PE", "NO TRADE"]
    return random.choice(signals)


# ================== UI START ==================
st.set_page_config(page_title="Pro Nifty Option Buying - Live Signal")

st.title("🚀 PRO NIFTY OPTION BUYING - LIVE SIGNAL")

# Timestamp
now = datetime.now(IST)
last_time = now.strftime("%H:%M:%S")

st.write(f"⏰ **Last Updated:** {last_time}")


# ================== SIGNAL ==================
if is_market_open():

    # generate dummy live signal
    signal = generate_signal()

    st.subheader(f"📢 Signal: {signal}")

else:
    st.subheader("📢 Signal: Market Closed")


# ================== REASONS ==================
with st.expander("📌 Detailed Reasons"):

    if is_market_open():
        st.write("✔ Market open (9:15 AM - 3:30 PM IST)")
        st.write("✔ Live auto signal enabled")
    else:
        st.write("❌ Market closed")
        st.write("Trading hours: 9:15 AM to 3:30 PM IST")


# ================== AUTO REFRESH ==================
time.sleep(15)
st.experimental_rerun()
