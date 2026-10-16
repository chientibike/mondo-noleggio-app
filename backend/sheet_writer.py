"""Write app bookings into the shop's Google Sheet through a Google Apps Script web app
bound to the sheet (no Google Cloud project needed). Configure SHEET_SCRIPT_URL and SHEET_SCRIPT_TOKEN.
"""
import logging
import os
from datetime import date

import httpx

logger = logging.getLogger(__name__)

SHEET_STATUS = {"confirmed": "Prenotato", "cancelled": "Annullato", "completed": "Completato"}


def enabled() -> bool:
    return bool(os.environ.get("SHEET_SCRIPT_URL"))


async def script_url(db) -> str:
    doc = await db.meta.find_one({"_id": "sheet_write"}) or {}
    return doc.get("url") or os.environ.get("SHEET_SCRIPT_URL", "")


async def ping(url: str) -> bool:
    """True when the URL is our Apps Script with the right token (it answers 'unknown action')."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.post(url, json={"action": "ping", "token": os.environ["SHEET_SCRIPT_TOKEN"]})
        return r.json().get("error") == "unknown action"
    except Exception:
        return False


def _it_date(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"'{d.day:02d}-{d.month:02d}-{d.year}"  # leading quote keeps it as text


async def _post(url: str, payload: dict) -> dict:
    payload = {**payload, "token": os.environ["SHEET_SCRIPT_TOKEN"]}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.post(url, json=payload)
    try:
        return r.json()
    except ValueError:
        return {"ok": False, "error": f"HTTP {r.status_code}"}


async def push_booking(db, booking_id: str):
    """Append the booking as a new row (once), or update its status if already written."""
    url = await script_url(db)
    if not url:
        return
    bk = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not bk or bk.get("source") != "app":
        return
    status = SHEET_STATUS.get(bk["status"])
    if not status:
        return
    try:
        if bk.get("sheet_id"):
            res = await _post(url, {"action": "update", "sheet_id": bk["sheet_id"], "status": status})
        elif bk["status"] == "confirmed":
            res = await _post(url, {
                "action": "append", "unit_id": bk.get("unit_id") or "", "customer": bk["user_name"],
                "phone": bk.get("phone") or "", "email": bk["user_email"],
                "start": _it_date(bk["start"]), "end": _it_date(bk["end"]), "amount": bk["total"], "status": status,
            })
            if res.get("ok") and res.get("sheet_id"):
                await db.bookings.update_one({"id": booking_id}, {"$set": {"sheet_id": res["sheet_id"]}})
                # A concurrent import may have copied the row as a sheet booking: drop the copy.
                await db.bookings.delete_many({"source": "sheet", "sheet_id": res["sheet_id"]})
        else:
            return
        if not res.get("ok"):
            logger.warning("Sheet write failed for %s: %s", booking_id, res)
    except Exception as e:
        logger.warning("Sheet write error for %s: %s", booking_id, e)
