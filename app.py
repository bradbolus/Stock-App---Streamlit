# requirements.txt content:
# streamlit>=1.28.0
# websocket-client>=1.6.0
# pandas>=1.5.0
# plotly>=5.15.0
# asyncio-compat
# threading

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
import threading
import time
import queue
import websocket
from collections import deque

# Page configuration
st.set_page_config(
    page_title="Live Bitcoin Price Tracker",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #f7931a;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-container {
        background: linear-gradient(90deg, #1f1f1f, #2d2d2d);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .stMetric > label {
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'price_data' not in st.session_state:
    st.session_state.price_data = deque(maxlen=1000)  # Keep last 1000 points
if 'ws_connected' not in st.session_state:
    st.session_state.ws_connected = False
if 'current_price' not in st.session_state:
    st.session_state.current_price = 0
if 'price_change_24h' not in st.session_state:
    st.session_state.price_change_24h = 0
if 'price_queue' not in st.session_state:
    st.session_state.price_queue = queue.Queue()

class BitcoinWebSocket:
    def __init__(self, price_queue):
        self.price_queue = price_queue
        self.ws = None
        self.running = False
        
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            
            # Handle different WebSocket message formats
            if 'c' in data:  # Binance format
                price = float(data['c'])
            elif 'price' in data:  # Generic format
                price = float(data['price'])
            elif isinstance(data, dict) and 'data' in data:
                price = float(data['data']['price'])
            else:
                return
                
            timestamp = datetime.now()
            
            # Put price data in queue for main thread
            self.price_queue.put({
                'timestamp': timestamp,
                'price': price
            })
            
        except Exception as e:
            st.error(f"Error processing message: {e}")
    
    def on_error(self, ws, error):
        st.error(f"WebSocket error: {error}")
        
    def on_close(self, ws, close_status_code, close_msg):
        st.session_state.ws_connected = False
        
    def on_open(self, ws):
        st.session_state.ws_connected = True
        # Subscribe to Bitcoin price updates (Binance format)
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": ["btcusdt@ticker"],
            "id": 1
        }
        ws.send(json.dumps(subscribe_message))
    
    def start_connection(self):
        self.running = True
        try:
            # Using Binance WebSocket (free and reliable)
            websocket.enableTrace(False)
            self.ws = websocket.WebSocketApp(
                "wss://stream.binance.com:9443/ws/btcusdt@ticker",
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            self.ws.run_forever()
        except Exception as e:
            st.error(f"WebSocket connection failed: {e}")
            self.running = False
    
    def stop_connection(self):
        self.running = False
        if self.ws:
            self.ws.close()

# Alternative WebSocket implementation for multiple exchanges
class MultiExchangeWebSocket:
    def __init__(self, price_queue):
        self.price_queue = price_queue
        self.exchanges = {
            'binance': {
                'url': 'wss://stream.binance.com:9443/ws/btcusdt@ticker',
                'subscribe': None,  # Auto-subscribes
                'parser': lambda data: float(json.loads(data)['c'])
            },
            'coinbase': {
                'url': 'wss://ws-feed.pro.coinbase.com',
                'subscribe': {
                    "type": "subscribe",
                    "channels": [{"name": "ticker", "product_ids": ["BTC-USD"]}]
                },
                'parser': lambda data: float(json.loads(data)['price']) if 'price' in json.loads(data) else None
            }
        }
        self.active_ws = None
        
    def connect_to_exchange(self, exchange_name):
        config = self.exchanges[exchange_name]
        
        def on_message(ws, message):
            try:
                price = config['parser'](message)
                if price:
                    self.price_queue.put({
                        'timestamp': datetime.now(),
                        'price': price,
                        'exchange': exchange_name
                    })
            except:
                pass
        
        def on_open(ws):
            st.session_state.ws_connected = True
            if config['subscribe']:
                ws.send(json.dumps(config['subscribe']))
        
        def on_close(ws, close_status_code, close_msg):
            st.session_state.ws_connected = False
        
        self.active_ws = websocket.WebSocketApp(
            config['url'],
            on_open=on_open,
            on_message=on_message,
            on_close=on_close
        )
        
        return self.active_ws

# Function to start WebSocket in thread
def start_websocket_thread():
    if 'ws_thread' not in st.session_state or not st.session_state.ws_thread.is_alive():
        ws_client = BitcoinWebSocket(st.session_state.price_queue)
        st.session_state.ws_thread = threading.Thread(target=ws_client.start_connection, daemon=True)
        st.session_state.ws_client = ws_client
        st.session_state.ws_thread.start()

# Function to process price queue
def process_price_updates():
    updated = False
    while not st.session_state.price_queue.empty():
        try:
            price_data = st.session_state.price_queue.get_nowait()
            st.session_state.price_data.append(price_data)
            st.session_state.current_price = price_data['price']
            updated = True
        except queue.Empty:
            break
    return updated

# Sidebar controls
st.sidebar.markdown("## ⚙️ Controls")

# WebSocket connection status
connection_status = "🟢 Connected" if st.session_state.ws_connected else "🔴 Disconnected"
st.sidebar.markdown(f"**Status:** {connection_status}")

# Start/Stop WebSocket
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("🚀 Start Stream"):
        start_websocket_thread()
        st.success("WebSocket started!")

with col2:
    if st.button("⏹️ Stop Stream"):
        if 'ws_client' in st.session_state:
            st.session_state.ws_client.stop_connection()
        st.session_state.ws_connected = False
        st.success("WebSocket stopped!")

# Chart settings
st.sidebar.markdown("## 📊 Chart Settings")
time_window = st.sidebar.selectbox(
    "Time Window",
    options=[1, 5, 10, 30, 60],
    index=2,
    format_func=lambda x: f"{x} minutes"
)

chart_style = st.sidebar.selectbox(
    "Chart Style",
    options=['line', 'candlestick', 'area'],
    index=0
)

auto_refresh = st.sidebar.checkbox("Auto Refresh (1s)", value=True)

# Main header
st.markdown('<h1 class="main-header">₿ Live Bitcoin Price Tracker</h1>', unsafe_allow_html=True)

# Process any new price updates
process_price_updates()

# Main metrics row
if st.session_state.current_price > 0:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Current Price",
            value=f"${st.session_state.current_price:,.2f}",
            delta=f"{st.session_state.price_change_24h:.2f}%"
        )
    
    with col2:
        if len(st.session_state.price_data) > 1:
            price_change = st.session_state.current_price - st.session_state.price_data[-2]['price']
            st.metric(
                label="Last Change",
                value=f"${price_change:.2f}",
                delta=f"{(price_change/st.session_state.price_data[-2]['price']*100):.3f}%"
            )
    
    with col3:
        if len(st.session_state.price_data) > 0:
            prices = [p['price'] for p in st.session_state.price_data]
            st.metric(
                label="Session High",
                value=f"${max(prices):,.2f}"
            )
    
    with col4:
        if len(st.session_state.price_data) > 0:
            prices = [p['price'] for p in st.session_state.price_data]
            st.metric(
                label="Session Low", 
                value=f"${min(prices):,.2f}"
            )

# Main chart
if len(st.session_state.price_data) > 1:
    # Filter data based on time window
    cutoff_time = datetime.now() - timedelta(minutes=time_window)
    filtered_data = [p for p in st.session_state.price_data if p['timestamp'] >= cutoff_time]
    
    if filtered_data:
        df = pd.DataFrame(filtered_data)
        
        # Create chart based on selected style
        if chart_style == 'line':
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                mode='lines+markers',
                name='BTC Price',
                line=dict(color='#f7931a', width=3),
                marker=dict(size=6)
            ))
        
        elif chart_style == 'area':
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                fill='tonexty',
                name='BTC Price',
                line=dict(color='#f7931a'),
                fillcolor='rgba(247, 147, 26, 0.3)'
            ))
        
        # Update layout
        fig.update_layout(
            title=f'Bitcoin Price - Last {time_window} Minutes',
            xaxis_title='Time',
            yaxis_title='Price (USD)',
            height=500,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white')
        )
        
        fig.update_xaxis(gridcolor='rgba(128,128,128,0.3)')
        fig.update_yaxis(gridcolor='rgba(128,128,128,0.3)')
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Data table
        st.markdown("## 📋 Recent Price Data")
        display_df = df.tail(10).copy()
        display_df['timestamp'] = display_df['timestamp'].dt.strftime('%H:%M:%S')
        display_df['price'] = display_df['price'].apply(lambda x: f"${x:,.2f}")
        st.dataframe(display_df.iloc[::-1], use_container_width=True)

else:
    st.info("🔄 Waiting for price data... Click 'Start Stream' to begin!")

# Auto-refresh
if auto_refresh and st.session_state.ws_connected:
    time.sleep(1)
    st.rerun()

# Footer
st.markdown("---")
st.markdown(
    "**Data Source:** Binance WebSocket API | **Refresh Rate:** ~1 second | "
    "**Built with:** Streamlit + WebSocket"
)
