import streamlit as st
from streamlit_autorefresh import st_autorefresh
import threading
import time
import json
import requests
import datetime
import pandas as pd
from websocket import WebSocketApp

ASSETS = {
    "Bitcoin (BTC)": "bitcoin",
}
HISTORY_MAX_POINTS = 1800

GLOBAL_PRICE_HISTORY = {}
GLOBAL_THREADS = {}
GLOBAL_LOCK = threading.Lock()

st.set_page_config(page_title="Live BTC Tracker", layout="wide")
st.title("📈 Live crypto price (demo)")
st.markdown("Streaming live tick prices for Bitcoin from CoinCap's websocket API.")

# Auto-refresh every 1 second
st_autorefresh(interval=1000, key="refresh")

selected_label = st.selectbox("Choose asset to track:", list(ASSETS.keys()))
asset = ASSETS[selected_label]

col_metric, col_chart = st.columns([1, 4])

def seed_price_once(asset_id: str):
    with GLOBAL_LOCK:
        if GLOBAL_PRICE_HISTORY.get(asset_id):
            return
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": asset_id, "vs_currencies": "usd"},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        price = float(data[asset_id]["usd"])
        ts = datetime.datetime.utcnow()
        with GLOBAL_LOCK:
            GLOBAL_PRICE_HISTORY.setdefault(asset_id, []).append({"time": ts, "price": price})
    except Exception as e:
        st.write("⚠️ Could not seed price via REST:", e)

def start_ws_for_asset(asset_id: str):
    if GLOBAL_THREADS.get(asset_id) and GLOBAL_THREADS[asset_id].is_alive():
        return

    url = f"wss://ws.coincap.io/prices?assets={asset_id}"

    def make_on_message(asset_id):
        def _on_message(ws, message):
            try:
                payload = json.loads(message)
                if asset_id in payload:
                    price = float(payload[asset_id])
                    ts = datetime.datetime.utcnow()
                    with GLOBAL_LOCK:
                        lst = GLOBAL_PRICE_HISTORY.setdefault(asset_id, [])
                        lst.append({"time": ts, "price": price})
                        if len(lst) > HISTORY_MAX_POINTS:
                            lst.pop(0)
            except Exception as e:
                print("on_message error:", e)
        return _on_message

    def run_ws_forever():
        while True:
            try:
                ws = WebSocketApp(url, on_message=make_on_message(asset_id))
                ws.run_forever()
            except Exception as e:
                print("WS run exception, reconnecting in 5s:", e)
                time.sleep(5)

    t = threading.Thread(target=run_ws_forever, daemon=True)
    GLOBAL_THREADS[asset_id] = t
    t.start()

seed_price_once(asset)
start_ws_for_asset(asset)

with GLOBAL_LOCK:
    hist = list(GLOBAL_PRICE_HISTORY.get(asset, []))

if hist:
    df = pd.DataFrame(hist)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time").sort_index()
    latest_price = df["price"].iloc[-1]
    col_metric.metric(f"{selected_label} — latest (USD)", f"${latest_price:,.2f}")
    col_chart.line_chart(df["price"], use_container_width=True)
else:
    col_metric.write("Connecting...")
    col_chart.write("Waiting for first datapoint...")



