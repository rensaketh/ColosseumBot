import urllib.parse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from bot.bootstrap import dump_debug_artifacts, solve_challenge_html

BASE_URL = "https://ticketing.colosseo.it/mtajax"


def _write_debug_json(name: str, payload: dict) -> None:
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    (debug_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _raise_for_response(resp, endpoint: str) -> None:
    if 200 <= resp.status_code < 300:
        return
    snippet = resp.text[:300].replace("\n", " ").strip()
    raise RuntimeError(f"{endpoint} failed with HTTP {resp.status_code} for {resp.url} :: {snippet}")


def _request_with_challenge_retry(session, method: str, url: str, endpoint: str, **kwargs):
    response = session.request(method, url, **kwargs)
    if response.status_code == 403 and "octofence-pub" in response.text.lower():
        dump_debug_artifacts(f"{endpoint}_blocked", response.text, str(response.url))
        solved = solve_challenge_html(session, response.text, str(response.url))
        if solved:
            response = session.request(method, url, **kwargs)
            if response.status_code == 403 and "octofence-pub" in response.text.lower():
                dump_debug_artifacts(f"{endpoint}_blocked_retry", response.text, str(response.url))
    _raise_for_response(response, endpoint)
    return response


def visit_event_page(session, slug: str) -> None:
    """Visit the event page to establish a real browser navigation in OctoFence's eyes."""
    _request_with_challenge_retry(
        session,
        "GET",
        f"https://ticketing.colosseo.it/en/eventi/{slug}/",
        endpoint="visit_event_page",
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
    resp = _request_with_challenge_retry(
        session,
        "POST",
        f"{BASE_URL}/calendars_month",
        endpoint="calendars_month",
        data={"action": "midaabc_calendars_month", "page": page, "year": year, "month": month},
        headers={"Referer": referer},
    )
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"calendars_month failed: {body}")
    return body["data"]


def tariffs(session: requests.Session, period_id: str, start_time: str, slug: str, date: str) -> list[dict]:
    """Returns available tariff types for the given slot."""
    referer = f"https://ticketing.colosseo.it/en/eventi/{slug}/?t={date}"
    resp = _request_with_challenge_retry(
        session,
        "POST",
        f"{BASE_URL}/tariffs",
        endpoint="tariffs",
        data={
            "action": "midaabc_tariffs",
            "period_id": period_id,
            "start_time": start_time,
        },
        headers={"Referer": referer},
    )
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"tariffs failed: {body}")
    return body["data"]


def activity_tariffs(
    session: requests.Session,
    period_id: str,
    start_time: str,
    activity_guid: str,
    slug: str,
    date: str,
) -> list[dict]:
    """Returns available activity-linked products for the given slot/activity."""
    referer = f"https://ticketing.colosseo.it/en/eventi/{slug}/?t={date}"
    resp = _request_with_challenge_retry(
        session,
        "POST",
        f"{BASE_URL}/activity_tariffs",
        endpoint="activity_tariffs",
        data={
            "action": "midaabc_activity_tariffs",
            "period_id": period_id,
            "start_time": start_time,
            "activity_guid": activity_guid,
        },
        headers={"Referer": referer},
    )
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"activity_tariffs failed: {body}")
    return body["data"]


def build_addtocart_item(
    period_id: str,
    start_time: str,
    end_time: str,
    quantity: int,
    tariff: dict,
) -> dict[str, str | int]:
    detail_guid = tariff.get("detail_guid") or tariff.get("detailGuid") or "_draft_0"
    object_guid = tariff.get("object_guid") or tariff.get("objectGuid")
    if not object_guid:
        raise RuntimeError(f"Selected tariff is missing object_guid: {tariff}")

    object_tablename = (
        tariff.get("object_tablename")
        or tariff.get("objectTableName")
        or tariff.get("tablename")
        or "packetTypes"
    )

    return {
        "items[0][detail_guid]": detail_guid,
        "items[0][period_id]": period_id,
        "items[0][start_time]": start_time,
        "items[0][end_time]": end_time,
        "items[0][object_guid]": object_guid,
        "items[0][object_tablename]": object_tablename,
        "items[0][quantity]": quantity,
        "items[0][convention_guid]": tariff.get("convention_guid", ""),
        "items[0][convention_text]": tariff.get("convention_text", ""),
        "items[0][group_guid]": tariff.get("group_guid", ""),
    }


