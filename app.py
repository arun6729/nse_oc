import streamlit as st
import requests
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import pandas as pd

def is_market_open():
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    
    if now.weekday() >= 5: # 5=Sat, 6=Sun
        return False, "Market is closed on weekends."
        
    market_open = dtime(9, 15)
    market_close = dtime(15, 30)
    current_time = now.time()
    
    if not (market_open <= current_time <= market_close):
        return False, f"Market is closed. Operating hours are 9:15 AM to 3:30 PM. Current time: {current_time.strftime('%H:%M:%S')} IST"
        
    nse_holidays_2026 = {
        "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31",
        "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-28",
        "2026-06-26", "2026-09-14", "2026-10-02", "2026-10-20",
        "2026-11-10", "2026-11-24", "2026-12-25"
    }
    
    current_date_str = now.strftime("%Y-%m-%d")
    if current_date_str in nse_holidays_2026:
        return False, "Market is closed today (NSE Holiday)."
        
    return True, "Market is open."

# Initialize session state for history
if "history" not in st.session_state:
    st.session_state.history = {}

st.set_page_config(page_title="NSE Option Chain Total OI", page_icon="📈", layout="centered")

st.title("📈 NSE Option Chain Total OI Tracker")

# Custom CSS for premium aesthetic
st.markdown("""
<style>
    .metric-card {
        background-color: #1E1E2E;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.2);
        color: #FFFFFF;
        margin-bottom: 20px;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: bold;
        margin: 10px 0;
    }
    .ce-color { color: #FF4B4B; }
    .pe-color { color: #00C853; }
</style>
""", unsafe_allow_html=True)

