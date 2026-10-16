"""Read-only sync from the shop's Google Sheet ("modulo noleggio") into MongoDB.

The sheet has two side-by-side tables on the first tab:
- fleet:    ID E-Bike | Modello & Tipologia ("Raimon Norza TG M") | ... | Stato Flotta
- bookings: ID Noleggio | ID E-Bike | Cliente | Telefono | Email | Data Inizio | Data Fine | Importo | Stato Noleggio
Dates are DD-MM-YYYY. Bike IDs prefix -> category: EG egravel, GR gravel, EB ebike_mtb.
"""
import csv
import io
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PREFIX_CATEGORY = {"EG": "egravel", "GR": "gravel", "EB": "ebike_mtb"}
STATUS_MAP = {"prenotato": "confirmed", "completato": "completed", "non presentato": "cancelled", "annullato": "cancelled"}
SIZES = ["S", "M", "L", "XL"]


def sheet_csv_url() -> str:
    return (f"https://docs.google.com/spreadsheets/d/{os.environ['SHEET_ID']}"
            f"/export?format=csv&gid={os.environ['SHEET_GID']}")


def _norm_id(v: str) -> str:
    return v.strip().upper()


def _date(v: str) -> Optional[str]:
    try:
        return datetime.strptime(v.strip(), "%d-%m-%Y").date().isoformat()
    except ValueError:
        return None


def _money(v: str) -> float:
    s = re.sub(r"[^\d,.-]", "", v).replace(".", "").replace(",", ".")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def parse_sheet(text: str):
    rows = list(csv.reader(io.StringIO(text)))
    header_idx = next(i for i, r in enumerate(rows) if "ID E-Bike" in r and "ID Noleggio" in r)
    header = rows[header_idx]
    fc = header.index("ID E-Bike")
    bc = header.index("ID Noleggio")

    def col(row, i):
        return row[i].strip() if i < len(row) else ""

    fleet = {}
    rentals = []
    for r in rows[header_idx + 1:]:
        uid = _norm_id(col(r, fc))
        model = col(r, fc + 1)
        m = re.search(r"\bTG\s*(XL|S|M|L)\b", model, re.I)
        if uid[:2] in PREFIX_CATEGORY and m:
            fleet[uid] = {"category": PREFIX_CATEGORY[uid[:2]], "size": m.group(1).upper(),
                          "status": col(r, fc + 9), "model": model}
        rid = col(r, bc)
        bike_uid = _norm_id(col(r, bc + 1))
        start, end = _date(col(r, bc + 5)), _date(col(r, bc + 6))
        if rid and bike_uid and start and end:
            rentals.append({"sheet_id": rid, "unit_id": bike_uid, "customer": col(r, bc + 2),
                            "phone": col(r, bc + 3), "email": col(r, bc + 4), "start": start, "end": end,
                            "amount": _money(col(r, bc + 7)), "status": col(r, bc + 8).lower()})
    return fleet, rentals


async def sync_from_sheet(db) -> dict:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        r = await c.get(sheet_csv_url())
    if r.status_code != 200 or "ID Noleggio" not in r.text:
        raise RuntimeError(f"Foglio non leggibile (HTTP {r.status_code})")
    fleet, rentals = parse_sheet(r.text)

    bikes = {b["category"]: b for b in await db.bikes.find({}, {"_id": 0}).sort("created_at", 1).to_list(100)}

    # Stock per model/size = number of units in the fleet table (out-of-service units excluded).
    stock = {cat: {s: 0 for s in SIZES} for cat in PREFIX_CATEGORY.values()}
    for u in fleet.values():
        if "servizio" not in u["status"].lower() and "venduta" not in u["status"].lower():
            stock[u["category"]][u["size"]] += 1
    for cat, st in stock.items():
        if cat in bikes:
            await db.bikes.update_one({"id": bikes[cat]["id"]}, {"$set": {"stock": st}})

    imported = 0
    for rt in rentals:
        unit = fleet.get(rt["unit_id"])
        bike = bikes.get(unit["category"]) if unit else None
        if not bike:
            continue
        days = (datetime.fromisoformat(rt["end"]) - datetime.fromisoformat(rt["start"])).days + 1
        status = STATUS_MAP.get(rt["status"], "confirmed")
        doc = {
            "user_id": "sheet", "user_email": rt["email"], "user_name": rt["customer"] or rt["sheet_id"],
            "phone": rt["phone"], "bike_id": bike["id"], "bike_name": bike["name"], "bike_image": bike.get("image_url", ""),
            "size": unit["size"], "unit_id": rt["unit_id"], "mode": "daily",
            "start": f"{rt['start']}T09:00", "end": f"{rt['end']}T19:00", "units": max(1, days),
            "total": rt["amount"], "payment_method": "store",
            "payment_status": "paid" if status == "completed" else "to_pay_in_store",
            "status": status, "source": "sheet",
        }
        res = await db.bookings.update_one(
            {"sheet_id": rt["sheet_id"], "source": "sheet"},
            {"$set": doc, "$setOnInsert": {"id": uuid.uuid4().hex, "sheet_id": rt["sheet_id"],
                                           "created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True)
        imported += 1 if (res.upserted_id or res.modified_count) else 0

    seen = [rt["sheet_id"] for rt in rentals]
    removed = await db.bookings.delete_many({"source": "sheet", "sheet_id": {"$nin": seen}})
    summary = {"units": len(fleet), "rentals": len(rentals), "changed": imported, "removed": removed.deleted_count,
               "stock": stock, "synced_at": datetime.now(timezone.utc).isoformat(), "error": None}
    await db.meta.update_one({"_id": "sheet_sync"}, {"$set": summary}, upsert=True)
    return summary
