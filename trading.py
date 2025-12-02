import streamlit as st
from datetime import datetime
import pytz
import time

# ========== TIME SETTINGS ==========
IST = pytz.timezone("Asia/Kolkata")

def get_market_status():
    now = datetime.now(IST)

    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if market_open <= now <= market_close:
        return "MARKET OPEN", now
    else:
        return "MARKET CLOSED", now


# ========== UI START ==========
st.set_page_config(page_title="Pro Nifty Option Signal", layout="centered")

st.title("🚀 PRO NIFTY OPTION SIGNAL")

status, now = get_market_status()

st.write("Last updated:", now.strftime("%H:%M:%S"))

# UI STATUS COLOR
if status == "MARKET OPEN":
    st.markdown(
        "<h1 style='color:green; font-weight:700;'>MARKET OPEN</h1>",
        unsafe_allow_html=True
    )
else:
    st.markdown(
        "<h1 style='color:orange; font-weight:700;'>MARKET CLOSED</h1>",
        unsafe_allow_html=True
    )


# ========== REASONS BOX ==========
st.subheader("Reasons")

if status == "MARKET CLOSED":
    st.write("• Market is closed. Trading hours: 9:15 AM to 3:30 PM IST ❌")
else:
    st.write("• Market is open. Signals will auto-refresh ✔️")


# ========== LIVE SIGNAL UI (SAME CONDITION PAR) ==========
st.subheader("📊 Live Nifty Option Signal")

if status == "MARKET OPEN":
    st.success("Waiting for signal... (market open)")
    st.info("Auto-refresh every 15 seconds enabled")
else:
    st.warning("Signal OFF — Market Closed")


# ========== AUTO REFRESH BUTTON ==========
if st.button("Auto-refresh now"):
    st.experimental_rerun()


# ========== AUTO REFRESH EVERY 15s ==========
time.sleep(15)
st.experimental_rerun()
