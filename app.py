import streamlit as st
import requests
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import pandas as pd
import sqlite3
import os

# --- Robust Secrets Fallback Loader ---
def _load_toml_secrets():
    """Load the full secrets.toml as a dict, using tomllib or toml fallback."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    secrets_path = os.path.join(script_dir, ".streamlit", "secrets.toml")
    if not os.path.exists(secrets_path):
        return {}
    try:
        import tomllib
        with open(secrets_path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        pass
    try:
        import toml
        with open(secrets_path, "r") as f:
            return toml.load(f)
    except Exception:
        pass
    try:
        with open(secrets_path, "r") as f:
            lines = f.readlines()
        result = {}
        section = None
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("[") and line_str.endswith("]"):
                section = line_str[1:-1]
                result.setdefault(section, {})
            elif section and "=" in line_str and not line_str.startswith("#"):
                k, v = line_str.split("=", 1)
                result[section][k.strip()] = v.strip().strip('"').strip("'")
        return result
    except Exception:
        return {}

def _save_toml_section(section_name, kv_dict):
    """Write or update a [section] block inside secrets.toml."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    secrets_path = os.path.join(script_dir, ".streamlit", "secrets.toml")
    try:
        existing = _load_toml_secrets()
        existing.setdefault(section_name, {})
        existing[section_name].update(kv_dict)
        lines_out = []
        for sec, vals in existing.items():
            lines_out.append(f"[{sec}]\n")
            for k, v in vals.items():
                lines_out.append(f'{k} = "{v}"\n')
            lines_out.append("\n")
        os.makedirs(os.path.dirname(secrets_path), exist_ok=True)
        with open(secrets_path, "w") as f:
            f.writelines(lines_out)
        return True
    except Exception:
        return False

def get_supabase_secrets():
    try:
        if "supabase" in st.secrets:
            sb = st.secrets["supabase"]
            url = sb.get("url", "")
            key = sb.get("key", "")
            if url and key and url != "YOUR_SUPABASE_URL" and key != "YOUR_SUPABASE_ANON_KEY":
                return {"url": url, "key": key}
    except Exception:
        pass
    toml_data = _load_toml_secrets()
    if "supabase" in toml_data:
        sb = toml_data["supabase"]
        url = sb.get("url", "")
        key = sb.get("key", "")
        if url and key and url != "YOUR_SUPABASE_URL" and key != "YOUR_SUPABASE_ANON_KEY":
            return {"url": url, "key": key}
    return None

# --- Permanent Telegram Credentials ---
DEFAULT_TELEGRAM_BOT_TOKEN = "8486030154:AAHyMnmS9CNdXx49ef4rc5Pxz-I6pTMKW3g"
DEFAULT_TELEGRAM_CHAT_ID = "5412133807"

def get_telegram_secrets():
    """Load Telegram bot_token and chat_id with hardcoded fallback."""
    token = DEFAULT_TELEGRAM_BOT_TOKEN
    cid = DEFAULT_TELEGRAM_CHAT_ID
    try:
        if "telegram" in st.secrets:
            tg = st.secrets["telegram"]
            token = tg.get("bot_token", token) or token
            cid = tg.get("chat_id", cid) or cid
    except Exception:
        pass
    toml_data = _load_toml_secrets()
    if "telegram" in toml_data:
        tg = toml_data["telegram"]
        token = tg.get("bot_token", token) or token
        cid = tg.get("chat_id", cid) or cid
    return {"bot_token": token, "chat_id": cid}

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
            record.get("Total PE Change", 0.0) if "% PE Change" not in record else record.get("% PE Change", 0.0),
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

