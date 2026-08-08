import streamlit as st
import requests
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import pandas as pd
import sqlite3
import os
import json

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

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nse_data.db")

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
                spot_price REAL,
                total_ce_oi INTEGER,
                ce_change_pct REAL,
                total_pe_oi INTEGER,
                pe_change_pct REAL,
                pcr REAL,
                diff_ce_pe INTEGER,
                max_pain REAL,
                otm_metrics TEXT,
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
                date, time, symbol, spot_price, total_ce_oi, ce_change_pct, total_pe_oi, pe_change_pct, pcr, diff_ce_pe, max_pain, otm_metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date_str,
            record.get("time", record.get("Time", "")),
            symbol,
            record.get("spot_price", 0.0),
            record.get("total_ce_oi", record.get("Total CE OI", 0)),
            0.0,
            record.get("total_pe_oi", record.get("Total PE OI", 0)),
            0.0,
            record.get("pcr", record.get("PCR", 0.0)),
            record.get("total_ce_oi", record.get("Total CE OI", 0)) - record.get("total_pe_oi", record.get("Total PE OI", 0)),
            record.get("max_pain", 0.0),
            json.dumps(record.get("otm_metrics", {}))
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
                date, time, symbol, spot_price,
                total_ce_oi, ce_change_pct, 
                total_pe_oi, pe_change_pct, 
                pcr, diff_ce_pe, max_pain, otm_metrics
            FROM nse_options_data 
            WHERE symbol = ? AND date = ? 
            ORDER BY time ASC
        """, (symbol.upper(), date_str))
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for r in rows:
            otm_parsed = {}
            if r["otm_metrics"]:
                try:
                    otm_parsed = json.loads(r["otm_metrics"])
                except Exception:
                    pass
            result.append({
                "date": r["date"],
                "time": r["time"],
                "symbol": r["symbol"],
                "spot_price": r["spot_price"] or 0.0,
                "total_ce_oi": r["total_ce_oi"],
                "total_pe_oi": r["total_pe_oi"],
                "pcr": r["pcr"],
                "diff_ce_pe": r["diff_ce_pe"],
                "max_pain": r["max_pain"] or 0.0,
                "otm_metrics": otm_parsed
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
            "time": record.get("time", record.get("Time", "")),
            "symbol": symbol.upper(),
            "spot_price": record.get("spot_price", 0.0),
            "total_ce_oi": record.get("total_ce_oi", record.get("Total CE OI", 0)),
            "ce_change_pct": 0,
            "total_pe_oi": record.get("total_pe_oi", record.get("Total PE OI", 0)),
            "pe_change_pct": 0,
            "pcr": record.get("pcr", record.get("PCR", 0)),
            "diff_ce_pe": record.get("total_ce_oi", record.get("Total CE OI", 0)) - record.get("total_pe_oi", record.get("Total PE OI", 0)),
            "otm_metrics": json.dumps(record.get("otm_metrics", {}))
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
                st.toast("💾 Loaded from Local SQLite!")
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
                    "Total PE OI": r.get("total_pe_oi", 0),
                    "PCR": r.get("pcr", 0.0),
                    "spot_price": r.get("spot_price", 0.0),
                    "otm_metrics": r.get("otm_metrics", {})
                })
        st.session_state.history[symbol] = session_history

if "history" not in st.session_state:
    st.session_state.history = {}

st.set_page_config(page_title="Trending OI - Options Analysis", page_icon="📊", layout="wide")

# Enhanced Custom Styling matching attached reference UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background-color: #FAFAFA;
        color: #1F2937;
    }

    /* Red accent controls matching reference screenshots */
    .stRadio label { font-weight: 600; color: #7F1D1D; }
    div[data-baseweb="select"] > div {
        border-radius: 6px;
        border: 1.5px solid #FCA5A5 !important;
        background-color: #FFFFFF;
    }

    /* Tabular monospaced numbers & optimal column padding */
    .stDataFrame table {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.88rem !important;
    }
    .stDataFrame td, .stDataFrame th {
        padding: 6px 12px !important;
        text-align: center !important;
    }
    
    .ticker-bar {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 16px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 15px;
        font-size: 0.88rem;
    }
    
    .ticker-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-weight: 600;
    }
    .ticker-positive { color: #16A34A; font-weight: 700; }
    .ticker-negative { color: #DC2626; font-weight: 700; }
    .max-pain-badge { background-color: #FEF3C7; color: #92400E; font-weight: 700; padding: 2px 8px; border-radius: 4px; border: 1px solid #FCD34D; }

    .top5-card {
        background: #FFF5F5;
        border: 1px solid #FECDD3;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 16px;
    }
    
    .top5-title {
        font-weight: 700;
        font-size: 0.90rem;
        color: #991B1B;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .underlying-bar {
        font-size: 0.88rem;
        color: #4B5563;
        text-align: right;
        margin-bottom: 12px;
        font-weight: 500;
    }

    .dlb-badge {
        background-color: #EF4444;
        color: #FFFFFF;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.78rem;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

INDEX_TOP_5_MAP = {
    "NIFTY": [
        ("Reliance", "RELIANCE"),
        ("HDFC Bank", "HDFCBANK"),
        ("Bharti Airtel", "BHARTIARTL"),
        ("ICICI Bank", "ICICIBANK"),
        ("Infosys", "INFY")
    ],
    "BANKNIFTY": [
        ("HDFC Bank", "HDFCBANK"),
        ("ICICI Bank", "ICICIBANK"),
        ("SBI", "SBIN"),
        ("Kotak Bank", "KOTAKBANK"),
        ("Axis Bank", "AXISBANK")
    ],
    "FINNIFTY": [
        ("HDFC Bank", "HDFCBANK"),
        ("ICICI Bank", "ICICIBANK"),
        ("Bajaj Finance", "BAJFINANCE"),
        ("Kotak Bank", "KOTAKBANK"),
        ("SBI", "SBIN")
    ],
    "MIDCPNIFTY": [
        ("Federal Bank", "FEDERALBNK"),
        ("IDFC First", "IDFCFIRSTB"),
        ("Godrej Prop", "GODREJPROP"),
        ("Cummins", "CUMMINSIND"),
        ("Persistent", "PERSISTENT")
    ]
}

GROWW_SYMBOL_MAP = {
    "NIFTY": "nifty",
    "BANKNIFTY": "nifty-bank",
    "FINNIFTY": "nifty-financial-services",
    "MIDCPNIFTY": "nifty-midcap-select"
}

GROWW_CASH_MAP = {
    "NIFTY": "NIFTY50",
    "BANKNIFTY": "NIFTYBANK",
    "FINNIFTY": "FINNIFTY",
    "MIDCPNIFTY": "MIDCPNIFTY"
}

def get_live_stock_quote(symbol_code):
    groww_code = GROWW_CASH_MAP.get(symbol_code.upper(), symbol_code.upper())
    url = f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/exchange/NSE/segment/CASH/{groww_code}/latest"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            d = res.json()
            ltp = d.get("ltp") or 0.0
            chg = d.get("dayChange") or 0.0
            chg_pct = d.get("dayChangePerc") or 0.0
            return {"ltp": ltp, "chg": chg, "chg_pct": chg_pct}
    except Exception:
        pass
    return {"ltp": 0.0, "chg": 0.0, "chg_pct": 0.0}

def calculate_max_pain(option_chains):
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
    groww_sym = GROWW_SYMBOL_MAP.get(symbol.upper(), symbol.lower())
    url = f"https://groww.in/v1/api/option_chain_service/v1/option_chain/{groww_sym}?expiry=latest"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            total_ce_oi = 0
            total_pe_oi = 0
            option_chains = data.get("optionChain", {}).get("optionChains", [])
            for row in option_chains:
                total_ce_oi += row.get("callOption", {}).get("openInterest", 0) or 0
                total_pe_oi += row.get("putOption", {}).get("openInterest", 0) or 0
                
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
            st.error(f"⚠️ Option chain fetch status: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

def extract_otm_metrics(option_chains, spot_price, step=50):
    if not option_chains or spot_price <= 0:
        return {}
    atm_strike = int(round(spot_price / step) * step)
    sorted_chains = sorted(option_chains, key=lambda x: x.get("strikePrice", 0))
    
    otm_ce_strikes = [atm_strike + (2 * step), atm_strike + (4 * step), atm_strike + (6 * step)]
    otm_pe_strikes = [atm_strike - (2 * step), atm_strike - (4 * step), atm_strike - (6 * step)]
    
    metrics = {
        "atm_strike": atm_strike,
        "ce_2_otm": {"strike": otm_ce_strikes[0], "oi": 0, "chg_oi": 0, "vol": 0},
        "ce_4_otm": {"strike": otm_ce_strikes[1], "oi": 0, "chg_oi": 0, "vol": 0},
        "ce_6_otm": {"strike": otm_ce_strikes[2], "oi": 0, "chg_oi": 0, "vol": 0},
        "pe_2_otm": {"strike": otm_pe_strikes[0], "oi": 0, "chg_oi": 0, "vol": 0},
        "pe_4_otm": {"strike": otm_pe_strikes[1], "oi": 0, "chg_oi": 0, "vol": 0},
        "pe_6_otm": {"strike": otm_pe_strikes[2], "oi": 0, "chg_oi": 0, "vol": 0},
    }
    
    strike_map = {int(row.get("strikePrice", 0)/100): row for row in sorted_chains}
    for key, stk in [("ce_2_otm", otm_ce_strikes[0]), ("ce_4_otm", otm_ce_strikes[1]), ("ce_6_otm", otm_ce_strikes[2])]:
        r = strike_map.get(stk)
        if r:
            c = r.get("callOption", {})
            oi = c.get("openInterest", 0) or 0
            prev_oi = c.get("prevOpenInterest", 0) or 0
            metrics[key] = {"strike": stk, "oi": oi, "chg_oi": oi - prev_oi, "vol": c.get("volume", 0) or 0}
            
    for key, stk in [("pe_2_otm", otm_pe_strikes[0]), ("pe_4_otm", otm_pe_strikes[1]), ("pe_6_otm", otm_pe_strikes[2])]:
        r = strike_map.get(stk)
        if r:
            p = r.get("putOption", {})
            oi = p.get("openInterest", 0) or 0
            prev_oi = p.get("prevOpenInterest", 0) or 0
            metrics[key] = {"strike": stk, "oi": oi, "chg_oi": oi - prev_oi, "vol": p.get("volume", 0) or 0}
            
    return metrics

def render_otm_tracker_table(history_records, timeframe_str):
    """Req 1, 2, 3: Heading 'OTM Tracker', tracking interval changes, MultiIndex layout with strike price column headers."""
    st.markdown("### 🎯 OTM Tracker")
    if not history_records:
        st.info("No OTM snapshot metrics recorded yet.")
        return
        
    df_raw = pd.DataFrame(history_records)
    resampled = resample_by_interval(df_raw, timeframe_str)
    
    if resampled.empty:
        st.info("No historical intervals recorded.")
        return
        
    # Extract strikes from latest available otm_metrics
    latest_otm = history_records[-1].get("otm_metrics", {})
    if isinstance(latest_otm, str):
        try: latest_otm = json.loads(latest_otm)
        except Exception: latest_otm = {}
        
    spot_val = round(history_records[-1].get("spot_price", 24570.0))
    stk_ce2 = latest_otm.get("otm_ce_2", {}).get("strike", "OTM CE 2 strike")
    stk_ce1 = latest_otm.get("otm_ce_1", {}).get("strike", "OTM CE 1 strike")
    stk_atm_ce = latest_otm.get("atm_ce", {}).get("strike", "ATM CE")
    stk_atm_pe = latest_otm.get("atm_pe", {}).get("strike", "ATM PE")
    stk_pe1 = latest_otm.get("otm_pe_1", {}).get("strike", "OTM PE 1 strike")
    stk_pe2 = latest_otm.get("otm_pe_2", {}).get("strike", "OTM PE 2 strike")
    
    rows = []
    for _, r in resampled.iterrows():
        t_str = r.get("Time", "")
        otm = r.get("otm_metrics", {})
        if isinstance(otm, str):
            try: otm = json.loads(otm)
            except Exception: otm = {}
            
        ce2 = otm.get("otm_ce_2", {})
        ce1 = otm.get("otm_ce_1", {})
        atm_ce = otm.get("atm_ce", {})
        atm_pe = otm.get("atm_pe", {})
        pe1 = otm.get("otm_pe_1", {})
        pe2 = otm.get("otm_pe_2", {})
        
        rows.append({
            ("time", "time"): t_str,
            (f"OTM CE 2 ({stk_ce2})", "total OI"): f"{ce2.get('oi', 0):,}",
            (f"OTM CE 2 ({stk_ce2})", "Change in OI"): f"{ce2.get('chg_oi', 0):,}",
            (f"OTM CE 2 ({stk_ce2})", "Vol"): f"{ce2.get('vol', 0):,}",
            (f"OTM CE 1 ({stk_ce1})", "total OI"): f"{ce1.get('oi', 0):,}",
            (f"OTM CE 1 ({stk_ce1})", "Change in OI"): f"{ce1.get('chg_oi', 0):,}",
            (f"OTM CE 1 ({stk_ce1})", "Vol"): f"{ce1.get('vol', 0):,}",
            (f"ATM CE ({stk_atm_ce})", "total OI"): f"{atm_ce.get('oi', 0):,}",
            (f"ATM CE ({stk_atm_ce})", "Change in OI"): f"{atm_ce.get('chg_oi', 0):,}",
            (f"ATM CE ({stk_atm_ce})", "Vol"): f"{atm_ce.get('vol', 0):,}",
            (f"Spot ({spot_val})", "Spot"): spot_val,
            (f"ATM PE ({stk_atm_pe})", "total OI"): f"{atm_pe.get('oi', 0):,}",
            (f"ATM PE ({stk_atm_pe})", "Change in OI"): f"{atm_pe.get('chg_oi', 0):,}",
            (f"ATM PE ({stk_atm_pe})", "Vol"): f"{atm_pe.get('vol', 0):,}",
            (f"OTM PE 1 ({stk_pe1})", "total OI"): f"{pe1.get('oi', 0):,}",
            (f"OTM PE 1 ({stk_pe1})", "Change in OI"): f"{pe1.get('chg_oi', 0):,}",
            (f"OTM PE 1 ({stk_pe1})", "Vol"): f"{pe1.get('vol', 0):,}",
            (f"OTM PE 2 ({stk_pe2})", "total OI"): f"{pe2.get('oi', 0):,}",
            (f"OTM PE 2 ({stk_pe2})", "Change in OI"): f"{pe2.get('chg_oi', 0):,}",
            (f"OTM PE 2 ({stk_pe2})", "Vol"): f"{pe2.get('vol', 0):,}",
        })
        
    df_multi = pd.DataFrame(rows)
    df_multi.columns = pd.MultiIndex.from_tuples(df_multi.columns)
    st.dataframe(df_multi, use_container_width=True, hide_index=True)

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ App Settings")
    bypass_market_hours = st.checkbox("Bypass Market Hours", value=False)
    
    st.header("⚡ Auto-Start VM/App (Mon-Fri 8:55 AM)")
    st.success("🟢 Active: Windows Task 'TrendingOI_AutoStart_855AM'")

    st.header("🗄️ Database Storage")
    st.success("💾 SQLite Local DB: Active (nse_data.db)")
    sb_secrets = get_supabase_secrets()
    if sb_secrets:
        st.success("☁️ Supabase Cloud: Active")
    else:
        st.info("☁️ Supabase Cloud: Not configured")

    st.markdown("---")
    db_source = st.radio("Select Historical Query Source", options=["Auto (Supabase -> SQLite)", "Supabase Cloud Only", "Local SQLite Only"], index=0)

def style_trending_table(df_in):
    """Req 4: Insert total CE OI and total PE OI columns fetching values from bottom of option chain."""
    if df_in.empty:
        return df_in
        
    cols_order = [
        "Time", "Total CE OI", "Total PE OI", "Day H/L Break", "Chg. In Call OI", "Chg. In Put OI", 
        "Diff. in OI", "Strength", "Direction of chg.", "Chg. In Direction", 
        "Total Call Ltp", "Call Ltp chng.", "CE + PE Ltp Chng.", 
        "Put Ltp chng.", "Total Put Ltp", "Net PCR"
    ]
    
    existing = [c for c in cols_order if c in df_in.columns]
    df_out = df_in[existing].copy()
    
    styler = df_out.style
    
    format_dict = {}
    if "Total CE OI" in df_out.columns: format_dict["Total CE OI"] = lambda x: f"{int(x):,}"
    if "Total PE OI" in df_out.columns: format_dict["Total PE OI"] = lambda x: f"{int(x):,}"
    if "Chg. In Call OI" in df_out.columns: format_dict["Chg. In Call OI"] = lambda x: f"{int(x):,}"
    if "Chg. In Put OI" in df_out.columns: format_dict["Chg. In Put OI"] = lambda x: f"{int(x):,}"
    if "Diff. in OI" in df_out.columns: format_dict["Diff. in OI"] = lambda x: f"{int(x):,}"
    if "Chg. In Direction" in df_out.columns: format_dict["Chg. In Direction"] = lambda x: f"{int(x):,}"
    if "Net PCR" in df_out.columns: format_dict["Net PCR"] = lambda x: f"{float(x):.2f}"
    
    styler = styler.format(format_dict)
    return styler

data_placeholder = st.empty()

def render_dashboard(symbol, timeframe, spot_price_val, bypass_market=False):
    is_open, msg = is_market_open()
    
    with data_placeholder.container():
        if not is_open and not bypass_market:
            st.warning(f"⚠️ {msg}")
            symbol_history = st.session_state.history.get(symbol, [])
            if symbol_history:
                raw_df = pd.DataFrame(symbol_history)
                resampled_df = resample_by_interval(raw_df, timeframe)
                processed_df = calculate_strength_direction(resampled_df)
                
                st.markdown(f"### 📊 Trending OI Table ({timeframe} Interval - Last Recorded)")
                st.dataframe(style_trending_table(processed_df), use_container_width=True, hide_index=True)
                render_otm_tracker_table(symbol_history, timeframe)
            return

        with st.spinner(f"Fetching latest metrics for {symbol}..."):
            data = get_nse_data(symbol)
            
        if data:
            total_ce_oi = data.get("filtered", {}).get("CE", {}).get("totOI", 0)
            total_pe_oi = data.get("filtered", {}).get("PE", {}).get("totOI", 0)
            pcr = round(total_pe_oi / total_ce_oi, 4) if total_ce_oi > 0 else 0
            
            ist = ZoneInfo("Asia/Kolkata")
            current_time = datetime.now(ist).strftime('%H:%M:00')
            
            symbol_history = st.session_state.history.get(symbol, [])

            new_record = {
                "Time": current_time,
                "Symbol": symbol,
                "spot_price": spot_price_val,
                "Total CE OI": total_ce_oi,
                "Total PE OI": total_pe_oi,
                "PCR": pcr,
                "otm_metrics": extract_otm_metrics(data.get("option_chains", []), spot_price_val)
            }
            symbol_history.append(new_record)
            st.session_state.history[symbol] = symbol_history
            
            insert_to_sqlite(symbol, new_record)
            insert_to_supabase(symbol, new_record)
            
            # Resample data based on selected interval dropdown
            raw_df = pd.DataFrame(symbol_history)
            resampled_df = resample_by_interval(raw_df, timeframe)
            processed_df = calculate_strength_direction(resampled_df)
            
            st.markdown(f"### 📊 Trending OI Table ({timeframe} Interval)")
            st.dataframe(style_trending_table(processed_df), use_container_width=True, hide_index=True)
            
            # Render OTM Tracker Table matching attached layout
            render_otm_tracker_table(symbol_history, timeframe)

render_dashboard(symbol=symbol, timeframe=timeframe, spot_price_val=spot_price_val, bypass_market=bypass_market_hours)

if not is_historical and timeframe != "Manual":
    tf_min_map = {"3 min": 3, "5 min": 5, "10 min": 10, "15 min": 15, "30 min": 30, "60 min": 60}
    interval_sec = tf_min_map.get(timeframe, 15) * 60
    
    countdown_placeholder = st.sidebar.empty()
    for remaining in range(interval_sec, 0, -1):
        mins, secs = divmod(remaining, 60)
        countdown_placeholder.markdown(
            f"""
            <div style="background-color: #1E1E2E; padding: 10px; border-radius: 8px; text-align: center; margin-top: 15px;">
                <span style="font-size: 0.80rem; color: #B0B0C0; display: block;">⏱️ Next Dashboard Refresh ({timeframe})</span>
                <span style="font-size: 1.4rem; font-weight: bold; color: #00C853; font-family: monospace;">{mins:02d}:{secs:02d}</span>
            </div>
            """, 
            unsafe_allow_html=True
        )
        time.sleep(1)
        
    st.rerun()

