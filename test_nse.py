import requests

url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
}

# Usually need to hit main page first to get cookies
session = requests.Session()
session.get("https://www.nseindia.com", headers=headers, timeout=10)

response = session.get(url, headers=headers, timeout=10)
print(response.status_code)
if response.status_code == 200:
    data = response.json()
    print("CE totOI:", data["filtered"]["CE"]["totOI"])
    print("PE totOI:", data["filtered"]["PE"]["totOI"])
else:
    print(response.text)
