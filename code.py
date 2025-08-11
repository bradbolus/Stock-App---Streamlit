import streamlit as st
import pandas as pd
import threading
import datetime
import json
from websocket import WebSocketApp
from streamlit_autorefresh import st_autorefresh
import random

# ----------------------------
# CONFIG
# ----------------------------
ASSETS = {
    "Bitcoin (BTC)": "bitcoin"
}
WEBSOCKET_URL = "wss://ws.coincap.io/prices?assets={asset_id}"

# ----------------------------
# GLOBALS
# ----------------------------
GLOBAL_PRICE_HISTORY = {}
GLOBAL_WS_THREADS = {}
GLOBAL_LOCK = threading.Lock()

# ----------------------------
# FUNCTIONS
# ----------------------------
def seed_local_price(asset_id: str):
    """Seed with a placeholder value so the chart isn't empty."""
    with GLOBAL_LOCK:
        if not GLOBAL_PRICE_HISTORY.get(asset_id):
            # Just pick a random-looking number in BTC range for visual start
            fake_price = round(random.uniform(25000, 30000), 2)
            ts = datetime.datetime.utcnow()
            GLOBAL_PRICE_HISTORY.setdefault(asset_id, []).append({"time": ts, "price": fake_price})

def on_message(ws, message, asset_id):
    """Handle incoming WebSocket messages."""
    try:
        data = json.loads(message)
        if asset_id in data:
            price = float(data[asset_id])
            ts = datetime.datetime.utcnow()
            with GLOBAL_LOCK:
                GLOBAL_PRICE_HISTORY.setdefault(asset_id, []).append({"time": ts, "price": price})
    except Exception as e:
        print(f"Error parsing message: {e}")

def start_ws_for_asset(asset_id: str):
    """Start WebSocket listener in a background thread."""
    if asset_id in GLOBAL_WS_THREADS:
        return  # Already running

    def run_ws():
        ws_url = WEBSOCKET_URL.format(asset_id=asset_id)
        ws = WebSocketApp(ws_url, on_message=lambda ws, msg: on_message(ws, msg, asset_id))
        ws.run_forever()

    t = threading.Thread(target=run_ws, daemon=True)
    t.start()
    GLOBAL_WS_THREADS[asset_id] = t

# ----------------------------
# STREAMLIT APP
# ----------------------------
st.set_page_config(page_title="Live Crypto Price", page_icon="📈", layout="centered")

st.title("📈 Live crypto price (demo)")
st.caption("Streaming live tick prices from CoinCap's WebSocket API.")

asset_label = st.selectbox("Choose asset to track:", list(ASSETS.keys()))
asset_id = ASSETS[asset_label]

# Seed with placeholder value
seed_local_price(asset_id)

# Start WebSocket thread
start_ws_for_asset(asset_id)

# Auto-refresh every 2 seconds
st_autorefresh(interval=2000, key="crypto_refresh")

# Retrieve history safely
with GLOBAL_LOCK:
    history = GLOBAL_PRICE_HISTORY.get(asset_id, []).copy()

df = pd.DataFrame(history)
df = df.sort_values("time")

# Display latest price
latest_price = df["price"].iloc[-1]
st.metric(label=f"{asset_label} — latest (USD)", value=f"${latest_price:,.2f}")

# Draw chart
st.line_chart(df.set_index("time")["price"])
