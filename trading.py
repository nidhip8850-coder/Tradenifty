import streamlit as st
from datetime import datetime
import pytz

# ---- TIME SETTINGS ----
IST = pytz.timezone("Asia/Kolkata")
now = datetime.now(IST)

market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

st.title("PRO NIFTY OPTION SIGNAL")

st.write("Last updated:", now.strftime("%H:%M:%S"))

# ---- MARKET STATUS LOGIC ----
if market_open <= now <= market_close:
    status = "MARKET OPEN"
    color = "green"
else:
    status = "MARKET CLOSED"
    color = "orange"

st.markdown(
    f"<h1 style='color:{color}; font-weight:700;'>{status}</h1>",
    unsafe_allow_html=True
)

# ---- SHOW REASON ----
st.subheader("Reasons")

if status == "MARKET CLOSED":
    st.write("• Market is closed. Trading hours: 9:15 AM to 3:30 PM IST")
else:
    st.write("• Market is open. Signals will auto-refresh.")

# ---- AUTO REFRESH ----
st.button("Auto-refresh every 15 seconds")
