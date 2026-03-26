import urllib.parse
from datetime import datetime, timezone

import requests

BASE_URL = "https://ticketing.colosseo.it/mtajax"


def visit_event_page(session, slug: str) -> None:
    """Visit the event page to establish a real browser navigation in OctoFence's eyes."""
    session.get(
        f"https://ticketing.colosseo.it/en/eventi/{slug}/",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        },
        timeout=15,
    )


def calendars_month(session, page: int, year: int, month: int, slug: str) -> list[dict]:
    """Returns all time slots for the given month."""
    referer = f"https://ticketing.colosseo.it/en/eventi/{slug}/"
    resp = session.post(
        f"{BASE_URL}/calendars_month",
        data={"action": "midaabc_calendars_month", "page": page, "year": year, "month": month},
        headers={"Referer": referer},
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"calendars_month failed: {body}")
    return body["data"]


def tariffs(session: requests.Session, period_id: str, start_time: str, slug: str, date: str) -> list[dict]:
    """Returns available tariff types for the given slot."""
    referer = f"https://ticketing.colosseo.it/en/eventi/{slug}/?t={date}"
    resp = session.post(
        f"{BASE_URL}/tariffs",
        data={
            "action": "midaabc_tariffs",
            "period_id": period_id,
            "start_time": start_time,
        },
        headers={"Referer": referer},
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"tariffs failed: {body}")
    return body["data"]


def addtocart(
    session: requests.Session,
    period_id: str,
    start_time: str,
    end_time: str,
    object_guid: str,
    quantity: int,
    page: int,
    slug: str,
) -> dict:
    """Adds tickets to cart. Returns response data on success."""
    referer = f"https://ticketing.colosseo.it/en/eventi/{slug}/?t={urllib.parse.quote(start_time)}"
    data = {
        "action": "midaabc_addtocart",
        "items[0][detail_guid]": "_draft_0",
        "items[0][period_id]": period_id,
        "items[0][start_time]": start_time,
        "items[0][end_time]": end_time,
        "items[0][object_guid]": object_guid,
        "items[0][object_tablename]": "packetTypes",
        "items[0][quantity]": quantity,
        "items[0][convention_guid]": "",
        "items[0][convention_text]": "",
        "items[0][group_guid]": "",
        "page": page,
    }
    resp = session.post(
        f"{BASE_URL}/addtocart",
        data=data,
        headers={"Referer": referer},
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"addtocart failed: {body}")
    return body["data"]


def find_slot(slots: list[dict], target_date: str, quantity: int) -> dict | None:
    """
    Returns the first slot on target_date (YYYY-MM-DD) with capacity >= quantity.
    Slots are already ordered by startDateTime from the API.
    """
    for slot in slots:
        slot_date = slot["startDateTime"][:10]  # "2026-04-24T16:00:00Z" -> "2026-04-24"
        if slot_date == target_date and slot["capacity"] >= quantity:
            return slot
    return None


def find_full_price_tariff(tariff_list: list[dict]) -> dict | None:
    """Returns the Full price tariff from a tariffs response."""
    for t in tariff_list:
        if t.get("label", "").lower() == "full price":
            return t
    return None
