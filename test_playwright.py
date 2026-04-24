from playwright.sync_api import sync_playwright

def get_data_playwright(symbol):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # Initial visit to set cookies and get Akamai bypass
        print("Visiting main NSE domain...")
        page.goto("https://www.nseindia.com", timeout=60000)
        page.wait_for_timeout(2000)
        
        # Now fetch data via browser fetch API
        print(f"Fetching API for {symbol}...")
        api_url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        
        data = page.evaluate(f"""async () => {{
            const response = await fetch('{api_url}');
            return await response.json();
        }}""")
        
        browser.close()
        return data

data = get_data_playwright("NIFTY")
if data and "filtered" in data:
    print("CE totOI:", data["filtered"]["CE"]["totOI"])
else:
    print("Data invalid or None:", str(data)[:100])
