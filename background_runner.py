import time
import datetime
from zoneinfo import ZoneInfo
import sqlite3
import os
import requests
import json

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nse_data.db")

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

def get_supabase_secrets():
    secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
    if not os.path.exists(secrets_path):
        return None
    try:
        import tomllib
        with open(secrets_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("supabase")
    except Exception:
        return None

def init_db():
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

def get_live_quote(symbol):
    groww_sym = GROWW_CASH_MAP.get(symbol.upper(), symbol.upper())
    url = f"https://groww.in/v1/api/stocks_data/v1/tr_live_prices/exchange/NSE/segment/CASH/{groww_sym}/latest"
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

def fetch_groww_oc(symbol):
    groww_sym = GROWW_SYMBOL_MAP.get(symbol.upper(), symbol.lower())
    url = f"https://groww.in/v1/api/option_chain_service/v1/option_chain/{groww_sym}?expiry=latest"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Error fetching OC: {e}")
    return None

def extract_otm_metrics(option_chains, spot_price, step=50):
    if not option_chains or spot_price <= 0:
        return {}
    
    atm_strike = int(round(spot_price / step) * step)
    sorted_chains = sorted(option_chains, key=lambda x: x.get("strikePrice", 0))
    
    # 2 Strikes OTM CE, 1 Strike OTM CE, ATM CE, ATM PE, 1 Strike OTM PE, 2 Strikes OTM PE
    otm_ce_2 = atm_strike + (2 * step)
    otm_ce_1 = atm_strike + (1 * step)
    atm_ce = atm_strike
    atm_pe = atm_strike
    otm_pe_1 = atm_strike - (1 * step)
    otm_pe_2 = atm_strike - (2 * step)
    
    metrics = {
        "spot": spot_price,
        "atm_strike": atm_strike,
        "otm_ce_2": {"strike": otm_ce_2, "oi": 0, "chg_oi": 0, "vol": 0},
        "otm_ce_1": {"strike": otm_ce_1, "oi": 0, "chg_oi": 0, "vol": 0},
        "atm_ce": {"strike": atm_ce, "oi": 0, "chg_oi": 0, "vol": 0},
        "atm_pe": {"strike": atm_pe, "oi": 0, "chg_oi": 0, "vol": 0},
        "otm_pe_1": {"strike": otm_pe_1, "oi": 0, "chg_oi": 0, "vol": 0},
        "otm_pe_2": {"strike": otm_pe_2, "oi": 0, "chg_oi": 0, "vol": 0},
    }
    
    strike_map = {}
    for row in sorted_chains:
        stk = int(row.get("strikePrice", 0) / 100)
        strike_map[stk] = row
        
    for key, target_stk, is_call in [
        ("otm_ce_2", otm_ce_2, True), ("otm_ce_1", otm_ce_1, True), ("atm_ce", atm_ce, True),
        ("atm_pe", atm_pe, False), ("otm_pe_1", otm_pe_1, False), ("otm_pe_2", otm_pe_2, False)
    ]:
        row = strike_map.get(target_stk)
        if row:
            opt = row.get("callOption" if is_call else "putOption", {})
            oi = opt.get("openInterest", 0) or 0
            prev_oi = opt.get("prevOpenInterest", 0) or 0
            vol = opt.get("volume", 0) or 0
            metrics[key] = {"strike": target_stk, "oi": oi, "chg_oi": oi - prev_oi, "vol": vol}

    return metrics

def extract_spot_from_oc(oc_data):
    if not oc_data:
        return 0.0
    try:
        chains = oc_data.get("optionChain", {}).get("optionChains", [])
        if chains and len(chains) > 0:
            row = chains[0]
            spot = row.get("callOption", {}).get("underlyingValue") or row.get("putOption", {}).get("underlyingValue") or 0.0
            if spot > 0:
                return float(spot)
    except Exception:
        pass
    return 0.0

def record_snapshot_for_symbol(symbol):
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.datetime.now(ist)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:00")
    
    quote = get_live_quote(symbol)
    oc_data = fetch_groww_oc(symbol)
    
    if not oc_data:
        return
        
    option_chains = oc_data.get("optionChain", {}).get("optionChains", [])
    total_ce_oi = 0
    total_pe_oi = 0
    
    for row in option_chains:
        total_ce_oi += row.get("callOption", {}).get("openInterest", 0) or 0
        total_pe_oi += row.get("putOption", {}).get("openInterest", 0) or 0
        
    pcr = round(total_pe_oi / total_ce_oi, 4) if total_ce_oi > 0 else 0.0
    spot_price = quote.get("ltp", 0.0)
    if spot_price <= 0:
        spot_price = extract_spot_from_oc(oc_data)
        
    step = 100 if symbol == "BANKNIFTY" else 50
    otm_metrics = extract_otm_metrics(option_chains, spot_price, step=step)
    otm_json = json.dumps(otm_metrics)
    
    # Save into SQLite
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO nse_options_data (
                date, time, symbol, spot_price, total_ce_oi, ce_change_pct, total_pe_oi, pe_change_pct, pcr, diff_ce_pe, max_pain, otm_metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date_str, time_str, symbol.upper(), spot_price, total_ce_oi, 0.0, total_pe_oi, 0.0, pcr, (total_ce_oi - total_pe_oi), 0.0, otm_json
        ))
        conn.commit()
        conn.close()
        print(f"[{time_str}] Recorded {symbol}: CE={total_ce_oi}, PE={total_pe_oi}, Spot={spot_price}")
    except Exception as e:
        print(f"SQLite Write Error: {e}")

    # Save into Supabase if configured
    sb_secrets = get_supabase_secrets()
    if sb_secrets and sb_secrets.get("url") and sb_secrets.get("key"):
        try:
            url = sb_secrets["url"]
            key = sb_secrets["key"]
            headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }
            payload = {
                "date": date_str,
                "time": time_str,
                "symbol": symbol.upper(),
                "spot_price": spot_price,
                "total_ce_oi": total_ce_oi,
                "total_pe_oi": total_pe_oi,
                "pcr": pcr,
                "diff_ce_pe": (total_ce_oi - total_pe_oi),
                "otm_metrics": otm_json
            }
            requests.post(f"{url}/rest/v1/nse_options_data", headers=headers, json=payload, timeout=5)
        except Exception:
            pass

def main():
    init_db()
    symbols = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]
    for s in symbols:
        record_snapshot_for_symbol(s)

if __name__ == "__main__":
    main()
