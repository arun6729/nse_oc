import streamlit as st
import requests
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import pandas as pd
import sqlite3
import os

DB_FILE = "nse_data.db"

def init_sqlite_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nse_options_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                total_ce_oi INTEGER,
                ce_change_pct REAL,
                total_pe_oi INTEGER,
                pe_change_pct REAL,
                pcr REAL,
                diff_ce_pe INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Failed to initialize SQLite Database: {e}")

# Initialize local SQLite DB on startup
init_sqlite_db()

def insert_to_sqlite(symbol, record):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        date_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        
        cursor.execute("""
            INSERT INTO nse_options_data (
                date, time, symbol, total_ce_oi, ce_change_pct, total_pe_oi, pe_change_pct, pcr, diff_ce_pe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date_str,
            record.get("Time", ""),
            symbol,
            record.get("Total CE OI", 0),
            record.get("% CE Change", 0.0),
            record.get("Total PE OI", 0),
            record.get("% PE Change", 0.0),
            record.get("PCR", 0.0),
            record.get("Total CE OI", 0) - record.get("Total PE OI", 0)
        ))
        conn.commit()
        conn.close()
        return True, "Success"
    except Exception as e:
        return False, str(e)

def fetch_from_sqlite_historical(symbol, date_str):
    try:
        if not os.path.exists(DB_FILE):
            return []
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                date, time, symbol, 
                total_ce_oi, ce_change_pct, 
                total_pe_oi, pe_change_pct, 
                pcr, diff_ce_pe 
            FROM nse_options_data 
            WHERE symbol = ? AND date = ? 
            ORDER BY time ASC
        """, (symbol.upper(), date_str))
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for r in rows:
            result.append({
                "date": r["date"],
                "time": r["time"],
                "symbol": r["symbol"],
                "total_ce_oi": r["total_ce_oi"],
                "ce_change_pct": r["ce_change_pct"],
                "total_pe_oi": r["total_pe_oi"],
                "pe_change_pct": r["pe_change_pct"],
                "pcr": r["pcr"],
                "diff_ce_pe": r["diff_ce_pe"]
            })
        return result
    except Exception as e:
        st.error(f"SQLite Read Error: {e}")
        return []

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

def fetch_historical_data(symbol, date_str):
    # Try Supabase first if configured
    data = None
    if "supabase" in st.secrets:
        url = st.secrets["supabase"].get("url", "")
        key = st.secrets["supabase"].get("key", "")
        if url and key and url != "YOUR_SUPABASE_URL" and key != "YOUR_SUPABASE_ANON_KEY":
            data = fetch_from_supabase_historical(symbol, date_str)
            
    # If no data or not configured, load from local SQLite
    if not data:
        data = fetch_from_sqlite_historical(symbol, date_str)
        
    return data

def load_today_history(symbol):
    """Load today's already-saved records from SQLite/Supabase to initialize the session state history."""
    if symbol not in st.session_state.history or not st.session_state.history[symbol]:
        today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        historical_records = fetch_historical_data(symbol, today_str)
        
        session_history = []
        if historical_records:
            for r in historical_records:
                session_history.append({
                    "Time": r.get("time", ""),
                    "Symbol": r.get("symbol", ""),
                    "Total CE OI": r.get("total_ce_oi", 0),
                    "% CE Change": r.get("ce_change_pct", 0.0),
                    "Total PE OI": r.get("total_pe_oi", 0),
                    "% PE Change": r.get("pe_change_pct", 0.0),
                    "PCR": r.get("pcr", 0.0)
                })
        st.session_state.history[symbol] = session_history

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
col1, col2, col3 = st.columns(3)
with col1:
    symbol = st.selectbox("Select Index Symbol", ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
with col2:
    selected_date = st.date_input("Select Date", value=datetime.now(ZoneInfo("Asia/Kolkata")).date())

is_historical = selected_date < datetime.now(ZoneInfo("Asia/Kolkata")).date()

with col3:
    if is_historical:
        hist_timeframe = st.selectbox("Historical Timeframe", ["All Data", "5 Min", "15 Min"])
        timeframe = "Manual" # Force manual for historical mode
    else:
        timeframe = st.selectbox("Select Refresh Timeframe", ["Manual", "3 Min", "5 Min", "15 Min"])

# Pre-populate session state history from SQLite/Supabase for today's selected symbol
if symbol not in st.session_state.history:
    st.session_state.history[symbol] = []
if not is_historical:
    load_today_history(symbol)

# General Settings Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    bypass_market_hours = st.checkbox(
        "Bypass Market Hours", 
        value=False, 
        help="Bypass the trading hours restriction (9:15 AM - 3:30 PM IST) to fetch and test the automatic refresh timer anytime."
    )

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