# User inputs
col1, col2 = st.columns(2)
with col1:
    symbol = st.selectbox("Select Index Symbol", ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
with col2:
    timeframe = st.selectbox("Select Refresh Timeframe", ["Manual", "3 Min", "5 Min", "15 Min"])

# Telegram Configuration Sidebar
with st.sidebar:
    st.header("📲 Telegram Bot Integration")
    st.markdown("Set up Telegram credentials to receive data directly in your chats on every update.")
    bot_token = st.text_input("Bot API Token", type="password", help="Get this from @BotFather")
    chat_id = st.text_input("Chat ID", help="The numeric ID of your chat or channel")
    enable_telegram = st.checkbox("Enable Alerts on Refresh")
    
def send_telegram_alert(token, chat_id, message):
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            st.sidebar.error("Failed to send Telegram message. Check credentials.")
    except Exception as e:
        st.sidebar.error(f"Telegram Error: {e}")

def get_nse_data(symbol):
    """Fetch live option chain data natively via Groww API which provides free unblocked NSE feeds."""
    # Ensure lowercase symbol for Groww API
    symbol = symbol.lower()
    url = f"https://groww.in/v1/api/option_chain_service/v1/option_chain/{symbol}?expiry=latest"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            # Manually sum Open Interest from the option chain
            total_ce_oi = 0
            total_pe_oi = 0
            
            option_chains = data.get("optionChain", {}).get("optionChains", [])
            for row in option_chains:
                total_ce_oi += row.get("callOption", {}).get("openInterest", 0)
                total_pe_oi += row.get("putOption", {}).get("openInterest", 0)
                
            # Normalize to match our original expected layout
            return {
                "filtered": {
                    "CE": {"totOI": total_ce_oi},
                    "PE": {"totOI": total_pe_oi}
                },
                "records": {
                    "timestamp": "Live (Alternative Feed)"
                }
            }
        else:
            st.error(f"⚠️ Failed to fetch data. Status code: {response.status_code}")
            return None
            
    except Exception as e:
        st.error(f"Error fetching data via alternative feed: {e}")
        return None

# Placeholder for data
data_placeholder = st.empty()

def render_data():
    is_open, msg = is_market_open()
    if not is_open:
        with data_placeholder.container():
            st.warning(f"⚠️ {msg}")
            
            # If we have history, still want to show the last known data for context
            if symbol in st.session_state.history and len(st.session_state.history[symbol]) > 0:
                st.markdown("### 📊 Historical Data Updates (Last session)")
                df = pd.DataFrame(st.session_state.history[symbol])
                
                def format_change(val):
                    if val > 0: return f"+{val}% 🟢"
                    elif val < 0: return f"{val}% 🔴"
                    return f"{val}% ⚪"
                    
                formatted_df = df.copy()
                formatted_df["% CE Change"] = formatted_df["% CE Change"].apply(format_change)
                formatted_df["% PE Change"] = formatted_df["% PE Change"].apply(format_change)
                formatted_df["Total CE OI"] = formatted_df["Total CE OI"].apply(lambda x: f"{x:,}")
                formatted_df["Total PE OI"] = formatted_df["Total PE OI"].apply(lambda x: f"{x:,}")
                st.dataframe(formatted_df, use_container_width=True, hide_index=True)
        return

    with data_placeholder.container():
        with st.spinner(f"Fetching latest data for {symbol}..."):
            data = get_nse_data(symbol)
            
        if data:
            total_ce_oi = data.get("filtered", {}).get("CE", {}).get("totOI", 0)
            total_pe_oi = data.get("filtered", {}).get("PE", {}).get("totOI", 0)
            timestamp = data.get("records", {}).get("timestamp", "Unknown")
            
            pcr = round(total_pe_oi / total_ce_oi, 4) if total_ce_oi > 0 else 0
            ist = ZoneInfo("Asia/Kolkata")
            current_time = datetime.now(ist).strftime('%H:%M:%S')
            
            # --- History & % Change calculation ---
            if symbol not in st.session_state.history:
                st.session_state.history[symbol] = []
            
            symbol_history = st.session_state.history[symbol]
            ce_change_pct = 0.0
            pe_change_pct = 0.0
            
            if len(symbol_history) > 0:
                last_record = symbol_history[-1]
                last_ce = last_record["Total CE OI"]
                last_pe = last_record["Total PE OI"]
                if last_ce > 0:
                    ce_change_pct = ((total_ce_oi - last_ce) / last_ce) * 100
                if last_pe > 0:
                    pe_change_pct = ((total_pe_oi - last_pe) / last_pe) * 100
                    
            # Format the columns for visuals & messaging
            def format_change(val):
                if val > 0:
                    return f"+{val}% 🟢"
                elif val < 0:
                    return f"{val}% 🔴"
                return f"{val}% ⚪"

            # Record current fetch
            new_record = {
                "Time": current_time,
                "Symbol": symbol,
                "Total CE OI": total_ce_oi,
                "% CE Change": round(ce_change_pct, 2),
                "Total PE OI": total_pe_oi,
                "% PE Change": round(pe_change_pct, 2),
                "PCR": pcr
            }
            symbol_history.append(new_record)
            st.session_state.history[symbol] = symbol_history
            
            # --- Telegram Dispatch ---
            if enable_telegram and bot_token and chat_id:
                # Need to run formatting on current change just for the message
                ce_icon = '🟢' if ce_change_pct > 0 else '🔴' if ce_change_pct < 0 else '⚪'
                pe_icon = '🟢' if pe_change_pct > 0 else '🔴' if pe_change_pct < 0 else '⚪'
                msg = (
                    f"📈 <b>NSE Update: {symbol}</b>\n"
                    f"🕒 Time: {current_time}\n\n"
                    f"<b>Total CE OI:</b> {total_ce_oi:,} (<i>{round(ce_change_pct,2)}% {ce_icon}</i>)\n"
                    f"<b>Total PE OI:</b> {total_pe_oi:,} (<i>{round(pe_change_pct,2)}% {pe_icon}</i>)\n\n"
                    f"<b>PCR (PE/CE):</b> {pcr}"
                )
                send_telegram_alert(bot_token, chat_id, msg)
            
            # --- Rendering ---
            st.write(f"**Last Updated (NSE Server):** {timestamp}")
            st.write(f"**Local Refresh Time:** {current_time}")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class="metric-card">
                    <div>Total CE OI</div>
                    <div class="metric-value ce-color">{total_ce_oi:,}</div>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class="metric-card">
                    <div>Total PE OI</div>
                    <div class="metric-value pe-color">{total_pe_oi:,}</div>
                </div>
                """, unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class="metric-card">
                    <div>PCR (PE/CE)</div>
                    <div class="metric-value" style="color: {'#00C853' if pcr >= 1 else '#FF4B4B'};">{pcr}</div>
                </div>
                """, unsafe_allow_html=True)
            
            # Show trend info based on PCR
            if pcr > 1:
                st.success(f"PCR is {pcr} (Bullish Bias - More Puts Sold than Calls)")
            elif pcr < 1:
                st.error(f"PCR is {pcr} (Bearish Bias - More Calls Sold than Puts)")
            else:
                st.info(f"PCR is {pcr} (Neutral)")
                
            # Render History Table
            st.markdown("### 📊 Historical Data Updates")
            df = pd.DataFrame(symbol_history)

            
            formatted_df = df.copy()
            formatted_df["% CE Change"] = formatted_df["% CE Change"].apply(format_change)
            formatted_df["% PE Change"] = formatted_df["% PE Change"].apply(format_change)
            formatted_df["Total CE OI"] = formatted_df["Total CE OI"].apply(lambda x: f"{x:,}")
            formatted_df["Total PE OI"] = formatted_df["Total PE OI"].apply(lambda x: f"{x:,}")
            
            st.dataframe(formatted_df, use_container_width=True, hide_index=True)

# Render initial data or manual refresh
if st.button("🔄 Refresh Data manually"):
    render_data()
else:
    # Initial render
    render_data()

# Handle Auto-refresh timeframe logic
if timeframe != "Manual":
    if timeframe == "3 Min":
        interval = 3 * 60
    elif timeframe == "5 Min":
        interval = 5 * 60
    elif timeframe == "15 Min":
        interval = 15 * 60
        
    is_open, _ = is_market_open()
    if not is_open:
        # If market closed, poll less frequently to save resources, but keep alive
        interval = max(interval, 5 * 60)
        
    time.sleep(interval)
    st.rerun()