def build_activity_addtocart_items(
    period_id: str,
    start_time: str,
    end_time: str,
    quantity: int,
    activity: dict,
    tariff: dict,
) -> dict[str, str | int | bool]:
    activity_object_guid = (
        activity.get("object_guid")
        or activity.get("objectGuid")
        or activity.get("activity_object_guid")
        or activity.get("guid")
    )
    if not activity_object_guid:
        raise RuntimeError(f"Selected activity is missing object_guid: {activity}")

    tariff_object_guid = tariff.get("object_guid") or tariff.get("objectGuid")
    if not tariff_object_guid:
        raise RuntimeError(f"Selected tariff is missing object_guid: {tariff}")

    return {
        "items[0][period_id]": period_id,
        "items[0][start_time]": start_time,
        "items[0][end_time]": end_time,
        "items[0][object_guid]": activity_object_guid,
        "items[0][object_tablename]": "activities",
        "items[0][activityDetail_guid]": activity.get("activityDetail_guid", ""),
        "items[0][quantity]": quantity,
        "items[0][group_guid]": activity.get("group_guid", ""),
        "items[1][detail_guid]": tariff.get("detail_guid") or tariff.get("detailGuid") or "_draft_0",
        "items[1][period_id]": period_id,
        "items[1][start_time]": start_time,
        "items[1][end_time]": end_time,
        "items[1][object_guid]": tariff_object_guid,
        "items[1][object_tablename]": tariff.get("object_tablename")
        or tariff.get("objectTableName")
        or tariff.get("tablename")
        or "packetTypes",
        "items[1][quantity]": quantity,
        "items[1][convention_guid]": tariff.get("convention_guid", ""),
        "items[1][convention_text]": tariff.get("convention_text", ""),
        "items[1][group_guid]": tariff.get("group_guid", ""),
        "items[1][activityDetail_guid]": activity.get("activityDetail_guid", ""),
        "items[1][activityPerPerson]": True,
    }


def addtocart(
    session: requests.Session,
    period_id: str,
    start_time: str,
    end_time: str,
    quantity: int,
    page: int,
    slug: str,
    tariff: dict,
    activity: dict | None = None,
) -> dict:
    """Adds tickets to cart. Returns response data on success."""
    referer = f"https://ticketing.colosseo.it/en/eventi/{slug}/?t={urllib.parse.quote(start_time)}"
    if activity is not None:
        data = build_activity_addtocart_items(period_id, start_time, end_time, quantity, activity, tariff)
    else:
        data = build_addtocart_item(period_id, start_time, end_time, quantity, tariff)
    data.update({
        "action": "midaabc_addtocart",
        "page": page,
    })
    _write_debug_json(
        "last_addtocart_payload.json",
        {
            "referer": referer,
            "payload": data,
            "selected_activity": activity,
            "selected_tariff": tariff,
            "cookies": {cookie.name: cookie.value for cookie in session.cookies.jar},
        },
    )
    resp = _request_with_challenge_retry(
        session,
        "POST",
        f"{BASE_URL}/addtocart",
        endpoint="addtocart",
        data=data,
        headers={"Referer": referer},
    )
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


def find_tariff_by_guid(tariff_list: list[dict], object_guid: str) -> dict | None:
    for tariff in tariff_list:
        if tariff.get("object_guid") == object_guid or tariff.get("objectGuid") == object_guid:
            return tariff
    return None


def find_activity_item(activity_list: list[dict], object_guid: str | None = None) -> dict | None:
    if object_guid:
        for activity in activity_list:
            if (
                activity.get("object_guid") == object_guid
                or activity.get("objectGuid") == object_guid
                or activity.get("guid") == object_guid
            ):
                return activity
    return activity_list[0] if activity_list else None
