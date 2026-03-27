import sys
import time
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import yaml

from bot.api import addtocart, calendars_month, find_full_price_tariff, find_slot, find_tariff_by_guid, tariffs, visit_event_page
from bot.bootstrap import bootstrap_session
from bot.notify import notify_success
from bot.session import build_session, session_cookie_dict, session_cookie_value

COOKIES_PATH = "cookies.json"
CONFIG_PATH = "config.yaml"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def write_debug_json(name: str, payload: dict) -> None:
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    (debug_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def compute_poll_interval(config: dict, target_date: str, now_utc: datetime) -> int:
    adaptive = config.get("adaptive_polling", {})
    if not adaptive.get("enabled", False):
        return config.get("poll_interval_seconds", 10)

    try:
        target_day = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return config.get("poll_interval_seconds", 10)

    if now_utc.date() != target_day:
        interval = int(adaptive.get("off_date_interval_seconds", adaptive.get("base_interval_seconds", 120)))
        return apply_poll_jitter(interval, adaptive)

    slot_times = adaptive.get("slot_times_utc", [])
    if not slot_times:
        return int(adaptive.get("base_interval_seconds", config.get("poll_interval_seconds", 10)))

    minute_windows = adaptive.get("minute_windows", {})
    fast_window = int(minute_windows.get("fast", 1))
    medium_window = int(minute_windows.get("medium", 5))
    slow_window = int(minute_windows.get("slow", 15))

    intervals = adaptive.get("interval_seconds", {})
    fast_interval = int(intervals.get("fast", 7))
    medium_interval = int(intervals.get("medium", 15))
    slow_interval = int(intervals.get("slow", 60))
    base_interval = int(adaptive.get("base_interval_seconds", config.get("poll_interval_seconds", 120)))

    now_minutes = now_utc.hour * 60 + now_utc.minute
    distances = [abs(now_minutes - (int(hour) * 60 + int(minute))) for hour, minute in slot_times]
    nearest_minutes = min(distances) if distances else 24 * 60

    if nearest_minutes <= fast_window:
        return apply_poll_jitter(fast_interval, adaptive)
    if nearest_minutes <= medium_window:
        return apply_poll_jitter(medium_interval, adaptive)
    if nearest_minutes <= slow_window:
        return apply_poll_jitter(slow_interval, adaptive)
    return apply_poll_jitter(base_interval, adaptive)


def apply_poll_jitter(interval: int, adaptive: dict) -> int:
    jitter = adaptive.get("jitter_seconds", 0)
    if not jitter:
        return max(1, interval)
    jitter = int(jitter)
    adjusted = interval + random.randint(-jitter, jitter)
    return max(1, adjusted)


def is_rate_limit_error(error: Exception) -> bool:
    message = str(error)
    return "HTTP 403" in message or "HTTP 429" in message


def create_bootstrapped_session(config: dict, slug: str):
    session = build_session(config, COOKIES_PATH)
    bootstrap = bootstrap_session(session, COOKIES_PATH, config, slug)
    return session, bootstrap


def run():
    config = load_config()
    active = config["active_event"]
    event = config["events"][active]

    slug = event["slug"]
    page = event["page"]
    target_date = event.get("date", config["target_date"])  # "YYYY-MM-DD"
    object_guid = event.get("object_guid")  # may be None
    object_tablename = event.get("object_tablename", "packetTypes")
    detail_guid = event.get("detail_guid", "_draft_0")
    quantity = event["quantity"]

    year, month, _ = target_date.split("-")
    year, month = int(year), int(month)

    session, bootstrap = create_bootstrapped_session(config, slug)

    ip_resp = session.get("https://ip.decodo.com/json", timeout=10)
    ip_info = ip_resp.json()
    exit_ip = ip_info.get("proxy", {}).get("ip") or ip_info.get("ip", "unknown")

    print(f"ColosseumBot starting")
    print(f"  Event : {slug}")
    print(f"  Date  : {target_date}")
    print(f"  Qty   : {quantity}")
    initial_poll = compute_poll_interval(config, target_date, datetime.now(timezone.utc))
    print(f"  Poll  : adaptive, starting at {initial_poll}s")
    print(f"  IP    : {exit_ip}")
    print(f"  FP    : {session_cookie_value(session, 'octofence_jslc_fp', '<missing>')}")
    if bootstrap.get("enabled"):
        print(f"  Boot  : inline_script={bootstrap.get('inline_script_found')} solved={bootstrap.get('solved_cookie_names')}")
        if "octofence_jslc" not in bootstrap.get("cookies_after_bootstrap", {}):
            print("  Warn  : bootstrap did not obtain octofence_jslc; read endpoints may work, but addtocart is likely to be blocked")
        for step in bootstrap.get("preflight_cookie_diffs", []):
            diff = step.get("cookie_diff_after_response", {})
            added = ",".join(sorted(diff.get("added", {}).keys())) or "-"
            changed = ",".join(sorted(diff.get("changed", {}).keys())) or "-"
            print(f"  Step  : {step.get('url')} added={added} changed={changed}")
    print()

    attempt = 0
    while True:
        attempt += 1
        now_dt = datetime.now(timezone.utc)
        now = now_dt.strftime("%H:%M:%S")
        poll_interval = compute_poll_interval(config, target_date, now_dt)
        print(f"[{now}] Attempt {attempt} — checking availability...", end=" ", flush=True)

        try:
            visit_event_page(session, slug)
            slots = calendars_month(session, page, year, month, slug)
            slot = find_slot(slots, target_date, quantity)

            if slot is None:
                print(f"no slot with capacity >= {quantity} on {target_date} (next poll in {poll_interval}s)")
                time.sleep(poll_interval)
                continue

            period_id = slot["period_id"]
            start_time = slot["startDateTime"]
            end_time = slot["endDateTime"]
            print(f"found slot {start_time} (capacity={slot['capacity']})")

            if object_guid:
                selected_tariff = {
                    "object_guid": object_guid,
                    "object_tablename": object_tablename,
                    "detail_guid": detail_guid,
                    "convention_guid": "",
                    "convention_text": "",
                    "group_guid": "",
                }
                print(f"  Using configured tariff directly: {object_guid}")
                write_debug_json(
                    "last_tariffs.json",
                    {
                        "slot": slot,
                        "selected_tariff": selected_tariff,
                        "tariffs": None,
                        "source": "configured_object_guid",
                    },
                )
            else:
                print("  Fetching tariffs for selected slot...")
                tariff_list = tariffs(session, period_id, start_time, slug, target_date)
                selected_tariff = find_full_price_tariff(tariff_list)
                if not selected_tariff:
                    raise RuntimeError(f"Could not resolve a usable tariff from response: {tariff_list}")
                print(f"  resolved Full price tariff: {selected_tariff.get('object_guid')}")
                write_debug_json(
                    "last_tariffs.json",
                    {
                        "slot": slot,
                        "selected_tariff": selected_tariff,
                        "tariffs": tariff_list,
                        "source": "tariffs_response",
                    },
                )

            visit_event_page(session, slug)
            print(f"  Adding {quantity}x to cart...", end=" ", flush=True)
            result = addtocart(session, period_id, start_time, end_time, quantity, page, slug, selected_tariff)
            print(f"done — cart items: {result.get('items')}")

            cart_url = f"https://ticketing.colosseo.it/en/checkout/"
            notify_success(f"Tickets added! Go to checkout: {cart_url}")
            print(f"\nCart URL: {cart_url}")
            print("\nSet these cookies in your browser before visiting the cart:")
            for name, value in session_cookie_dict(session).items():
                print(f"  {name} = {value}")
            sys.exit(0)

        except KeyboardInterrupt:
            print("\nStopped by user.")
            sys.exit(0)
        except Exception as e:
            print(f"error: {e}")
            print("debug: if this was an OctoFence block, inspect files under ./debug/")
            if is_rate_limit_error(e):
                print("debug: rate-limit/block response detected; rebuilding session before retry")
            if config.get("session", {}).get("rebuild_on_error", True):
                print("debug: rebuilding session and re-running bootstrap before the next attempt")
                session, bootstrap = create_bootstrapped_session(config, slug)
            time.sleep(poll_interval)


if __name__ == "__main__":
    run()
