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
        if re.match(r"^[A-Z]{2,3}-\d+$", uid) and m:
            base = re.sub(r"\s*\bTG\s*(XL|S|M|L)\b.*$", "", model, flags=re.I).strip()
            fleet[uid] = {"category": PREFIX_CATEGORY.get(uid[:2]), "size": m.group(1).upper(),
                          "status": col(r, fc + 9), "model": model, "base": base}
        rid = col(r, bc)
        bike_uid = _norm_id(col(r, bc + 1))
        start, end = _date(col(r, bc + 5)), _date(col(r, bc + 6))
        if rid and bike_uid and start and end:
            rentals.append({"sheet_id": rid, "unit_id": bike_uid, "customer": col(r, bc + 2),
                            "phone": col(r, bc + 3), "email": col(r, bc + 4), "start": start, "end": end,
                            "amount": _money(col(r, bc + 7)), "status": col(r, bc + 8).lower()})
    return fleet, rentals


# Optional "Modelli" tab: one row per model with app details.
MODEL_COLS = {"modello": "base", "nome app": "name", "categoria": "category", "prezzo giorno": "price_day",
              "foto": "image_url", "descrizione": "description", "descrizione en": "description_en",
              "telaio": "frame", "motore": "motor", "batteria": "battery", "autonomia": "range",
              "escursione": "suspension", "cambio": "groupset", "freni": "brakes", "ruote": "wheels", "peso": "weight"}
SPEC_FIELDS = ["frame", "motor", "battery", "range", "suspension", "groupset", "brakes", "wheels", "weight"]
CATEGORY_PRICES = {"gravel": 40.0, "egravel": 50.0, "ebike_mtb": 60.0}


def _category(v: str) -> Optional[str]:
    s = re.sub(r"[^a-z]", "", v.lower())
    if "mtb" in s or s in ("emtb", "ebike"):
        return "ebike_mtb"
    if s.startswith("e") and "gravel" in s:
        return "egravel"
    if "gravel" in s:
        return "gravel"
    return None


def parse_models(text: str) -> dict:
    rows = list(csv.reader(io.StringIO(text)))
    for i, r in enumerate(rows):
        keys = [c.strip().lower() for c in r]
        if "modello" in keys and "categoria" in keys:
            idx = {MODEL_COLS[k]: j for j, k in enumerate(keys) if k in MODEL_COLS}
            out = {}
            for row in rows[i + 1:]:
                get = lambda f: row[idx[f]].strip() if f in idx and idx[f] < len(row) else ""  # noqa: E731
                base = get("base")
                if not base:
                    continue
                info = {f: get(f) for f in idx if f != "base"}
                info["category"] = _category(info.get("category", "")) or ""
                info["price_day"] = _money(info["price_day"]) if info.get("price_day") else 0.0
                out[base.lower()] = info
            return out
    return {}


