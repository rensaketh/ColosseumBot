import json
from pathlib import Path

from curl_cffi import requests

BASE_URL = "https://ticketing.colosseo.it"
VOLATILE_COOKIE_NAMES = {
    "PHPSESSID",
    "octofence_jslc",
    "octofence_jslc_fp",
    "expiration_date",
}

DEFAULT_HEADERS = {
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


def load_cookies(cookies_path: str) -> dict[str, str]:
    path = Path(cookies_path)
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def save_cookies(cookies_path: str, cookies: dict[str, str]) -> None:
    path = Path(cookies_path)
    with path.open("w") as f:
        json.dump(cookies, f, indent=2, sort_keys=True)
        f.write("\n")


def session_cookie_dict(session: requests.Session) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for cookie in session.cookies.jar:
        cookies[cookie.name] = cookie.value
    return cookies


def session_cookie_value(session: requests.Session, name: str, default: str | None = None) -> str | None:
    return session_cookie_dict(session).get(name, default)


def clean_start_cookies(cookies: dict[str, str], extra_names: list[str] | None = None) -> dict[str, str]:
    names = set(VOLATILE_COOKIE_NAMES)
    if extra_names:
        names.update(extra_names)
    return {name: value for name, value in cookies.items() if name not in names}


def build_session(config: dict, cookies_path: str) -> requests.Session:
    session_cfg = config.get("session", {})
    proxy = config.get("proxy")
    cookies = load_cookies(cookies_path)
    if config.get("bootstrap", {}).get("clean_start", True):
        cookies = clean_start_cookies(cookies, config.get("bootstrap", {}).get("extra_volatile_cookie_names"))

    impersonate = session_cfg.get("impersonate", "firefox")
    session = requests.Session(impersonate=impersonate)

    headers = dict(DEFAULT_HEADERS)
    if session_cfg.get("accept_language"):
        headers["Accept-Language"] = session_cfg["accept_language"]
    headers.update(session_cfg.get("headers", {}))

    session.headers.update(headers)
    session.cookies.update(cookies)
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    session.bot_config = config
    session.cookies_path = cookies_path
    return session
