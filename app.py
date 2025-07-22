import streamlit as st
import pandas as pd
import pandas_ta as ta
import time
import requests
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- Page Configuration ---
st.set_page_config(page_title="Crypto Futures Signal Dashboard", layout="wide")

# --- App Secrets and Configuration ---
# This will try to read from secrets, but falls back to a placeholder if not found.
try:
    DISCORD_WEBHOOK_URL = st.secrets["discord"]["webhook_url"]
except (FileNotFoundError, KeyError):
    st.sidebar.warning("Discord Webhook URL not found in secrets. Notifications will be disabled.", icon="⚠️")
    DISCORD_WEBHOOK_URL = "" # Placeholder

# --- App Constants ---
REFRESH_INTERVAL = 600  # 5 minutes
BINANCE_API_BASE = "https://fapi.binance.com" # Futures API endpoint

# --- UI: Top Level Selectors ---
st.sidebar.title("⚙️ Controls")
selected_tf_label = st.sidebar.selectbox(
    "Select Timeframe for Analysis",
    ("15 minutes", "30 minutes", "1 hour", "4 hours"),
    index=2 # Default to 1 hour
)
TIMEFRAME_MAP = {
    "15 minutes": "15m", "30 minutes": "30m",
    "1 hour": "1h", "4 hours": "4h"
}
selected_tf = TIMEFRAME_MAP[selected_tf_label]

# --- Disclaimer & Title ---
st.title(f'📈 Crypto Futures Signal Dashboard')
st.caption(f"Analyzing Top Binance USDT Futures on the {selected_tf_label} timeframe.")
with st.expander("⚠️ Important Disclaimer & How-To"):
    st.warning(
        """
        **This tool is for informational and educational purposes only. Not Financial Advice.**
        Futures trading is extremely risky. The signals provided are based on technical indicators and are not guaranteed to be accurate. 
        Always conduct your own research and manage your risk.
        """
    )
    st.info("""
    **How to Use This Dashboard:**
    - The main table shows the live trading signals for the top 10 USDT perpetual futures on Binance.
    - Click the `▶` icon next to any coin to expand a detailed view.
    - The detailed view contains an interactive chart and a "Signal Rationale" checklist showing exactly which conditions are met.
    """)

# --- Data Fetching ---
@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner=False)
def get_binance_klines(symbol, interval='1h', limit=100):
    url = f"{BINANCE_API_BASE}/fapi/v1/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        return df.set_index('open_time')
    except requests.exceptions.RequestException:
        return pd.DataFrame()

# --- Top 10 Futures Symbols (Adjust as needed) ---
TOP_10_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT"]

# --- Core Logic ---
def compute_indicators(df):
    if df.empty or len(df) < 21: return None
    df.ta.rsi(close=df['close'], length=14, append=True)
    df.ta.sma(close=df['close'], length=9, append=True)
    df.ta.sma(close=df['close'], length=21, append=True)
    df.rename(columns={'RSI_14': 'RSI', 'SMA_9': 'SMA_9', 'SMA_21': 'SMA_21'}, inplace=True)
    return df

def generate_signal(df):
    if df is None or df.empty: return 'Error'
    latest = df.iloc[-1]
    if any(pd.isna(latest[col]) for col in ['RSI', 'SMA_9', 'SMA_21']): return 'Not Available'
    price, rsi, sma9, sma21 = latest['close'], latest['RSI'], latest['SMA_9'], latest['SMA_21']
    if rsi < 30 and price > sma9 and sma9 > sma21: return 'STRONG BUY'
    if rsi < 40 and price > sma9: return 'BUY'
    if rsi > 70: return 'OVERBOUGHT'
    return 'HOLD'

