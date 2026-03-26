import sys
import time
from datetime import datetime, timezone

import yaml

from bot.alarm import sound_alarm
from bot.api import addtocart, calendars_month, find_full_price_tariff, find_slot, tariffs, visit_event_page
from bot.session import build_session

COOKIES_PATH = "cookies.json"
CONFIG_PATH = "config.yaml"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run():
    config = load_config()
    active = config["active_event"]
    event = config["events"][active]
    poll_interval = config.get("poll_interval_seconds", 10)

    slug = event["slug"]
    page = event["page"]
    target_date = event["date"]  # "YYYY-MM-DD"
    object_guid = event.get("object_guid")  # may be None
    quantity = event["quantity"]

    year, month, _ = target_date.split("-")
    year, month = int(year), int(month)

    proxy = config.get("proxy")
    session = build_session(COOKIES_PATH, proxy=proxy)

    ip_resp = session.get("https://ip.decodo.com/json", timeout=10)
    ip_info = ip_resp.json()
    exit_ip = ip_info.get("proxy", {}).get("ip") or ip_info.get("ip", "unknown")

    print(f"ColosseumBot starting")
    print(f"  Event : {slug}")
    print(f"  Date  : {target_date}")
    print(f"  Qty   : {quantity}")
    print(f"  Poll  : every {poll_interval}s")
    print(f"  IP    : {exit_ip}")
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

            # Resolve object_guid via tariffs if not in config
            resolved_guid = object_guid
            if not resolved_guid:
                print("  object_guid not in config — calling tariffs to find Full price...")
                tariff_list = tariffs(session, period_id, start_time, slug, target_date)
                full_price = find_full_price_tariff(tariff_list)
                if not full_price:
                    raise RuntimeError("Could not find Full price tariff in tariffs response")
                resolved_guid = full_price["object_guid"]
                print(f"  resolved object_guid: {resolved_guid}")

            visit_event_page(session, slug)
            print(f"  Adding {quantity}x to cart...", end=" ", flush=True)
            result = addtocart(session, period_id, start_time, end_time, resolved_guid, quantity, page, slug)
            print(f"done — cart items: {result.get('items')}")

            cart_url = f"https://ticketing.colosseo.it/en/cart/"
            sound_alarm(f"Tickets added! Go to cart: {cart_url}")
            print(f"\nCart URL: {cart_url}")
            print("\nSet these cookies in your browser before visiting the cart:")
            for name, value in session.cookies.items():
                print(f"  {name} = {value}")
            sys.exit(0)

        except KeyboardInterrupt:
            print("\nStopped by user.")
            sys.exit(0)
        except Exception as e:
            print(f"error: {e}")
            time.sleep(poll_interval)


if __name__ == "__main__":
    run()
