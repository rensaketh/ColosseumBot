import json

from curl_cffi import requests

BASE_URL = "https://ticketing.colosseo.it"

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE_URL,
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "TE": "trailers",
}


def build_session(cookies_path: str, proxy: str | None = None) -> requests.Session:
    with open(cookies_path) as f:
        cookies = json.load(f)

    session = requests.Session(impersonate="firefox")
    session.headers.update(HEADERS)
    session.cookies.update(cookies)
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session