async def _fetch(url: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        r = await c.get(url)
    return r.text if r.status_code == 200 else None


async def resolve_bikes(db, fleet: dict, models: dict) -> dict:
    """Return base model name (lowercase) -> bike doc, creating/updating bikes from the sheet."""
    bikes = await db.bikes.find({}, {"_id": 0}).sort("created_at", 1).to_list(200)
    by_model = {b["sheet_model"].lower(): b for b in bikes if b.get("sheet_model")}
    bases = {}
    for u in fleet.values():
        prev = bases.get(u["base"].lower())
        if not prev or (not prev[1] and u["category"]):
            bases[u["base"].lower()] = (u["base"], u["category"])
    for k, info in models.items():
        bases.setdefault(k, (k, info.get("category") or None))

    out = {}
    for key, (base, unit_cat) in bases.items():
        info = models.get(key, {})
        cat = info.get("category") or unit_cat
        bike = by_model.get(key)
        if not bike and cat:
            # Legacy bikes created before the sheet linked models: adopt the first one of the same category.
            bike = next((b for b in bikes if b["category"] == cat and not b.get("sheet_model")), None)
            if bike:
                bike["sheet_model"] = base
                await db.bikes.update_one({"id": bike["id"]}, {"$set": {"sheet_model": base}})
        if not bike:
            if not cat:
                continue
            bike = {"id": uuid.uuid4().hex, "name": info.get("name") or base, "category": cat,
                    "description": "", "description_en": "", "image_url": "", "specs": {},
                    "price_day": info.get("price_day") or CATEGORY_PRICES[cat],
                    "stock": {s: 0 for s in SIZES}, "sheet_model": base,
                    "created_at": datetime.now(timezone.utc).isoformat()}
            await db.bikes.insert_one(dict(bike))
            bikes.append(bike)
        upd = {}
        for f in ("name", "image_url", "description", "description_en"):
            if info.get(f):
                upd[f] = info[f]
        if info.get("price_day"):
            upd["price_day"] = info["price_day"]
        if info.get("category"):
            upd["category"] = info["category"]
        for f in SPEC_FIELDS:
            if info.get(f):
                upd[f"specs.{f}"] = info[f]
        if upd:
            await db.bikes.update_one({"id": bike["id"]}, {"$set": upd})
        out[key] = bike
    return out


async def sync_from_sheet(db) -> dict:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        r = await c.get(sheet_csv_url())
    if r.status_code != 200 or "ID Noleggio" not in r.text:
        raise RuntimeError(f"Foglio non leggibile (HTTP {r.status_code})")
    fleet, rentals = parse_sheet(r.text)
    models_txt = await _fetch(f"https://docs.google.com/spreadsheets/d/{os.environ['SHEET_ID']}/gviz/tq?tqx=out:csv&sheet=Modelli")
    models = parse_models(models_txt) if models_txt else {}
    by_base = await resolve_bikes(db, fleet, models)

    # Stock per model/size = number of units in the fleet table (out-of-service units excluded).
    stock = {}
    units = []
    for uid, u in fleet.items():
        bike = by_base.get(u["base"].lower())
        if not bike:
            continue
        u["bike_id"] = bike["id"]
        st = stock.setdefault(bike["id"], {s: 0 for s in SIZES})
        active = "servizio" not in u["status"].lower() and "venduta" not in u["status"].lower()
        if active:
            st[u["size"]] += 1
        units.append({"unit_id": uid, "bike_id": bike["id"], "size": u["size"], "active": active})
    for b in await db.bikes.find({"sheet_model": {"$exists": True}}, {"_id": 0, "id": 1}).to_list(200):
        await db.bikes.update_one({"id": b["id"]}, {"$set": {"stock": stock.get(b["id"], {s: 0 for s in SIZES})}})
    await db.units.delete_many({"unit_id": {"$nin": list(fleet)}})
    for u in units:
        await db.units.update_one({"unit_id": u["unit_id"]}, {"$set": u}, upsert=True)
    bikes = {b["id"]: b for b in await db.bikes.find({}, {"_id": 0}).to_list(200)}

    imported = 0
    app_sheet_ids = set(await db.bookings.distinct("sheet_id", {"source": "app"}))
    app_sheet_ids.discard(None)
    await db.bookings.delete_many({"source": "sheet", "sheet_id": {"$in": list(app_sheet_ids)}})
    for rt in rentals:
        unit = fleet.get(rt["unit_id"])
        bike = bikes.get(unit.get("bike_id")) if unit else None
        if not bike or rt["sheet_id"] in app_sheet_ids:
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
    summary = {"units": len(fleet), "rentals": len(rentals), "models": len(by_base), "models_tab": bool(models),
               "changed": imported, "removed": removed.deleted_count,
               "stock": stock, "synced_at": datetime.now(timezone.utc).isoformat(), "error": None}
    await db.meta.update_one({"_id": "sheet_sync"}, {"$set": summary}, upsert=True)
    return summary