# --- UI Components ---
def create_detail_chart(df, symbol):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=(f'{symbol} Price Chart', 'RSI'), row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Price'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_9'], mode='lines', name='SMA 9', line=dict(color='cyan', width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_21'], mode='lines', name='SMA 21', line=dict(color='yellow', width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], mode='lines', name='RSI', line=dict(color='white', width=1)), row=2, col=1)
    fig.add_hrect(y0=70, y1=100, line_width=0, fillcolor='red', opacity=0.2, row=2, col=1)
    fig.add_hrect(y0=0, y1=40, line_width=0, fillcolor='green', opacity=0.2, row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1); fig.add_hline(y=40, line_dash="dash", line_color="yellow", row=2, col=1); fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    fig.update_layout(height=400, template='plotly_dark', showlegend=False, margin=dict(l=10, r=10, t=30, b=10))
    fig.update_xaxes(rangeslider_visible=False)
    return fig

def display_signal_rationale(latest):
    price, rsi, sma9, sma21 = latest['close'], latest['RSI'], latest['SMA_9'], latest['SMA_21']
    st.markdown("**Signal Rationale (Conditions for BUY)**")
    cond1_ok = rsi < 40; cond2_ok = price > sma9; cond3_ok = sma9 > sma21
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**RSI < 40**: {'✅' if cond1_ok else '❌'} (Currently: {rsi:.2f})")
        st.markdown(f"**Price > SMA 9**: {'✅' if cond2_ok else '❌'} (P: {price:,.2f}, S9: {sma9:,.2f})")
    with col2:
        st.markdown(f"**SMA 9 > SMA 21**: {'✅' if cond3_ok else '❌'} (S9: {sma9:,.2f}, S21: {sma21:,.2f})")
        st.markdown(f"*(Condition required for STRONG BUY)*")

# --- Discord Notifications ---
def send_buy_signal_notification(coin, signal, price, timeframe):
    """Sends a notification ONLY for BUY or STRONG BUY signals."""
    if "YOUR_DISCORD" in DISCORD_WEBHOOK_URL: return
    color = 3066993 if signal == "BUY" else 5763719 # Cyan for BUY, Green for STRONG BUY
    embed = {
        "title": f"🚀 New Trade Signal: {coin} → {signal}",
        "description": f"A new **{signal}** signal has been detected on the **{timeframe}** timeframe.",
        "color": color,
        "fields": [{"name": "Current Price", "value": f"${price:,.2f}", "inline": True}]
    }
    try: requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    except requests.exceptions.RequestException: pass

def send_heartbeat_notification():
    """Sends a periodic status update to Discord."""
    if "YOUR_DISCORD" in DISCORD_WEBHOOK_URL: return
    embed = {
        "title": "STATUS: Bot is Running",
        "description": f"Data refresh completed at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "color": 3447003,
        "footer": {"text": f"Next refresh in {REFRESH_INTERVAL//60} minutes."}
    }
    try: requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    except requests.exceptions.RequestException: pass

def send_bot_started_notification():
    """Sends a one-time message when the bot starts."""
    if "YOUR_DISCORD" in DISCORD_WEBHOOK_URL: return
    embed = {
        "title": "✅ Bot Started Successfully",
        "description": f"Monitoring has begun on the **{selected_tf_label}** timeframe.",
        "color": 5763719,
        "footer": {"text": f"Checked at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
    }
    try: requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    except requests.exceptions.RequestException: pass

# --- Main App Logic ---
# Initialize session state for tracking signals and startup notification
if 'last_signal' not in st.session_state:
    st.session_state.last_signal = {}
if 'bot_started_notified' not in st.session_state:
    st.session_state.bot_started_notified = False

# Send the startup notification ONLY ONCE per session
if not st.session_state.bot_started_notified:
    send_bot_started_notification()
    st.session_state.bot_started_notified = True

main_placeholder = st.empty()

while True:
    master_df_data = []
    
    with st.spinner(f"Analyzing top futures on the {selected_tf_label} timeframe..."):
        for symbol in TOP_10_SYMBOLS:
            market_df = get_binance_klines(symbol, interval=selected_tf)
            if market_df.empty: continue
            
            indicator_df = compute_indicators(market_df.copy())
            if indicator_df is None: continue
                
            signal = generate_signal(indicator_df)
            latest = indicator_df.iloc[-1]
            price = latest['close']
            
            # --- MODIFIED NOTIFICATION LOGIC ---
            # Only notify if the new signal is a buy signal AND is different from the last one
            if signal in ['BUY', 'STRONG BUY'] and st.session_state.last_signal.get(symbol) != signal:
                send_buy_signal_notification(symbol, signal, price, selected_tf_label)
            
            # Always update the last known signal
            st.session_state.last_signal[symbol] = signal
            
            master_df_data.append({'Coin': symbol, 'Price': price, 'RSI': latest['RSI'], 'Signal': signal, 'Chart': indicator_df})
    
    with main_placeholder.container():
        if not master_df_data:
            st.error("Could not fetch data from Binance. The API might be down or your IP is blocked. Please try again later.")
        else:
            cols = st.columns((2, 2, 2, 2, 8)); cols[0].markdown("**Coin**"); cols[1].markdown("**Price**"); cols[2].markdown("**RSI (14)**"); cols[3].markdown("**Signal**")
            for item in master_df_data:
                cols = st.columns((2, 2, 2, 2, 8))
                cols[0].write(f"**{item['Coin']}**"); cols[1].write(f"${item['Price']:,.2f}"); cols[2].write(f"{item['RSI']:.2f}")
                signal_color = {"BUY": "cyan", "STRONG BUY": "lightgreen", "OVERBOUGHT": "salmon", "HOLD": "gray"}.get(item['Signal'], "white")
                cols[3].markdown(f"<span style='color:{signal_color}; font-weight:bold;'>{item['Signal']}</span>", unsafe_allow_html=True)
                with cols[4].expander("Show Details & Chart"):
                    st.plotly_chart(create_detail_chart(item['Chart'], item['Coin']), use_container_width=True)
                    display_signal_rationale(item['Chart'].iloc[-1])
            
            st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # --- Send Heartbeat and Sleep ---
    send_heartbeat_notification()
    time.sleep(REFRESH_INTERVAL)