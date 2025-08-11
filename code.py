import streamlit as st
import pandas as pd
import requests
import threading
import datetime
import json
from websocket import WebSocketApp
from streamlit_autorefresh import st_autorefresh

# ----------------------------
# CONFIG
# ----------------------------
ASSETS = {
    "Bitcoin (BTC)": "bitcoin"
}
WEBSOCKET_URL = "wss://ws.coincap.io/prices?assets={asset_id}"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

# ----------------------------
# GLOBALS
# ----------------------------
GLOBAL_PRICE_HISTORY = {}
GLOBAL_WS_THREADS = {}
GLOBAL_LOCK = threading.Lock()

# ----------------------------
# FUNCTIONS
# ----------------------------
def seed_price_once(asset_id: str):
    """Fetch one initial price from CoinGecko only if no history exists."""
    with GLOBAL_LOCK:
        if GLOBAL_PRICE_HISTORY.get(asset_id):
            return  # Already have data, no need to seed

    try:
        resp = requests.get(
            COINGECKO_URL,
            params={"ids": asset_id, "vs_currencies": "usd"},
            timeout=5
        )
        resp.raise_for_status()
        price = float(resp.json()[asset_id]["usd"])
        ts = datetime.datetime.utcnow()
        with GLOBAL_LOCK:
            GLOBAL_PRICE_HISTORY.setdefault(asset_id, []).append({"time": ts, "price": price})
    except Exception as e:
        st.warning(f"⚠️ Could not seed price via REST: {e}")

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

# Seed once if needed
seed_price_once(asset_id)

# Start WebSocket thread
start_ws_for_asset(asset_id)

# Auto-refresh every 2 seconds
st_autorefresh(interval=2000, key="crypto_refresh")

# Retrieve history safely
with GLOBAL_LOCK:
    history = GLOBAL_PRICE_HISTORY.get(asset_id, []).copy()

if not history:
    st.info("⏳ Waiting for first datapoint from WebSocket...")
else:
    df = pd.DataFrame(history)
    df = df.sort_values("time")

    latest_price = df["price"].iloc[-1]
    st.metric(label=f"{asset_label} — latest (USD)", value=f"${latest_price:,.2f}")

    st.line_chart(df.set_index("time")["price"])
