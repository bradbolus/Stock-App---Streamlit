import streamlit as st
from streamlit_autorefresh import st_autorefresh
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
    # add more mappings here: "Label": "coincap-id"
}

REFRESH_MS = 1000  # frontend refresh interval (milliseconds)
HISTORY_MAX_POINTS = 1800  # keep up to ~30 minutes at 1s if you like

# ---------- Globals (in-memory) ----------
GLOBAL_PRICE_HISTORY = {}     # { asset_id: [ {time: datetime, price: float}, ... ] }
GLOBAL_THREADS = {}           # { asset_id: Thread }
GLOBAL_LOCK = threading.Lock()

# ---------- Streamlit page setup ----------
st.set_page_config(page_title="Live BTC Tracker", layout="wide")
st.title("📈 Live crypto price (demo)")
st.markdown("This demo uses CoinCap's public WebSocket to stream live tick prices for Bitcoin.")

# lightweight auto-refresh so the page re-runs and picks up new data without blocking
_autorefresh_counter = st_autorefresh(interval=REFRESH_MS, limit=None, key="autorefresh")

selected_label = st.selectbox("Choose asset to track:", list(ASSETS.keys()))
asset = ASSETS[selected_label]

col_metric, col_chart = st.columns([1, 4])

# ---------- Helper functions ----------

def seed_price_once(asset_id: str):
    """Fetch a single price via REST to populate the UI immediately (only if empty)."""
    with GLOBAL_LOCK:
        if GLOBAL_PRICE_HISTORY.get(asset_id):
            return
    try:
        resp = requests.get(f"https://api.coincap.io/v2/assets/{asset_id}", timeout=5)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        price = float(data.get("priceUsd"))
        ts = datetime.datetime.utcnow()
        with GLOBAL_LOCK:
            GLOBAL_PRICE_HISTORY.setdefault(asset_id, []).append({"time": ts, "price": price})
    except Exception as e:
        # don't crash the app for a seed failure
        st.write("⚠️ Could not seed price via REST:", e)


def start_ws_for_asset(asset_id: str):
    """Ensure a background websocket thread is running for the requested asset.

    The thread will reconnect if the connection drops.
    """
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
                ws = WebSocketApp(url,
                                  on_message=make_on_message(asset_id),
                                  on_error=on_error,
                                  on_close=on_close)
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

# ---------- Build dataframe from in-memory buffer ----------
with GLOBAL_LOCK:
    hist = list(GLOBAL_PRICE_HISTORY.get(asset, []))

if hist:
    df = pd.DataFrame(hist)
    # ensure timezone-aware datetimes (assume stored UTC)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    # convert to local timezone (Africa/Johannesburg) for display
    try:
        df["time_local"] = df["time"].dt.tz_convert("Africa/Johannesburg")
    except Exception:
        # fallback: keep UTC timestamps
        df["time_local"] = df["time"]
    df = df.set_index("time_local").sort_index()
    latest_price = df["price"].iloc[-1]
else:
    df = pd.DataFrame(columns=["price"])
    latest_price = None

# ---------- UI ----------
if latest_price is not None:
    # show latest price
    col_metric.metric(label=f"{selected_label} — latest (USD)", value=f"${latest_price:,.2f}")
else:
    col_metric.write("Connecting... (waiting for data)")

# show chart
if not df.empty:
    col_chart.line_chart(df["price"], use_container_width=True)
else:
    col_chart.write("Waiting for first datapoint...")

st.caption("Source: CoinCap websocket (wss://ws.coincap.io/prices) — REST seed via https://api.coincap.io/v2/assets/{id}")

# Helpful debug / info for the user
if st.checkbox("Show raw buffer (debug)"):
    with GLOBAL_LOCK:
        st.write(hist[-20:])

# END