# Database Configuration Sidebar
with st.sidebar:
    st.header("🗄️ Database Storage")
    
    # SQLite local DB (Always Active)
    st.success("💾 SQLite Local DB: Active (nse_data.db)")
    
    # Supabase cloud DB (Optional Setup)
    if "supabase" not in st.secrets or "url" not in st.secrets["supabase"] or "key" not in st.secrets["supabase"] or st.secrets["supabase"]["url"] == "YOUR_SUPABASE_URL":
        st.info("☁️ Supabase Cloud: Not configured.")
        with st.expander("How to Setup Cloud Sync"):
            st.markdown("""
            1. Create a project on [Supabase](https://supabase.com/).
            2. Go to the SQL Editor and run this query to create the table:
            ```sql
            create table nse_options_data (
              id bigint generated by default as identity primary key,
              date date not null,
              time text not null,
              symbol text not null,
              total_ce_oi bigint,
              ce_change_pct numeric,
              total_pe_oi bigint,
              pe_change_pct numeric,
              pcr numeric,
              diff_ce_pe bigint,
              created_at timestamp with time zone default timezone('utc'::text, now()) not null
            );
            ```
            3. Add your credentials to `.streamlit/secrets.toml`:
            ```toml
            [supabase]
            url = "YOUR_SUPABASE_URL"
            key = "YOUR_SUPABASE_ANON_KEY"
            ```
            """)
    else:
        st.success("☁️ Supabase Cloud: Configured & Syncing")

def insert_to_supabase(symbol, record):
    if "supabase" not in st.secrets:
        return False, "Not Configured"
    url = st.secrets["supabase"].get("url", "")
    key = st.secrets["supabase"].get("key", "")
    if not url or not key:
        return False, "Not Configured"
        
    try:
        date_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        
        data = {
            "date": date_str,
            "time": record.get("Time", ""),
            "symbol": symbol,
            "total_ce_oi": record.get("Total CE OI", 0),
            "ce_change_pct": record.get("% CE Change", 0),
            "total_pe_oi": record.get("Total PE OI", 0),
            "pe_change_pct": record.get("% PE Change", 0),
            "pcr": record.get("PCR", 0),
            "diff_ce_pe": record.get("Total CE OI", 0) - record.get("Total PE OI", 0)
        }
        
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        endpoint = f"{url}/rest/v1/nse_options_data"
        response = requests.post(endpoint, headers=headers, json=data, timeout=5)
        
        if response.status_code in (200, 201):
            return True, "Success"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
            
    except Exception as e:
        return False, str(e)

