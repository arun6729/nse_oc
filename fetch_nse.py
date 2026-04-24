import sys
import json
from playwright.sync_api import sync_playwright

def get_data(symbol):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--disable-http2'])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()
            page.goto("https://www.nseindia.com/option-chain", timeout=60000, wait_until="commit")
            page.wait_for_timeout(3000)
            
            url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
            data = page.evaluate(f'''async () => {{
                try {{
                    const r = await fetch('{url}');
                    return await r.json();
                }} catch (error) {{
                    return null;
                }}
            }}''')
            browser.close()
            print(json.dumps({"success": True, "data": data}))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        get_data(sys.argv[1])
