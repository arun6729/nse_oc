import requests

headers = {
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'DNT': '1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Sec-Fetch-User': '?1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-Mode': 'navigate',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
}

session = requests.Session()
response = session.get("https://www.nseindia.com", headers=headers, timeout=10)
print("Main page status:", response.status_code)
cookies = session.cookies.get_dict()

response2 = session.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", headers=headers, cookies=cookies, timeout=10)
print("API status:", response2.status_code)
if response2.status_code == 200:
    data = response2.json()
    if data:
        print("CE totOI:", data["filtered"]["CE"]["totOI"])
    else:
        print("Data is empty dict")
else:
    print(response2.text[:200])
