import streamlit as st
import threading
import time
import json
import requests
import datetime
import pandas as pd
from websocket import WebSocketApp

# ---------- Configuration ----------
ASSETS = {
    "Bitcoin (BTC)": "bitcoin",
}
REFRESH_SEC = 1
HISTORY_MAX_POINTS = 1800

# ---------- Globals ----------
GLOBAL_PRICE_HISTORY = {}
GLOBAL_THREADS = {}
GLOBAL_LOCK = threading.Lock()

# ---------- Streamlit setup ----------
st.set_page_config(page_title="Live BTC Tracker", layout="wide")
st.title("📈 Live crypto price (demo)")
st.markdown("Streaming live tick prices for Bitcoin from CoinCap's websocket API.")

selected_label = st.selectbox("Choose asset to track:", list(ASSETS.keys()))
asset = ASSETS[selected_label]

col_metric, col_chart = st.columns([1, 4])

# ---------- Helper functions ----------
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

    def on_error(ws, error):
        print("WebSocket error:", error)

    def on_close(ws, close_status_code, close_msg):
        print("WebSocket closed", close_status_code, close_msg)

    def run_ws_forever():
        while True:
            try:
                ws = WebSocketApp(
                    url,
                    on_message=make_on_message(asset_id),
                    on_error=on_error,
                    on_close=on_close
                )
                ws.run_forever()
            except Exception as e:
                print("WS run exception, reconnecting in 5s:", e)
                time.sleep(5)

    t = threading.Thread(target=run_ws_forever, daemon=True)
    GLOBAL_THREADS[asset_id] = t
    t.start()

# ---------- Start/seed the data + WS thread ----------
seed_price_once(asset)
start_ws_for_asset(asset)

# ---------- Live update loop ----------
chart_placeholder = col_chart.empty()
metric_placeholder = col_metric.empty()

while True:
    with GLOBAL_LOCK:
        hist = list(GLOBAL_PRICE_HISTORY.get(asset, []))

    if hist:
        df = pd.DataFrame(hist)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        try:
            df["time_local"] = df["time"].dt.tz_convert("Africa/Johannesburg")
        except Exception:
            df["time_local"] = df["time"]
        df = df.set_index("time_local").sort_index()
        latest_price = df["price"].iloc[-1]

        metric_placeholder.metric(
            label=f"{selected_label} — latest (USD)",
            value=f"${latest_price:,.2f}"
        )
        chart_placeholder.line_chart(df["price"], use_container_width=True)
    else:
        metric_placeholder.write("Connecting...")
        chart_placeholder.write("Waiting for first datapoint...")

    time.sleep(REFRESH_SEC)


