import streamlit as st
import pandas as pd
import threading
import datetime
import json
from websocket import WebSocketApp
from streamlit_autorefresh import st_autorefresh
import altair as alt

ASSETS = {
    "Bitcoin (BTC)": "bitcoin"
}
WEBSOCKET_URL = "wss://ws.coincap.io/prices?assets={asset_id}"
MAX_POINTS = 300

# Initialize session state
if "price_history" not in st.session_state:
    st.session_state.price_history = {asset_id: [] for asset_id in ASSETS.values()}
if "ws_started" not in st.session_state:
    st.session_state.ws_started = set()

def on_message(ws, message, asset_id):
    try:
        data = json.loads(message)
        if asset_id in data:
            price = float(data[asset_id])
            ts = datetime.datetime.utcnow()
            st.session_state.price_history[asset_id].append(
                {"time": ts, "price": price}
            )
            if len(st.session_state.price_history[asset_id]) > MAX_POINTS:
                st.session_state.price_history[asset_id] = st.session_state.price_history[asset_id][-MAX_POINTS:]
    except Exception as e:
        print(f"Error parsing message: {e}")

def start_ws(asset_id):
    def run():
        ws_url = WEBSOCKET_URL.format(asset_id=asset_id)
        ws = WebSocketApp(ws_url, on_message=lambda ws, msg: on_message(ws, msg, asset_id))
        ws.run_forever()
    threading.Thread(target=run, daemon=True).start()

st.set_page_config(page_title="Live Crypto Price", page_icon="📈")

st.title("📈 Live crypto price")
st.caption("Streaming live tick prices from CoinCap's WebSocket API.")

asset_label = st.selectbox("Choose asset to track:", list(ASSETS.keys()))
asset_id = ASSETS[asset_label]

# Start WebSocket once
if asset_id not in st.session_state.ws_started:
    start_ws(asset_id)
    st.session_state.ws_started.add(asset_id)

st_autorefresh(interval=2000, key="crypto_refresh")

df = pd.DataFrame(st.session_state.price_history[asset_id]).sort_values("time")

if not df.empty:
    latest_price = df["price"].iloc[-1]
    st.metric(f"{asset_label} — latest (USD)", f"${latest_price:,.2f}")

    chart = alt.Chart(df).mark_line().encode(
        x=alt.X("time:T", title="Time"),
        y=alt.Y("price:Q", title="Price (USD)")
    ).properties(width=700, height=400)

    st.altair_chart(chart, use_container_width=True)
else:
    st.write("Connecting... waiting for first data point...")
