import sys
import time
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from bot.alarm import sound_alarm
from bot.api import addtocart, calendars_month, find_full_price_tariff, find_slot, find_tariff_by_guid, tariffs, visit_event_page
from bot.bootstrap import bootstrap_session
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


def create_bootstrapped_session(config: dict, slug: str):
    session = build_session(config, COOKIES_PATH)
    bootstrap = bootstrap_session(session, COOKIES_PATH, config, slug)
    return session, bootstrap


def run():
    config = load_config()
    active = config["active_event"]
    event = config["events"][active]
    poll_interval = config.get("poll_interval_seconds", 10)

    slug = event["slug"]
    page = event["page"]
    target_date = event.get("date", config["target_date"])  # "YYYY-MM-DD"
    object_guid = event.get("object_guid")  # may be None
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
    print(f"  Poll  : every {poll_interval}s")
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
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{now}] Attempt {attempt} — checking availability...", end=" ", flush=True)

        try:
            visit_event_page(session, slug)
            slots = calendars_month(session, page, year, month, slug)
            slot = find_slot(slots, target_date, quantity)

            if slot is None:
                print(f"no slot with capacity >= {quantity} on {target_date}")
                time.sleep(poll_interval)
                continue

            period_id = slot["period_id"]
            start_time = slot["startDateTime"]
            end_time = slot["endDateTime"]
            print(f"found slot {start_time} (capacity={slot['capacity']})")

            print("  Fetching tariffs for selected slot...")
            tariff_list = tariffs(session, period_id, start_time, slug, target_date)
            selected_tariff = None

            if object_guid:
                selected_tariff = find_tariff_by_guid(tariff_list, object_guid)
                if selected_tariff:
                    print(f"  matched configured object_guid: {object_guid}")
                else:
                    print("  configured object_guid not found in live tariff list; falling back to Full price...")

            if not selected_tariff:
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
                },
            )

            visit_event_page(session, slug)
            print(f"  Adding {quantity}x to cart...", end=" ", flush=True)
            result = addtocart(session, period_id, start_time, end_time, quantity, page, slug, selected_tariff)
            print(f"done — cart items: {result.get('items')}")

            cart_url = f"https://ticketing.colosseo.it/en/checkout/"
            sound_alarm(f"Tickets added! Go to cart: {cart_url}")
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
            if config.get("session", {}).get("rebuild_on_error", True):
                print("debug: rebuilding session and re-running bootstrap before the next attempt")
                session, bootstrap = create_bootstrapped_session(config, slug)
            time.sleep(poll_interval)


if __name__ == "__main__":
    run()