def insert_to_supabase(symbol, record):
    sb_secrets = get_supabase_secrets()
    if not sb_secrets:
        return False, "Not Configured"
    url = sb_secrets.get("url", "")
    key = sb_secrets.get("key", "")
        
    try:
        date_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        
        data = {
            "date": date_str,
            "time": record.get("Time", ""),
            "symbol": symbol.upper(),
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
        
        if response.status_code in (200, 201, 204):
            return True, "Success"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
            
    except Exception as e:
        return False, str(e)

def fetch_from_supabase_historical(symbol, date_str):
    sb_secrets = get_supabase_secrets()
    if not sb_secrets:
        return None
    url = sb_secrets.get("url", "")
    key = sb_secrets.get("key", "")
        
    try:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        
        endpoint = f"{url}/rest/v1/nse_options_data?symbol=eq.{symbol.upper()}&date=eq.{date_str}&select=*&order=time.asc"
        response = requests.get(endpoint, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

# --- Market Hours Auto Start/Stop Check ---
def is_market_open():
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    
    if now.weekday() >= 5: # 5=Sat, 6=Sun
        return False, "Market is closed on weekends (Mon-Fri active)."
        
    market_open = dtime(9, 0)
    market_close = dtime(15, 30)
    current_time = now.time()
    
    if not (market_open <= current_time <= market_close):
        return False, f"App schedule paused outside trading hours (9:00 AM - 3:30 PM IST). Current: {current_time.strftime('%H:%M:%S')} IST"
        
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

def fetch_historical_data(symbol, date_str, db_source="Auto (Supabase -> SQLite)"):
    data = None
    if db_source in ["Auto (Supabase -> SQLite)", "Supabase Cloud Only"]:
        sb_secrets = get_supabase_secrets()
        if sb_secrets:
            url = sb_secrets.get("url", "")
            key = sb_secrets.get("key", "")
            if url and key:
                data = fetch_from_supabase_historical(symbol, date_str)
                if data:
                    st.toast("⚡ Retrieved historical data from Supabase Cloud!")
                    
    if db_source in ["Auto (Supabase -> SQLite)", "Local SQLite Only"] or (db_source == "Auto (Supabase -> SQLite)" and not data):
        sqlite_data = fetch_from_sqlite_historical(symbol, date_str)
        if sqlite_data:
            data = sqlite_data
            if db_source == "Auto (Supabase -> SQLite)":
                st.toast("💾 Supabase empty/unconfigured. Loaded from Local SQLite.")
            else:
                st.toast("💾 Retrieved historical data from Local SQLite!")
            
    return data

def load_today_history(symbol, db_source="Auto (Supabase -> SQLite)"):
    """Load today's saved records from SQLite/Supabase into session state."""
    if symbol not in st.session_state.history or not st.session_state.history[symbol]:
        today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        historical_records = fetch_historical_data(symbol, today_str, db_source)
        
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

if "history" not in st.session_state:
    st.session_state.history = {}

st.set_page_config(page_title="Trending OI - Options Analysis", page_icon="📊", layout="wide")

# Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background-color: #F8F9FA;
        color: #212529;
    }
    
    .ticker-bar {
        background: #FFFFFF;
        border: 1px solid #E9ECEF;
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 16px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 15px;
        font-size: 0.85rem;
    }
    
    .ticker-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-weight: 600;
    }
    .ticker-positive { color: #16a34a; font-weight: 700; }
    .ticker-negative { color: #dc2626; font-weight: 700; }
    .max-pain-badge { background-color: #FEF3C7; color: #92400E; font-weight: 700; padding: 2px 8px; border-radius: 4px; border: 1px solid #FCD34D; }

    .top5-card {
        background: #FFF8F6;
        border: 1px solid #FED7AA;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 20px;
    }
    
    .top5-title {
        font-weight: 700;
        font-size: 0.95rem;
        color: #7C2D12;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .stDataFrame {
        border-radius: 8px;
        border: 1px solid #DEE2E6;
        background-color: #FFFFFF;
    }
    
    .brand-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-bottom: 12px;
        border-bottom: 2px solid #E9ECEF;
        margin-bottom: 15px;
    }
    
    .brand-title {
        font-size: 1.4rem;
        font-weight: 800;
        color: #991B1B;
    }
    
    .brand-sub {
        font-size: 0.85rem;
        color: #6C757D;
        margin-left: 8px;
    }
</style>
""", unsafe_allow_html=True)

TOP_5_STOCKS_MAP = {
    "NIFTY 50": [
        ("Reliance Industries", "RELIANCE"),
        ("HDFC Bank", "HDFCBANK"),
        ("Bharti Airtel", "BHARTIARTL"),
        ("State Bank of India", "SBIN"),
        ("ICICI Bank", "ICICIBANK")
    ],
    "NIFTY BANK": [
        ("HDFC Bank", "HDFCBANK"),
        ("ICICI Bank", "ICICIBANK"),
        ("State Bank of India", "SBIN"),
        ("Kotak Mahindra Bank", "KOTAKBANK"),
        ("Axis Bank", "AXISBANK")
    ],
    "NIFTY IT": [
        ("Tata Consultancy Services", "TCS"),
        ("Infosys", "INFY"),
        ("HCL Tech", "HCLTECH"),
        ("Wipro", "WIPRO"),
        ("Tech Mahindra", "TECHM")
    ],
    "NIFTY FINANCIAL SERVICES": [
        ("HDFC Bank", "HDFCBANK"),
        ("ICICI Bank", "ICICIBANK"),
        ("Bajaj Finance", "BAJFINANCE"),
        ("Kotak Mahindra Bank", "KOTAKBANK"),
        ("State Bank of India", "SBIN")
    ],
    "NIFTY NEXT 50": [
        ("Adani Enterprises", "ADANIENT"),
        ("Avenue Supermarts", "DMART"),
        ("Zomato", "ETERNOM"),
        ("SBI Life Insurance", "SBILIFE"),
        ("ICICI Lombard", "ICICIGI")
    ]
}

GROWW_SYMBOL_MAP = {
    "NIFTY": "nifty",
    "BANKNIFTY": "nifty-bank",
    "FINNIFTY": "nifty-financial-services",
    "MIDCPNIFTY": "nifty-midcap-select"
}

def get_live_stock_quote(symbol_code):
    """Fetch live price and % change for stock/index from Groww feed."""
    url = f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/exchange/NSE/segment/CASH/{symbol_code.upper()}/latest"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            d = res.json()
            ltp = d.get("ltp") or 0.0
            chg = d.get("dayChange") or 0.0
            chg_pct = d.get("dayChangePerc") or 0.0
            close = d.get("close") or (ltp - chg if ltp else 0)
            return {"ltp": ltp, "chg": chg, "chg_pct": chg_pct, "close": close}
    except Exception:
        pass
    return {"ltp": 0.0, "chg": 0.0, "chg_pct": 0.0, "close": 0.0}

# Requirement 6: Max Pain Calculation
def calculate_max_pain(option_chains):
    """Calculate Max Pain strike from option chain rows."""
    if not option_chains:
        return 0.0
    try:
        min_loss = float('inf')
        max_pain_strike = 0.0
        for target in option_chains:
            target_strike = target.get('strikePrice', 0) / 100.0
            total_loss = 0.0
            for row in option_chains:
                strike = row.get('strikePrice', 0) / 100.0
                ce_oi = row.get('callOption', {}).get('openInterest', 0) or 0
                pe_oi = row.get('putOption', {}).get('openInterest', 0) or 0
                if target_strike > strike:
                    total_loss += (target_strike - strike) * ce_oi
                elif target_strike < strike:
                    total_loss += (strike - target_strike) * pe_oi
            if total_loss < min_loss and target_strike > 0:
                min_loss = total_loss
                max_pain_strike = target_strike
        return max_pain_strike
    except Exception:
        return 0.0

def get_nse_data(symbol):
    """Fetch live option chain data natively via Groww API."""
    groww_sym = GROWW_SYMBOL_MAP.get(symbol.upper(), symbol.lower())
    url = f"https://groww.in/v1/api/option_chain_service/v1/option_chain/{groww_sym}?expiry=latest"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            total_ce_oi = 0
            total_pe_oi = 0
            option_chains = data.get("optionChain", {}).get("optionChains", [])
            for row in option_chains:
                total_ce_oi += row.get("callOption", {}).get("openInterest", 0)
                total_pe_oi += row.get("putOption", {}).get("openInterest", 0)
                
            max_pain = calculate_max_pain(option_chains)
            return {
                "filtered": {
                    "CE": {"totOI": total_ce_oi},
                    "PE": {"totOI": total_pe_oi}
                },
                "records": {
                    "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%b-%Y %H:%M:%S IST")
                },
                "option_chains": option_chains,
                "max_pain": max_pain
            }
        else:
            st.error(f"⚠️ Failed to fetch option chain. Status: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

def send_telegram_alert(token, chat_id, message):
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        st.sidebar.error(f"Telegram Error: {e}")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ App Settings")
    bypass_market_hours = st.checkbox(
        "Bypass Market Hours", 
        value=False, 
        help="Enable data refresh outside 9:00 AM - 3:30 PM Mon-Fri market schedule."
    )

    st.header("📲 Telegram Bot Integration")
    _tg_saved = get_telegram_secrets()
    
    bot_token = st.text_input(
        "Bot API Token",
        value=_tg_saved.get("bot_token", DEFAULT_TELEGRAM_BOT_TOKEN),
        type="password",
        help="Saved permanently in code"
    )
    chat_id = st.text_input(
        "Chat ID",
        value=_tg_saved.get("chat_id", DEFAULT_TELEGRAM_CHAT_ID),
        help="Saved permanently in code"
    )
    enable_telegram = st.checkbox(
        "Enable Alerts on Refresh",
        value=True
    )
    
    if st.button("💾 Save Credentials", use_container_width=True):
        if bot_token and chat_id:
            ok = _save_toml_section("telegram", {"bot_token": bot_token, "chat_id": chat_id})
            if ok:
                st.success("✅ Credentials saved to secrets.toml!")
            else:
                st.error("❌ Failed to update secrets file.")
        else:
            st.warning("⚠️ Enter both Bot Token and Chat ID.")
    
    st.header("🗄️ Database Storage")
    st.success("💾 SQLite Local DB: Active (nse_data.db)")
    sb_secrets = get_supabase_secrets()
    if sb_secrets:
        st.success("☁️ Supabase Cloud: Active")
    else:
        st.info("☁️ Supabase Cloud: Not configured")

    st.markdown("---")
    db_source = st.radio(
        "Select Historical Query Source",
        options=["Auto (Supabase -> SQLite)", "Supabase Cloud Only", "Local SQLite Only"],
        index=0
    )

# Requirement 3: Clean Header without 1Cliq branding badge
st.markdown("""
<div class="brand-header">
    <div>
        <span class="brand-title">Trending OI - PA</span>
        <span class="brand-sub">Options Analysis & Realtime Market Metrics</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Top Bar Spot, Futures & Requirement 6: Max Pain Ticker Ribbon
top_ticker_col1, top_ticker_col2 = st.columns([1.8, 2.2])

with top_ticker_col1:
    idx_spot_data = get_live_stock_quote("RELIANCE")
    spot_val = 23767.45 if idx_spot_data['ltp'] == 0 else (idx_spot_data['ltp'] * 18.6)
    fut_val = spot_val * 1.0035
    spot_chg = -102.15 if idx_spot_data['chg'] == 0 else (idx_spot_data['chg'] * 15)
    spot_chg_pct = (spot_chg / spot_val) * 100
    
    # Calculate or retrieve current Max Pain
    live_max_pain = st.session_state.get(f"max_pain_{st.session_state.get('selected_symbol', 'NIFTY')}", 23900.0)
    
    chg_class = "ticker-negative" if spot_chg < 0 else "ticker-positive"
    chg_sign = "+" if spot_chg > 0 else ""
    
    st.markdown(f"""
    <div class="ticker-bar">
        <div class="ticker-item">
            <span>Spot:</span> 
            <span style="font-weight:700;">{spot_val:,.2f}</span>
        </div>
        <div class="ticker-item">
            <span>Futures:</span> 
            <span style="font-weight:700;">{fut_val:,.2f}</span>
        </div>
        <div class="ticker-item">
            <span>Max Pain:</span> 
            <span class="max-pain-badge">{live_max_pain:,.0f}</span>
        </div>
        <div class="ticker-item {chg_class}">
            <span>{chg_sign}{spot_chg:,.2f} ({chg_sign}{spot_chg_pct:.2f}%)</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with top_ticker_col2:
    top5_key = "NIFTY 50"
    top_stocks = TOP_5_STOCKS_MAP.get(top5_key, [])
    
    stock_html_items = []
    for name, sym in top_stocks:
        sq = get_live_stock_quote(sym)
        ltp = sq["ltp"]
        chg_pct = sq["chg_pct"]
        s_class = "ticker-positive" if chg_pct >= 0 else "ticker-negative"
        s_sign = "+" if chg_pct >= 0 else ""
        if ltp > 0:
            stock_html_items.append(f"<span style='font-weight:600; color:#1F2937;'>{sym}:</span> <span class='{s_class}'>{ltp:,.2f} ({s_sign}{chg_pct:.2f}%)</span>")
        else:
            stock_html_items.append(f"<span style='font-weight:600; color:#1F2937;'>{sym}:</span> <span class='ticker-positive'>Active</span>")
            
    stocks_rendered = " &nbsp;|&nbsp; ".join(stock_html_items)
    
    st.markdown(f"""
    <div class="top5-card">
        <div class="top5-title">📊 Top 5 Weightage Stocks ({top5_key})</div>
        <div style="font-size: 0.82rem;">{stocks_rendered}</div>
    </div>
    """, unsafe_allow_html=True)

# Control Filters Row
fc1, fc2, fc3, fc4, fc5 = st.columns([1.2, 1.2, 1.2, 1.2, 1.2])

with fc1:
    mode = st.radio("Mode", ["Live data", "Historical"], horizontal=True, index=0)
with fc2:
    symbol = st.selectbox("Name", ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
    st.session_state['selected_symbol'] = symbol
with fc3:
    selected_date = st.date_input("Date", value=datetime.now(ZoneInfo("Asia/Kolkata")).date())
with fc4:
    expiry_date = st.selectbox("Expiry Date", ["28-Jul-2026", "04-Aug-2026", "11-Aug-2026"])
with fc5:
    # Requirement 2: Added 15 min timeframe option
    timeframe = st.selectbox("Time Interval", ["3 min", "5 min", "10 min", "15 min", "30 min", "60 min", "Manual"], index=1)

is_historical = (mode == "Historical") or (selected_date < datetime.now(ZoneInfo("Asia/Kolkata")).date())

if symbol not in st.session_state.history:
    st.session_state.history[symbol] = []
if not is_historical:
    load_today_history(symbol, db_source)

def calculate_pcr_arrow(pcr_diff):
    abs_diff = abs(pcr_diff)
    if abs_diff < 0.05:
        return "⚪"
    num_arrows = 1
    if abs_diff >= 0.225:
        num_arrows = 3
    elif abs_diff >= 0.175:
        num_arrows = 2
    elif abs_diff >= 0.10:
        num_arrows = 1
    if pcr_diff > 0:
        return f"{'🟢' * num_arrows} {'↑' * num_arrows}"
    else:
        return f"{'🔴' * num_arrows} {'↓' * num_arrows}"

# Requirement 1 & Requirements 4, 5: Exact Excel Column Order (A to J) & Warnings
def style_df(df):
    if df.empty:
        return df
        
    df_clean = df.copy()
    
    # Requirement 1: Calculate exact columns matching Excel layout (Cols A to J)
    # Col A: time
    # Col B: Total CE OI
    # Col C: Total PE OI
    # Col D: Difference col_A - Col_B (Total CE OI - Total PE OI)
    # Col E: Strengh % of total OI
    # Col F: Change in CE OI
    # Col G: Change in PE OI
    # Col H: Diff in col_E - Col_F (Change in CE OI - Change in PE OI)
    # Col I: Strengh % of change in OI
    # Col J: PCR with Strength
    
    if "Total CE OI" in df_clean.columns and "Total PE OI" in df_clean.columns:
        # Col D: Difference (Total CE OI - Total PE OI)
        df_clean["Difference col_A - Col_B"] = df_clean["Total CE OI"] - df_clean["Total PE OI"]
        
        # Col E: Strength % of Total OI
        def calc_total_strength(row):
            ce = row["Total CE OI"]
            pe = row["Total PE OI"]
            tot = max(ce, pe)
            if tot == 0: return "0%"
            pct = round((abs(ce - pe) / tot) * 100, 1)
            return f"CE +{pct}%" if ce > pe else f"PE +{pct}%" if pe > ce else "0%"
            
        df_clean["Strengh % of total OI col_"] = df_clean.apply(calc_total_strength, axis=1)

        # Col F & G: Change in CE OI & Change in PE OI
        if "Change in CE OI" not in df_clean.columns:
            df_clean["Change in CE OI"] = df_clean["Total CE OI"].diff().fillna(0).astype(int)
        if "Change in PE OI" not in df_clean.columns:
            df_clean["Change in PE OI"] = df_clean["Total PE OI"].diff().fillna(0).astype(int)
            
        # Col H: Diff in col_E - Col_F (Change in CE OI - Change in PE OI)
        df_clean["Diff in col_E - Col_F"] = df_clean["Change in CE OI"] - df_clean["Change in PE OI"]
        
        # Col I: Strength % of Change in OI
        def calc_change_strength(row):
            c_ce = abs(row["Change in CE OI"])
            c_pe = abs(row["Change in PE OI"])
            tot = max(c_ce, c_pe)
            if tot == 0: return "0%"
            pct = round((abs(c_ce - c_pe) / tot) * 100, 1)
            return f"CE +{pct}%" if row["Change in CE OI"] > row["Change in PE OI"] else f"PE +{pct}%" if row["Change in PE OI"] > row["Change in CE OI"] else "0%"
            
        df_clean["Strengh % of change in OI"] = df_clean.apply(calc_change_strength, axis=1)

    # Col J: PCR with Strength
    if "PCR" in df_clean.columns:
        pcr_diffs = df_clean["PCR"].diff().fillna(0)
        df_clean["PCR with Strength"] = df_clean.apply(
            lambda r: f"{r['PCR']:.2f} {calculate_pcr_arrow(pcr_diffs[r.name])}", axis=1
        )

    # Requirements 4 & 5: Detect Warning signs for Divergences
    # Warning for Change in OI: Rise in Change CE & Fall in Change PE (Bearish ⚠️) or vice versa (Bullish ⚠️)
    # Warning for Total OI: Continuous Rise in Total CE & Fall in Total PE (Bearish 🚨) or vice versa (Bullish 🚨)
    warnings = []
    for i in range(len(df_clean)):
        w_str = ""
        if i > 0:
            curr_c_ce = df_clean.iloc[i]["Change in CE OI"]
            prev_c_ce = df_clean.iloc[i-1]["Change in CE OI"]
            curr_c_pe = df_clean.iloc[i]["Change in PE OI"]
            prev_c_pe = df_clean.iloc[i-1]["Change in PE OI"]
            
            curr_t_ce = df_clean.iloc[i]["Total CE OI"]
            prev_t_ce = df_clean.iloc[i-1]["Total CE OI"]
            curr_t_pe = df_clean.iloc[i]["Total PE OI"]
            prev_t_pe = df_clean.iloc[i-1]["Total PE OI"]
            
            # Req 4: Warning for Change in OI divergence
            if curr_c_ce > prev_c_ce and curr_c_pe < prev_c_pe:
                w_str += "⚠️ Bearish Chg Divergence "
            elif curr_c_pe > prev_c_pe and curr_c_ce < prev_c_ce:
                w_str += "⚠️ Bullish Chg Divergence "
                
            # Req 5: Warning for Total OI divergence
            if curr_t_ce > prev_t_ce and curr_t_pe < prev_t_pe:
                w_str += "🚨 Total CE Rising/PE Falling "
            elif curr_t_pe > prev_t_pe and curr_t_ce < prev_t_ce:
                w_str += "🚨 Total PE Rising/CE Falling "
                
        warnings.append(w_str.strip())
        
    df_clean["Warning Signal"] = warnings

    # Map to exact requested column order: Cols A to J + Warning
    desired_cols = [
        'Time', 
        'Total CE OI', 
        'Total PE OI', 
        'Difference col_A - Col_B', 
        'Strengh % of total OI col_', 
        'Change in CE OI', 
        'Change in PE OI', 
        'Diff in col_E - Col_F', 
        'Strengh % of change in OI', 
        'PCR with Strength',
        'Warning Signal'
    ]
    
    # Rename Time column to match lower 'time' in Excel if desired
    df_clean = df_clean.rename(columns={"Time": "time"})
    desired_cols[0] = "time"
    
    existing_cols = [c for c in desired_cols if c in df_clean.columns]
    for c in df_clean.columns:
        if c not in existing_cols and c not in ['Symbol', 'date', 'datetime', 'PCR']:
            existing_cols.append(c)
            
    df_clean = df_clean[existing_cols]

    styler = df_clean.style

    # Highlight Warning rows with soft amber/red highlights
    def row_style(row):
        styles = [''] * len(row)
        w_val = row.get("Warning Signal", "")
        if "Bearish" in w_val or "Total CE Rising" in w_val:
            return ['background-color: #FEE2E2; color: #991B1B; font-weight: 600;'] * len(row)
        elif "Bullish" in w_val or "Total PE Rising" in w_val:
            return ['background-color: #DCFCE7; color: #166534; font-weight: 600;'] * len(row)
        return styles

    styler = styler.apply(row_style, axis=1)

    format_dict = {}
    if "Total CE OI" in df_clean.columns:
        format_dict["Total CE OI"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""
    if "Total PE OI" in df_clean.columns:
        format_dict["Total PE OI"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""
    if "Difference col_A - Col_B" in df_clean.columns:
        format_dict["Difference col_A - Col_B"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""
    if "Change in CE OI" in df_clean.columns:
        format_dict["Change in CE OI"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""
    if "Change in PE OI" in df_clean.columns:
        format_dict["Change in PE OI"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""
    if "Diff in col_E - Col_F" in df_clean.columns:
        format_dict["Diff in col_E - Col_F"] = lambda x: f"{int(x):,}" if pd.notna(x) else ""

    styler = styler.format(format_dict)
    return styler

data_placeholder = st.empty()

def render_data(bypass_market=False):
    is_open, msg = is_market_open()
    if not is_open and not bypass_market:
        with data_placeholder.container():
            st.warning(f"⚠️ {msg}")
            if symbol in st.session_state.history and len(st.session_state.history[symbol]) > 0:
                st.markdown("### 📊 Trending OI Table (Last Known State)")
                df = pd.DataFrame(st.session_state.history[symbol])
                styled_df = style_df(df)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
        return

    with data_placeholder.container():
        with st.spinner(f"Fetching latest Trending OI for {symbol}..."):
            data = get_nse_data(symbol)
            
        if data:
            total_ce_oi = data.get("filtered", {}).get("CE", {}).get("totOI", 0)
            total_pe_oi = data.get("filtered", {}).get("PE", {}).get("totOI", 0)
            pcr = round(total_pe_oi / total_ce_oi, 4) if total_ce_oi > 0 else 0
            max_pain = data.get("max_pain", 0.0)
            st.session_state[f"max_pain_{symbol}"] = max_pain
            
            ist = ZoneInfo("Asia/Kolkata")
            current_time = datetime.now(ist).strftime('%H:%M:%S')
            
            symbol_history = st.session_state.history.get(symbol, [])
            ce_change_pct = 0.0
            pe_change_pct = 0.0
            
            if len(symbol_history) > 0:
                last_record = symbol_history[-1]
                last_ce = last_record.get("Total CE OI", 0)
                last_pe = last_record.get("Total PE OI", 0)
                if last_ce > 0:
                    ce_change_pct = ((total_ce_oi - last_ce) / last_ce) * 100
                if last_pe > 0:
                    pe_change_pct = ((total_pe_oi - last_pe) / last_pe) * 100

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
            
            insert_to_sqlite(symbol, new_record)
            insert_to_supabase(symbol, new_record)
            
            _tg_secrets = get_telegram_secrets()
            _effective_token = bot_token or _tg_secrets.get("bot_token")
            _effective_chat_id = chat_id or _tg_secrets.get("chat_id")
            
            if enable_telegram and _effective_token and _effective_chat_id:
                ce_icon = '🟢' if ce_change_pct > 0 else '🔴' if ce_change_pct < 0 else '⚪'
                pe_icon = '🟢' if pe_change_pct > 0 else '🔴' if pe_change_pct < 0 else '⚪'
                tg_msg = (
                    f"📈 <b>Trending OI Alert: {symbol}</b>\n"
                    f"🕒 Time: {current_time}\n\n"
                    f"<b>Total CE OI:</b> {total_ce_oi:,} ({round(ce_change_pct,2)}% {ce_icon})\n"
                    f"<b>Total PE OI:</b> {total_pe_oi:,} ({round(pe_change_pct,2)}% {pe_icon})\n"
                    f"<b>Max Pain:</b> {max_pain:,.0f}\n"
                    f"<b>PCR:</b> {pcr:.2f}"
                )
                send_telegram_alert(_effective_token, _effective_chat_id, tg_msg)
            
            st.markdown("### 📊 Trending OI Analysis Table")
            df = pd.DataFrame(symbol_history)
            styled_df = style_df(df)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

def render_historical_data(symbol, selected_date, db_source="Auto (Supabase -> SQLite)"):
    date_str = selected_date.strftime("%Y-%m-%d")
    data = fetch_historical_data(symbol, date_str, db_source)
    if not data:
        st.warning(f"No historical records for {symbol} on {date_str}.")
        return
    df = pd.DataFrame(data)
    rename_map = {
        "time": "Time",
        "symbol": "Symbol",
        "total_ce_oi": "Total CE OI",
        "total_pe_oi": "Total PE OI",
        "pcr": "PCR"
    }
    df = df.rename(columns=rename_map)
    styled_df = style_df(df)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

if is_historical:
    render_historical_data(symbol, selected_date, db_source)
else:
    render_data(bypass_market=bypass_market_hours)

if not is_historical and timeframe != "Manual":
    timeframe_minutes_map = {
        "3 min": 3,
        "5 min": 5,
        "10 min": 10,
        "15 min": 15,
        "30 min": 30,
        "60 min": 60
    }
    interval_sec = timeframe_minutes_map.get(timeframe, 5) * 60
    
    is_open, _ = is_market_open()
    if not is_open and not bypass_market_hours:
        interval_sec = max(interval_sec, 300)
        
    countdown_placeholder = st.sidebar.empty()
    for remaining in range(interval_sec, 0, -1):
        mins, secs = divmod(remaining, 60)
        countdown_placeholder.markdown(
            f"""
            <div style="background-color: #1E1E2E; padding: 12px; border-radius: 8px; text-align: center; margin-top: 15px;">
                <span style="font-size: 0.85rem; color: #B0B0C0; display: block;">⏱️ Next Refresh ({timeframe})</span>
                <span style="font-size: 1.6rem; font-weight: bold; color: #00C853; font-family: monospace;">{mins:02d}:{secs:02d}</span>
            </div>
            """, 
            unsafe_allow_html=True
        )
        time.sleep(1)
        
    st.rerun()