def fetch_from_supabase_historical(symbol, date_str):
    if "supabase" not in st.secrets:
        return None
    url = st.secrets["supabase"].get("url", "")
    key = st.secrets["supabase"].get("key", "")
    if not url or not key:
        return None
        
    try:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        
        endpoint = f"{url}/rest/v1/nse_options_data?symbol=eq.{symbol}&date=eq.{date_str}&select=*&order=time.asc"
        response = requests.get(endpoint, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def style_df(df):
    """
    Format and style the DataFrame with premium styling and colors.
    Positive values are colored green, negative values red.
    """
    if df.empty:
        return df
        
    df_clean = df.copy()
    
    # Calculate derived columns if they don't exist
    if "Total CE OI" in df_clean.columns and "Total PE OI" in df_clean.columns:
        if "Chg in CE" not in df_clean.columns:
            df_clean["Chg in CE"] = df_clean["Total CE OI"].diff().fillna(0).astype(int)
        if "Chg in PE" not in df_clean.columns:
            df_clean["Chg in PE"] = df_clean["Total PE OI"].diff().fillna(0).astype(int)
        if "Diff of Chg (CE - PE)" not in df_clean.columns:
            df_clean["Diff of Chg (CE - PE)"] = df_clean["Chg in CE"] - df_clean["Chg in PE"]
        if "Diff (CE - PE)" not in df_clean.columns:
            df_clean["Diff (CE - PE)"] = df_clean["Total CE OI"] - df_clean["Total PE OI"]
            
    # Reorder columns to a perfect layout
    desired_cols = [
        'Time', 'Symbol', 
        'Total CE OI', 'Chg in CE', '% CE Change', 
        'Total PE OI', 'Chg in PE', '% PE Change', 
        'PCR', 'Diff (CE - PE)', 'Diff of Chg (CE - PE)'
    ]
    existing_cols = [c for c in desired_cols if c in df_clean.columns]
    for c in df_clean.columns:
        if c not in existing_cols:
            existing_cols.append(c)
    df_clean = df_clean[existing_cols]
    
    # We will use pandas styler to format and color
    styler = df_clean.style
    
    # Define color function based on cell values
    def get_color(val):
        try:
            num = float(val)
            if num > 0:
                return 'color: #00C853; font-weight: bold;'
            elif num < 0:
                return 'color: #FF4B4B; font-weight: bold;'
        except (ValueError, TypeError):
            pass
        return 'color: #E0E0E0;'

    # Apply colors to change columns
    change_cols = ['Chg in CE', '% CE Change', 'Chg in PE', '% PE Change', 'Diff of Chg (CE - PE)']
    cols_to_color = [c for c in change_cols if c in df_clean.columns]
    
    if cols_to_color:
        if hasattr(styler, 'map'):
            styler = styler.map(get_color, subset=cols_to_color)
        else:
            styler = styler.applymap(get_color, subset=cols_to_color)
            
    # Format functions for clean display
    format_dict = {}
    if "Total CE OI" in df_clean.columns:
        format_dict["Total CE OI"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""
    if "Total PE OI" in df_clean.columns:
        format_dict["Total PE OI"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""
    if "Diff (CE - PE)" in df_clean.columns:
        format_dict["Diff (CE - PE)"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""
    if "PCR" in df_clean.columns:
        format_dict["PCR"] = lambda x: f"{x:.4f}" if pd.notna(x) else ""
        
    # Formatting for change columns to have standard +, - and emoji signs
    if "Chg in CE" in df_clean.columns:
        format_dict["Chg in CE"] = lambda x: f"+{int(x):,} 🟢" if x > 0 else (f"{int(x):,} 🔴" if x < 0 else "0 ⚪")
    if "Chg in PE" in df_clean.columns:
        format_dict["Chg in PE"] = lambda x: f"+{int(x):,} 🟢" if x > 0 else (f"{int(x):,} 🔴" if x < 0 else "0 ⚪")
    if "Diff of Chg (CE - PE)" in df_clean.columns:
        format_dict["Diff of Chg (CE - PE)"] = lambda x: f"+{int(x):,} 🟢" if x > 0 else (f"{int(x):,} 🔴" if x < 0 else "0 ⚪")
        
    if "% CE Change" in df_clean.columns:
        format_dict["% CE Change"] = lambda x: f"+{x:.2f}% 🟢" if x > 0 else (f"{x:.2f}% 🔴" if x < 0 else "0.00% ⚪")
    if "% PE Change" in df_clean.columns:
        format_dict["% PE Change"] = lambda x: f"+{x:.2f}% 🟢" if x > 0 else (f"{x:.2f}% 🔴" if x < 0 else "0.00% ⚪")
        
    styler = styler.format(format_dict)
    return styler

def render_historical_data(symbol, selected_date, timeframe):
    st.write(f"### 🕰️ Historical Data for {symbol} on {selected_date}")
    
    with st.spinner(f"Fetching historical data..."):
        date_str = selected_date.strftime("%Y-%m-%d")
        data = fetch_historical_data(symbol, date_str)
        
    if not data:
        st.warning(f"No historical data found for {symbol} on {date_str} in either local SQLite or Supabase database.")
        return
        
    df = pd.DataFrame(data)
    if df.empty:
        st.warning(f"No records found for {symbol} on {date_str}.")
        return
        
    # Rename columns to match existing table
    rename_map = {
        "time": "Time",
        "symbol": "Symbol",
        "total_ce_oi": "Total CE OI",
        "ce_change_pct": "% CE Change",
        "total_pe_oi": "Total PE OI",
        "pe_change_pct": "% PE Change",
        "pcr": "PCR",
        "diff_ce_pe": "Diff (CE - PE)"
    }
    df = df.rename(columns=rename_map)
    
    if timeframe in ["5 Min", "15 Min"]:
        # Resampling logic
        df['datetime_str'] = df['date'] + ' ' + df['Time']
        df['datetime'] = pd.to_datetime(df['datetime_str'], errors='coerce')
        df.set_index('datetime', inplace=True)
        
        resample_str = '5min' if timeframe == "5 Min" else '15min'
        
        # Resample logic (last in window)
        df_resampled = df.resample(resample_str).last().dropna(subset=['Total CE OI'])
        
        if df_resampled.empty:
            st.warning("No data left after resampling.")
            return
            
        df = df_resampled.reset_index()
        
    styled_df = style_df(df)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # Render Historical Trend Charts
    if not df.empty and len(df) > 1:
        chart_df = df.copy()
        if "Time" in chart_df.columns and "Total CE OI" in chart_df.columns and "Total PE OI" in chart_df.columns:
            chart_df = chart_df.set_index("Time")
            st.markdown("### 📈 Open Interest (OI) Trend Analysis")
            st.line_chart(chart_df[["Total CE OI", "Total PE OI"]], height=300)
            
            if "PCR" in chart_df.columns:
                st.markdown("### 📊 Put-Call Ratio (PCR) Trend")
                st.line_chart(chart_df["PCR"], height=200)

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

def render_data(bypass_market=False):
    is_open, msg = is_market_open()
    if not is_open and not bypass_market:
        with data_placeholder.container():
            st.warning(f"⚠️ {msg}")
            
            # If we have history, still want to show the last known data for context
            if symbol in st.session_state.history and len(st.session_state.history[symbol]) > 0:
                st.markdown("### 📊 Historical Data Updates (Last session)")
                df = pd.DataFrame(st.session_state.history[symbol])
                styled_df = style_df(df)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
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
            
            # --- SQLite & Supabase Dispatch ---
            sqlite_success, sqlite_msg = insert_to_sqlite(symbol, new_record)
            sb_success, sb_msg = insert_to_supabase(symbol, new_record)
            
            status_text = []
            if sqlite_success:
                status_text.append("💾 Local SQLite synced")
            else:
                status_text.append(f"💾 SQLite Error: {sqlite_msg}")
                
            if sb_success:
                status_text.append("☁️ Supabase synced")
            elif sb_msg != "Not Configured":
                status_text.append(f"☁️ Supabase Error: {sb_msg}")
                
            st.session_state[f"sync_status_{symbol}"] = " | ".join(status_text)
            
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
            st.info(f"⚙️ **Sync Status:** `{st.session_state.get(f'sync_status_{symbol}', '💾 Local SQLite synced')}`")
            
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
            styled_df = style_df(df)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

            # Render Live Trend Charts
            if not df.empty and len(df) > 1:
                chart_df = df.copy()
                if "Time" in chart_df.columns and "Total CE OI" in chart_df.columns and "Total PE OI" in chart_df.columns:
                    chart_df = chart_df.set_index("Time")
                    st.markdown("### 📈 Open Interest (OI) Trend Analysis")
                    st.line_chart(chart_df[["Total CE OI", "Total PE OI"]], height=300)
                    
                    if "PCR" in chart_df.columns:
                        st.markdown("### 📊 Put-Call Ratio (PCR) Trend")
                        st.line_chart(chart_df["PCR"], height=200)

# Render initial data or manual refresh
if is_historical:
    if st.button("🔄 Reload Historical Data"):
        render_historical_data(symbol, selected_date, hist_timeframe)
    else:
        render_historical_data(symbol, selected_date, hist_timeframe)
else:
    if st.button("🔄 Refresh Data manually"):
        render_data(bypass_market=bypass_market_hours)
    else:
        # Initial render
        render_data(bypass_market=bypass_market_hours)

# Handle Auto-refresh timeframe logic
if not is_historical and timeframe != "Manual":
    if timeframe == "3 Min":
        interval = 3 * 60
    elif timeframe == "5 Min":
        interval = 5 * 60
    elif timeframe == "15 Min":
        interval = 15 * 60
        
    is_open, _ = is_market_open()
    if not is_open and not bypass_market_hours:
        # If market closed, poll less frequently to save resources, but keep alive
        interval = max(interval, 5 * 60)
        
    # We will show a nice countdown widget in the sidebar
    countdown_placeholder = st.sidebar.empty()
    
    # Run the countdown
    for remaining in range(interval, 0, -1):
        mins, secs = divmod(remaining, 60)
        countdown_placeholder.markdown(
            f"""
            <div style="background-color: #1E1E2E; padding: 15px; border-radius: 8px; border: 1px solid #3E3E5E; text-align: center; margin-top: 15px;">
                <span style="font-size: 0.9rem; color: #B0B0C0; display: block; margin-bottom: 5px;">⏱️ Next Auto-Refresh</span>
                <span style="font-size: 1.8rem; font-weight: bold; color: #00C853; font-family: monospace;">{mins:02d}:{secs:02d}</span>
            </div>
            """, 
            unsafe_allow_html=True
        )
        time.sleep(1)
        
    st.rerun()
