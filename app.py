# requirements.txt content:
# streamlit>=1.28.0
# websocket-client>=1.6.0
# pandas>=1.5.0
# plotly>=5.15.0
# requests>=2.31.0

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import time
import requests
from collections import deque
import asyncio
import threading
from threading import Thread
import queue

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
    st.session_state.price_data = deque(maxlen=500)  # Reduced for better performance
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'current_price' not in st.session_state:
    st.session_state.current_price = 0
if 'last_update' not in st.session_state:
    st.session_state.last_update = None
if 'connection_status' not in st.session_state:
    st.session_state.connection_status = "Disconnected"

# Streamlit Cloud compatible WebSocket alternative using REST API with fast polling
class BitcoinPriceStreamer:
    def __init__(self):
        self.apis = [
            {
                'name': 'Binance',
                'url': 'https://api.binance.com/api/v3/ticker/price',
                'params': {'symbol': 'BTCUSDT'},
                'parser': lambda data: float(data['price'])
            },
            {
                'name': 'CoinGecko',
                'url': 'https://api.coingecko.com/api/v3/simple/price',
                'params': {'ids': 'bitcoin', 'vs_currencies': 'usd'},
                'parser': lambda data: float(data['bitcoin']['usd'])
            },
            {
                'name': 'Coinbase', 
                'url': 'https://api.coinbase.com/v2/exchange-rates',
                'params': {'currency': 'BTC'},
                'parser': lambda data: float(data['data']['rates']['USD'])
            }
        ]
        self.current_api = 0
        
    def get_price(self):
        """Get Bitcoin price with API fallback"""
        for attempt in range(len(self.apis)):
            api = self.apis[self.current_api]
            try:
                response = requests.get(
                    api['url'], 
                    params=api['params'], 
                    timeout=3,
                    headers={'User-Agent': 'StreamlitBitcoinTracker/1.0'}
                )
                
                if response.status_code == 200:
                    price = api['parser'](response.json())
                    st.session_state.connection_status = f"Connected ({api['name']})"
                    return price
                else:
                    raise Exception(f"HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"API {api['name']} failed: {e}")
                self.current_api = (self.current_api + 1) % len(self.apis)
                continue
        
        st.session_state.connection_status = "All APIs Failed"
        return None

# Initialize streamer
if 'streamer' not in st.session_state:
    st.session_state.streamer = BitcoinPriceStreamer()

# Sidebar controls
st.sidebar.markdown("## ⚙️ Controls")

# Connection status
if st.session_state.connection_status.startswith("Connected"):
    status_color = "🟢"
else:
    status_color = "🔴"

st.sidebar.markdown(f"**Status:** {status_color} {st.session_state.connection_status}")

# Start/Stop buttons
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("🚀 Start Stream", disabled=st.session_state.is_running):
        st.session_state.is_running = True
        st.rerun()

with col2:
    if st.button("⏹️ Stop Stream", disabled=not st.session_state.is_running):
        st.session_state.is_running = False
        st.rerun()

# Chart settings
st.sidebar.markdown("## 📊 Chart Settings")
time_window = st.sidebar.selectbox(
    "Time Window",
    options=[1, 5, 10, 30],
    index=1,
    format_func=lambda x: f"{x} minutes"
)

chart_style = st.sidebar.selectbox(
    "Chart Style", 
    options=['line', 'bar'],
    index=0
)

refresh_rate = st.sidebar.selectbox(
    "Refresh Rate",
    options=[1, 2, 3, 5],
    index=1,
    format_func=lambda x: f"{x} seconds"
)

# Main header
st.markdown('<h1 class="main-header">₿ Live Bitcoin Price Tracker</h1>', unsafe_allow_html=True)

# Auto-refresh logic for Streamlit Cloud
if st.session_state.is_running:
    # Get new price data
    price = st.session_state.streamer.get_price()
    
    if price is not None:
        timestamp = datetime.now()
        st.session_state.price_data.append({
            'timestamp': timestamp,
            'price': price
        })
        st.session_state.current_price = price
        st.session_state.last_update = timestamp
        
        # Show success message
        st.sidebar.success(f"Updated: ${price:,.2f}")
    else:
        st.sidebar.error("Failed to fetch price")

# Main metrics
if st.session_state.current_price > 0:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if len(st.session_state.price_data) >= 2:
            prev_price = list(st.session_state.price_data)[-2]['price']
            change = st.session_state.current_price - prev_price
            change_pct = (change / prev_price) * 100
            delta = f"{change_pct:+.3f}%"
        else:
            delta = None
            
        st.metric(
            label="Current Price",
            value=f"${st.session_state.current_price:,.2f}",
            delta=delta
        )
    
    with col2:
        if len(st.session_state.price_data) > 1:
            prices = [p['price'] for p in st.session_state.price_data]
            price_change = st.session_state.current_price - prices[-2] if len(prices) >= 2 else 0
            st.metric(
                label="Last Change",
                value=f"${price_change:+.2f}",
                delta=f"{(price_change/prices[-2]*100):+.3f}%" if len(prices) >= 2 and prices[-2] != 0 else "0%"
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

# Price chart
if len(st.session_state.price_data) > 1:
    # Filter data by time window
    cutoff_time = datetime.now() - timedelta(minutes=time_window)
    filtered_data = [
        p for p in st.session_state.price_data 
        if p['timestamp'] >= cutoff_time
    ]
    
    if filtered_data:
        df = pd.DataFrame(filtered_data)
        
        # Calculate price changes for color coding
        df['price_change'] = df['price'].diff()
        df['color'] = df['price_change'].apply(
            lambda x: '#00ff00' if x > 0 else '#ff0000' if x < 0 else '#f7931a'
        )
        
        # Create chart
        fig = go.Figure()
        
        if chart_style == 'line':
            # Line chart with color-coded segments
            for i in range(1, len(df)):
                color = '#00ff00' if df.iloc[i]['price_change'] > 0 else '#ff0000' if df.iloc[i]['price_change'] < 0 else '#f7931a'
                fig.add_trace(go.Scatter(
                    x=df['timestamp'].iloc[i-1:i+1],
                    y=df['price'].iloc[i-1:i+1],
                    mode='lines',
                    line=dict(color=color, width=3),
                    showlegend=False,
                    hovertemplate='<b>%{y:$,.2f}</b><br>%{x}<extra></extra>'
                ))
            
            # Add markers for data points
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                mode='markers',
                marker=dict(size=6, color=df['color'], line=dict(width=1, color='white')),
                showlegend=False,
                hovertemplate='<b>%{y:$,.2f}</b><br>%{x}<extra></extra>'
            ))
            
        elif chart_style == 'bar':
            # Bar chart with color coding based on price movement
            fig.add_trace(go.Bar(
                x=df['timestamp'],
                y=df['price'],
                marker=dict(
                    color=df['color'],
                    line=dict(width=1, color='white')
                ),
                name='BTC Price',
                showlegend=False,
                hovertemplate='<b>%{y:$,.2f}</b><br>%{x}<br><b>Change:</b> %{customdata:+.2f}<extra></extra>',
                customdata=df['price_change'].fillna(0)
            ))
        
        # Update layout
        fig.update_layout(
            title=f'Bitcoin Price - Last {time_window} Minutes ({len(filtered_data)} points)',
            xaxis_title='Time',
            yaxis_title='Price (USD)', 
            height=500,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white'),
            xaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
            yaxis=dict(gridcolor='rgba(128,128,128,0.2)'),
            hovermode='x unified'
        )
        
        # Add legend for colors
        fig.add_annotation(
            x=0.02, y=0.98,
            xref="paper", yref="paper",
            text="🟢 Price Up  🔴 Price Down  🟠 No Change",
            showarrow=False,
            font=dict(size=12, color="white"),
            bgcolor="rgba(0,0,0,0.5)",
            bordercolor="white",
            borderwidth=1
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Recent data table
        if len(filtered_data) > 0:
            st.markdown("## 📋 Recent Prices")
            recent_df = pd.DataFrame(filtered_data[-10:]).iloc[::-1]  # Last 10, reversed
            recent_df['Time'] = recent_df['timestamp'].dt.strftime('%H:%M:%S')
            recent_df['Price (USD)'] = recent_df['price'].apply(lambda x: f"${x:,.2f}")
            
            # Add price change column with colors
            recent_df['Change'] = recent_df['price'].diff().fillna(0)
            recent_df['Change ($)'] = recent_df['Change'].apply(
                lambda x: f"+${x:.2f}" if x > 0 else f"${x:.2f}" if x < 0 else "$0.00"
            )
            recent_df['Trend'] = recent_df['Change'].apply(
                lambda x: "🟢 ↗" if x > 0 else "🔴 ↘" if x < 0 else "🟠 →"
            )
            
            st.dataframe(
                recent_df[['Time', 'Price (USD)', 'Change ($)', 'Trend']],
                use_container_width=True,
                hide_index=True
            )

else:
    if st.session_state.is_running:
        st.info("🔄 Collecting data... Please wait for price updates...")
    else:
        st.info("🔄 Click 'Start Stream' to begin tracking Bitcoin prices!")

# Status info
if st.session_state.last_update:
    time_since = datetime.now() - st.session_state.last_update
    st.sidebar.info(f"Last update: {time_since.seconds}s ago")

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Data Points:** {len(st.session_state.price_data)}")
st.sidebar.markdown(f"**Refresh Rate:** {refresh_rate}s")

# Auto refresh when running
if st.session_state.is_running:
    time.sleep(refresh_rate)
    st.rerun()

# Footer
st.markdown("---")
st.markdown(
    f"**Data Sources:** Binance, CoinGecko, Coinbase APIs | "
    f"**Refresh Rate:** {refresh_rate}s | **Built with:** Streamlit"
)
