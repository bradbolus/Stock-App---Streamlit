import streamlit as st
import pandas as pd
import requests
import threading
import json
import datetime
import websocket
import altair as alt
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Live Bitcoin Price", layout="centered")

# Refresh every 2 seconds
st_autorefresh(interval=2000, key="crypto_refresh")

# Initialize session state
if "price_history" not in st.session_state:
    st.session_state.price_history = {}

if "ws_threads" not in st.session_state:
    st.session_state.ws_threads = {}

# Asset options
ASSETS = {
    "bitcoin": "Bitcoin (BTC)",
}

st.title("📈 Live crypto price (demo)")
st.caption("Streaming live tick prices from CoinCap's WebSocket API.")

# Asset selection
asset_id = st.selectbox("Choose asset to track:", list(ASSETS.keys()), format_func=lambda k: ASSETS[k])
asset_label = ASSETS[asset_id]

# Ensure price list exists
if asset_id not in st.session_state.price_history:
    st.session_state.price_history[asset_id] = []

# Seed from REST API only if empty
def seed_price_once(asset):
    if st.session_state.price_history[asset]:
        return
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": asset, "vs_currencies": "usd"},
            timeout=5
        )
        resp.raise_for_status()
        price = resp.json()[asset]["usd"]
        st.session_state.price_history[asset].append({
            "time": datetime.datetime.utcnow(),
            "price": price
        })
    except Exception as e:
        st.warning(f"⚠️ Could not seed price via REST: {e}")

# WebSocket
def start_ws_for_asset(asset):
    if asset in st.session_state.ws_threads:
        return

    def on_message(ws, message):
        data = json.loads(message)
        price = float(data.get("priceUsd", 0))
        if price > 0:
            st.session_state.price_history[asset].append({
                "time": datetime.datetime.utcnow(),
                "price": price
            })

    def run_ws():
        ws_url = f"wss://ws.coincap.io/prices?assets={asset}"
        ws = websocket.WebSocketApp(ws_url, on_message=on_message)
        ws.run_forever()

    t = threading.Thread(target=run_ws, daemon=True)
    st.session_state.ws_threads[asset] = t
    t.start()

# Start streaming
seed_price_once(asset_id)
start_ws_for_asset(asset_id)

# Plot chart
df = pd.DataFrame(st.session_state.price_history[asset_id])

if not df.empty:
    df = df.sort_values("time")
    latest_price = df["price"].iloc[-1]

    st.metric(f"{asset_label} — latest (USD)", f"${latest_price:,.2f}")

    chart = alt.Chart(df).mark_line().encode(
        x=alt.X("time:T", title="Time"),
        y=alt.Y("price:Q", title="Price (USD)")
    ).properties(width=700, height=400)

    st.altair_chart(chart, use_container_width=True)
else:
    st.write("Connecting... waiting for first data point...")
