import streamlit as st
import pandas as pd
import threading
import datetime
import json
from websocket import WebSocketApp
from streamlit_autorefresh import st_autorefresh
import random
import altair as alt

# ----------------------------
# CONFIG
# ----------------------------
ASSETS = {
    "Bitcoin (BTC)": "bitcoin"
}
WEBSOCKET_URL = "wss://ws.coincap.io/prices?assets={asset_id}"
MAX_POINTS = 300  # keep last N points in memory

# ----------------------------
# INIT SESSION STATE
# ----------------------------
if "price_history" not in st.session_state:
    st.session_state.price_history = {asset_id: [] for asset_id in ASSETS.values()}
if "ws_threads" not in st.session_state:
    st.session_state.ws_threads = {}

# ----------------------------
# FUNCTIONS
# ----------------------------
def seed_local_price(asset_id: str):
    """Seed with a placeholder so the chart isn't empty."""
    if not st.session_state.price_history[asset_id]:
        fake_price = round(random.uniform(25000, 30000), 2)
        ts = datetime.datetime.utcnow()
        st.session_state.price_history[asset_id].append(
            {"time": ts, "price": fake_price, "source": "placeholder"}
        )

def on_message(ws, message, asset_id):
    """Handle incoming WebSocket messages."""
    try:
        data = json.loads(message)
        if asset_id in data:
            price = float(data[asset_id])
            ts = datetime.datetime.utcnow()
            st.session_state.price_history[asset_id].append(
                {"time": ts, "price": price, "source": "live"}
            )
            # Trim old points
            if len(st.session_state.price_history[asset_id]) > MAX_POINTS:
                st.session_state.price_history[asset_id] = st.session_state.price_history[asset_id][-MAX_POINTS:]
    except Exception as e:
        print(f"Error parsing message: {e}")

def start_ws_for_asset(asset_id: str):
    """Start WebSocket listener in a background thread."""
    if asset_id in st.session_state.ws_threads:
        return  # Already running

    def run_ws():
        ws_url = WEBSOCKET_URL.format(asset_id=asset_id)
        ws = WebSocketApp(ws_url, on_message=lambda ws, msg: on_message(ws, msg, asset_id))
        ws.run_forever()

    t = threading.Thread(target=run_ws, daemon=True)
    t.start()
    st.session_state.ws_threads[asset_id] = t

# ----------------------------
# STREAMLIT APP
# ----------------------------
st.set_page_config(page_title="Live Crypto Price", page_icon="📈", layout="centered")

st.title("📈 Live crypto price (demo)")
st.caption("Streaming live tick prices from CoinCap's WebSocket API.")

asset_label = st.selectbox("Choose asset to track:", list(ASSETS.keys()))
asset_id = ASSETS[asset_label]

# Seed placeholder
seed_local_price(asset_id)

# Start WebSocket
start_ws_for_asset(asset_id)

# Auto-refresh every 2 seconds
st_autorefresh(interval=2000, key="crypto_refresh")

# Build dataframe
df = pd.DataFrame(st.session_state.price_history[asset_id]).sort_values("time")

# Show latest metric
latest_price = df["price"].iloc[-1]
st.metric(label=f"{asset_label} — latest (USD)", value=f"${latest_price:,.2f}")

# ----------------------------
# Altair chart
# ----------------------------
base = alt.Chart(df).encode(
    x=alt.X("time:T", title="Time"),
    y=alt.Y("price:Q", title="Price (USD)")
)

# Live data line
live_line = base.transform_filter(
    alt.datum.source == "live"
).mark_line(color="steelblue").encode()

# Placeholder points (if any)
placeholder_points = base.transform_filter(
    alt.datum.source == "placeholder"
).mark_point(color="lightgray", size=60, shape="circle").encode()

chart = (live_line + placeholder_points).properties(
    width=700, height=400
)

st.altair_chart(chart, use_container_width=True)
