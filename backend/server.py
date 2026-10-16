from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import re
import asyncio
from sheet_sync import sync_from_sheet
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
from datetime import datetime, timezone, timedelta, date as date_cls
import bcrypt
import jwt
import httpx
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout, CheckoutSessionRequest,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
TOKEN_DAYS = 7
STRIPE_API_KEY = os.environ['STRIPE_API_KEY']
SHEET_SYNC_SECONDS = 120

SIZES = ["S", "M", "L", "XL"]
SIZE_HEIGHTS = {"S": "155-165 cm", "M": "165-175 cm", "L": "175-185 cm", "XL": "185-195 cm"}
CATEGORIES = ["gravel", "egravel", "ebike_mtb"]
CATEGORY_PRICES = {"gravel": 40.0, "egravel": 50.0, "ebike_mtb": 60.0}
OPEN_HOUR = 9
CLOSE_HOUR = 19

app = FastAPI()


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


# ---------------- Models ----------------
class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    role: str
    picture: Optional[str] = None
    phone: Optional[str] = None


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=200)
    name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: str
    password: str


class SessionIn(BaseModel):
    session_id: str


class Bike(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    category: Literal["gravel", "egravel", "ebike_mtb"]
    description: str = ""
    description_en: str = ""
    image_url: str = ""
    price_day: float
    specs: Dict[str, str] = Field(default_factory=dict)
    stock: Dict[str, int] = Field(default_factory=lambda: {s: 0 for s in SIZES})
    created_at: str = Field(default_factory=now_iso)


class BikeIn(BaseModel):
    name: str = Field(min_length=1)
    category: Literal["gravel", "egravel", "ebike_mtb"]
    description: str = ""
    description_en: str = ""
    image_url: str = ""
    price_day: float = Field(gt=0)
    specs: Dict[str, str] = Field(default_factory=dict)
    stock: Dict[str, int]


class Booking(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    user_email: str
    user_name: str
    bike_id: str
    bike_name: str
    bike_image: str = ""
    size: str
    mode: Literal["hourly", "daily"]
    start: str  # local "YYYY-MM-DDTHH:MM"
    end: str
    units: int
    total: float
    payment_method: Literal["stripe", "store"]
    payment_status: Literal["pending", "paid", "to_pay_in_store", "failed"]
    status: Literal["pending_payment", "confirmed", "cancelled", "completed"]
    stripe_session_id: Optional[str] = None
    source: str = "app"  # "app" or "sheet"
    sheet_id: Optional[str] = None
    unit_id: Optional[str] = None
    phone: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class BookingIn(BaseModel):
    bike_id: str
    size: Literal["S", "M", "L", "XL"]
    mode: Literal["daily"] = "daily"
    date: str  # YYYY-MM-DD
    days: Optional[int] = None
    payment_method: Literal["stripe", "store"]
    phone: Optional[str] = Field(default=None, max_length=30)


class CheckoutIn(BaseModel):
    booking_id: str
    return_url: str


class AdminBookingPatch(BaseModel):
    status: Optional[Literal["pending_payment", "confirmed", "cancelled", "completed"]] = None
    payment_status: Optional[Literal["pending", "paid", "to_pay_in_store", "failed"]] = None


# ---------------- Auth helpers ----------------
def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except Exception:
        return False


def make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + timedelta(days=TOKEN_DAYS)}, JWT_SECRET, algorithm=JWT_ALG)


def to_public(u: dict) -> UserPublic:
    return UserPublic(id=u["id"], email=u["email"], name=u.get("name") or u["email"].split("@")[0],
                      role=u.get("role", "user"), picture=u.get("picture"), phone=u.get("phone"))


async def current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Non autenticato")
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Sessione scaduta")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user:
        raise HTTPException(401, "Utente non trovato")
    return user


async def admin_user(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Solo amministratori")
    return user


# ---------------- Auth routes ----------------
@api.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Email non valida")
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email già registrata")
    user = {"id": new_id(), "email": email, "name": body.name.strip(), "role": "user",
            "password_hash": hash_pw(body.password), "created_at": now_iso()}
    await db.users.insert_one(user)
    return {"token": make_token(user["id"]), "user": to_public(user)}


@api.post("/auth/login")
async def login(body: LoginIn):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not verify_pw(body.password, user["password_hash"]):
        raise HTTPException(401, "Email o password errati")
    return {"token": make_token(user["id"]), "user": to_public(user)}


@api.post("/auth/session")
async def google_session(body: SessionIn):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                        headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(401, "Sessione Google non valida")
    data = r.json()
    email = data["email"].strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        await db.users.update_one({"id": user["id"]}, {"$set": {"picture": data.get("picture"),
                                                                 "name": user.get("name") or data.get("name")}})
        user = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    else:
        user = {"id": new_id(), "email": email, "name": data.get("name") or email.split("@")[0],
                "picture": data.get("picture"), "role": "user", "created_at": now_iso()}
        await db.users.insert_one(user)
        user.pop("_id", None)
    return {"session_token": make_token(user["id"]), "user": to_public(user)}


@api.get("/auth/me", response_model=UserPublic)
async def me(user: dict = Depends(current_user)):
    return to_public(user)


# ---------------- Availability ----------------
def parse_range(body: BookingIn) -> tuple[str, str, int]:
    try:
        d = date_cls.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(422, "Data non valida")
    if d < datetime.now().date():
        raise HTTPException(422, "Non puoi prenotare nel passato")
    days = body.days or 1
    if days < 1 or days > 30:
        raise HTTPException(422, "Durata tra 1 e 30 giorni")
    end_d = d + timedelta(days=days - 1)
    return f"{d.isoformat()}T{OPEN_HOUR:02d}:00", f"{end_d.isoformat()}T{CLOSE_HOUR:02d}:00", days


async def booked_counts(bike_id: str, start: str, end: str) -> Dict[str, int]:
    counts = {s: 0 for s in SIZES}
    cursor = db.bookings.find({"bike_id": bike_id, "status": {"$in": ["pending_payment", "confirmed"]},
                               "start": {"$lt": end}, "end": {"$gt": start}}, {"_id": 0, "size": 1})
    async for b in cursor:
        counts[b["size"]] = counts.get(b["size"], 0) + 1
    return counts


async def availability(bike: dict, start: Optional[str], end: Optional[str]) -> Dict[str, int]:
    stock = {s: int(bike.get("stock", {}).get(s, 0)) for s in SIZES}
    if not start or not end:
        return stock
    used = await booked_counts(bike["id"], start, end)
    return {s: max(0, stock[s] - used[s]) for s in SIZES}


@api.get("/meta")
async def meta():
    return {"sizes": SIZES, "size_heights": SIZE_HEIGHTS, "categories": CATEGORIES, "category_prices": CATEGORY_PRICES,
            "open_hour": OPEN_HOUR, "close_hour": CLOSE_HOUR, "currency": "EUR"}


@api.get("/bikes")
async def list_bikes(category: Optional[str] = None, size: Optional[str] = None,
                     start: Optional[str] = None, end: Optional[str] = None):
    q = {"category": category} if category else {}
    bikes = await db.bikes.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    out = []
    for b in bikes:
        bike = Bike(**b).model_dump()
        bike["available"] = await availability(b, start, end)
        if size and bike["available"].get(size, 0) <= 0 and not start:
            continue
        if size and start and bike["available"].get(size, 0) <= 0:
            continue
        out.append(bike)
    return out


@api.get("/bikes/{bike_id}")
async def get_bike(bike_id: str, start: Optional[str] = None, end: Optional[str] = None):
    b = await db.bikes.find_one({"id": bike_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Bici non trovata")
    bike = Bike(**b).model_dump()
    bike["available"] = await availability(b, start, end)
    return bike


@api.post("/bikes/{bike_id}/quote")
async def quote(bike_id: str, body: BookingIn):
    b = await db.bikes.find_one({"id": bike_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Bici non trovata")
    start, end, units = parse_range(body)
    avail = await availability(b, start, end)
    price = b["price_day"]
    return {"start": start, "end": end, "units": units, "total": round(price * units, 2), "available": avail}


# ---------------- Bookings ----------------
@api.post("/bookings")
async def create_booking(body: BookingIn, user: dict = Depends(current_user)):
    b = await db.bikes.find_one({"id": body.bike_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Bici non trovata")
    start, end, units = parse_range(body)
    avail = await availability(b, start, end)
    if avail.get(body.size, 0) <= 0:
        raise HTTPException(409, f"Taglia {body.size} non disponibile per il periodo scelto")
    price = b["price_day"]
    booking = Booking(
        user_id=user["id"], user_email=user["email"], user_name=user.get("name") or user["email"],
        bike_id=b["id"], bike_name=b["name"], bike_image=b.get("image_url", ""), size=body.size,
        mode=body.mode, start=start, end=end, units=units, total=round(price * units, 2),
        payment_method=body.payment_method,
        payment_status="pending" if body.payment_method == "stripe" else "to_pay_in_store",
        status="pending_payment" if body.payment_method == "stripe" else "confirmed",
        phone=(body.phone or "").strip() or user.get("phone"),
    )
    if body.phone and body.phone.strip():
        await db.users.update_one({"id": user["id"]}, {"$set": {"phone": body.phone.strip()}})
    await db.bookings.insert_one(booking.model_dump())
    return booking


@api.get("/bookings/me", response_model=List[Booking])
async def my_bookings(user: dict = Depends(current_user)):
    docs = await db.bookings.find({"user_id": user["id"]}, {"_id": 0}).sort("start", -1).to_list(500)
    return [Booking(**d) for d in docs]


@api.post("/bookings/{booking_id}/cancel", response_model=Booking)
async def cancel_booking(booking_id: str, user: dict = Depends(current_user)):
    bk = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not bk or (bk["user_id"] != user["id"] and user.get("role") != "admin"):
        raise HTTPException(404, "Prenotazione non trovata")
    if bk["status"] in ("cancelled", "completed"):
        raise HTTPException(409, "Prenotazione non annullabile")
    await db.bookings.update_one({"id": booking_id}, {"$set": {"status": "cancelled"}})
    bk["status"] = "cancelled"
    return Booking(**bk)


# ---------------- Stripe ----------------
def stripe_client(request: Request) -> StripeCheckout:
    host = str(request.base_url).rstrip("/")
    return StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=f"{host}/api/webhook/stripe")


@api.post("/payments/stripe/checkout")
async def stripe_checkout(body: CheckoutIn, request: Request, user: dict = Depends(current_user)):
    bk = await db.bookings.find_one({"id": body.booking_id, "user_id": user["id"]}, {"_id": 0})
    if not bk:
        raise HTTPException(404, "Prenotazione non trovata")
    if bk["payment_status"] == "paid" or bk["status"] == "cancelled":
        raise HTTPException(409, "Prenotazione non pagabile")
    sep = "&" if "?" in body.return_url else "?"
    success = f"{body.return_url}{sep}session_id={{CHECKOUT_SESSION_ID}}&booking_id={bk['id']}"
    cancel = f"{body.return_url}{sep}cancelled=1&booking_id={bk['id']}"
    sc = stripe_client(request)
    session = await sc.create_checkout_session(CheckoutSessionRequest(
        amount=float(bk["total"]), currency="eur", success_url=success, cancel_url=cancel,
        metadata={"booking_id": bk["id"], "user_id": user["id"]},
    ))
    await db.payment_transactions.insert_one({
        "id": new_id(), "session_id": session.session_id, "booking_id": bk["id"], "user_id": user["id"],
        "amount": float(bk["total"]), "currency": "eur", "payment_status": "initiated", "created_at": now_iso(),
    })
    await db.bookings.update_one({"id": bk["id"]}, {"$set": {"stripe_session_id": session.session_id}})
    return {"url": session.url, "session_id": session.session_id}


async def apply_payment(session_id: str, payment_status: str, status: str):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        return
    if tx["payment_status"] == "paid":
        return
    await db.payment_transactions.update_one({"session_id": session_id},
                                             {"$set": {"payment_status": payment_status, "status": status}})
    if payment_status == "paid":
        await db.bookings.update_one({"id": tx["booking_id"]},
                                     {"$set": {"payment_status": "paid", "status": "confirmed"}})
    elif status == "expired":
        await db.bookings.update_one({"id": tx["booking_id"], "payment_status": {"$ne": "paid"}},
                                     {"$set": {"payment_status": "failed", "status": "cancelled"}})


@api.get("/payments/stripe/status/{session_id}")
async def stripe_status(session_id: str, request: Request, user: dict = Depends(current_user)):
    tx = await db.payment_transactions.find_one({"session_id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not tx:
        raise HTTPException(404, "Pagamento non trovato")
    st = await stripe_client(request).get_checkout_status(session_id)
    await apply_payment(session_id, st.payment_status, st.status)
    bk = await db.bookings.find_one({"id": tx["booking_id"]}, {"_id": 0})
    return {"payment_status": st.payment_status, "status": st.status, "booking": Booking(**bk)}


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    try:
        ev = await stripe_client(request).handle_webhook(payload, request.headers.get("Stripe-Signature"))
    except Exception as e:
        logger.warning("Stripe webhook error: %s", e)
        raise HTTPException(400, "Webhook non valido")
    if ev.session_id:
        await apply_payment(ev.session_id, ev.payment_status or "", "complete" if ev.payment_status == "paid" else "")
    return {"received": True}


@api.get("/payments/return", response_class=HTMLResponse)
async def payment_return(cancelled: Optional[str] = None, lang: str = "it"):
    if lang == "en":
        msg = "Payment cancelled" if cancelled else "Payment completed"
        hint = "Close this window and return to the Mondo Noleggio app."
    else:
        msg = "Pagamento annullato" if cancelled else "Pagamento completato"
        hint = "Chiudi questa finestra e torna all'app Mondo Noleggio."
    return f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>
<body style='font-family:-apple-system,sans-serif;text-align:center;padding:60px 24px;color:#121212'>
<h2>{msg}</h2><p>{hint}</p></body></html>"""


# ---------------- Admin ----------------
@api.get("/admin/bookings", response_model=List[Booking])
async def admin_bookings(status: Optional[str] = None, _: dict = Depends(admin_user)):
    q = {"status": status} if status else {}
    docs = await db.bookings.find(q, {"_id": 0}).sort("start", -1).to_list(1000)
    return [Booking(**d) for d in docs]


@api.patch("/admin/bookings/{booking_id}", response_model=Booking)
async def admin_patch_booking(booking_id: str, body: AdminBookingPatch, _: dict = Depends(admin_user)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(422, "Nessuna modifica")
    res = await db.bookings.find_one_and_update({"id": booking_id}, {"$set": upd}, projection={"_id": 0},
                                                return_document=True)
    if not res:
        raise HTTPException(404, "Prenotazione non trovata")
    return Booking(**res)


@api.post("/admin/sheet/sync")
async def admin_sheet_sync(_: dict = Depends(admin_user)):
    try:
        return await sync_from_sheet(db)
    except Exception as e:
        logger.warning("Sheet sync failed: %s", e)
        raise HTTPException(502, "Foglio Google non raggiungibile")


@api.get("/admin/sheet/status")
async def admin_sheet_status(_: dict = Depends(admin_user)):
    doc = await db.meta.find_one({"_id": "sheet_sync"}, {"_id": 0})
    return doc or {"synced_at": None}


async def sheet_sync_loop():
    while True:
        try:
            await sync_from_sheet(db)
        except Exception as e:
            logger.warning("Sheet sync failed: %s", e)
            await db.meta.update_one({"_id": "sheet_sync"}, {"$set": {"error": str(e)}}, upsert=True)
        await asyncio.sleep(SHEET_SYNC_SECONDS)


@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(admin_user)):
    today = datetime.now().date().isoformat()
    bikes = await db.bikes.find({}, {"_id": 0, "stock": 1}).to_list(500)
    total_units = sum(sum(int(v) for v in b.get("stock", {}).values()) for b in bikes)
    active = await db.bookings.count_documents({"status": {"$in": ["confirmed", "pending_payment"]}})
    today_count = await db.bookings.count_documents({"status": {"$in": ["confirmed", "pending_payment"]},
                                                     "start": {"$lte": f"{today}T23:59"}, "end": {"$gte": f"{today}T00:00"}})
    paid = await db.bookings.find({"payment_status": "paid"}, {"_id": 0, "total": 1}).to_list(5000)
    return {"bike_models": len(bikes), "total_units": total_units, "active_bookings": active,
            "today_bookings": today_count, "revenue_paid": round(sum(p["total"] for p in paid), 2)}


def clean_stock(stock: Dict[str, int]) -> Dict[str, int]:
    return {s: max(0, int(stock.get(s, 0))) for s in SIZES}


@api.post("/admin/bikes", response_model=Bike)
async def admin_create_bike(body: BikeIn, _: dict = Depends(admin_user)):
    bike = Bike(**{**body.model_dump(), "stock": clean_stock(body.stock)})
    await db.bikes.insert_one(bike.model_dump())
    return bike


@api.put("/admin/bikes/{bike_id}", response_model=Bike)
async def admin_update_bike(bike_id: str, body: BikeIn, _: dict = Depends(admin_user)):
    upd = {**body.model_dump(), "stock": clean_stock(body.stock)}
    res = await db.bikes.find_one_and_update({"id": bike_id}, {"$set": upd}, projection={"_id": 0},
                                             return_document=True)
    if not res:
        raise HTTPException(404, "Bici non trovata")
    return Bike(**res)


@api.delete("/admin/bikes/{bike_id}")
async def admin_delete_bike(bike_id: str, _: dict = Depends(admin_user)):
    res = await db.bikes.delete_one({"id": bike_id})
    if not res.deleted_count:
        raise HTTPException(404, "Bici non trovata")
    return {"ok": True}


# ---------------- Startup / seed ----------------
IMG_PARAMS = "?auto=format,compress&w=1200&h=800&fit=fill&fill=solid&fill-color=ffffff"
SEED_BIKES = [
    {"name": "Raymon Soreno Comp", "category": "gravel", "price_day": 40,
     "description": "Gravel muscolare con telaio in carbonio leggero e gomme da 45 mm: veloce su asfalto, sicura e divertente su strade bianche e sterrati.",
     "description_en": "Non-electric gravel bike with a light carbon frame and 45 mm tyres: fast on tarmac, safe and fun on gravel roads and trails.",
     "image_url": "https://raymon.imgix.net/userdata/dcshop/images/901102_raymon-soreno-comp-carbon-matt-side.png" + IMG_PARAMS,
     "specs": {"frame": "Carbonio MLC / MLC carbon", "groupset": "Shimano GRX 1x12 (40T, 10-51T)",
               "brakes": "Shimano idrauliche a disco, 160 mm / Shimano hydraulic disc, 160 mm",
               "wheels": "28\", Maxxis Reaver 45 mm", "weight": "10,2 kg"},
     "stock": {"S": 2, "M": 3, "L": 3, "XL": 1}},
    {"name": "Raymon Norza Comp", "category": "egravel", "price_day": 50,
     "description": "E-gravel in carbonio con motore Bosch SX: leggera e sportiva, ti spinge in salita e contro vento senza perdere il feeling della gravel.",
     "description_en": "Carbon e-gravel with Bosch SX motor: light and sporty, it pushes you uphill and into the wind while keeping that gravel feel.",
     "image_url": "https://raymon.imgix.net/userdata/dcshop/images/291072_raymon-norza-comp-greige-freckels-front.png" + IMG_PARAMS,
     "specs": {"frame": "Carbonio MLC, batteria estraibile / MLC carbon, removable battery",
               "motor": "Bosch Performance Line SX, 60 Nm", "battery": "Bosch CompactTube 400 Wh",
               "groupset": "Shimano CUES 1x11 (11-50T)",
               "brakes": "Shimano idrauliche a disco, 180 mm / Shimano hydraulic disc, 180 mm",
               "wheels": "28\", Continental Terra Trail 45 mm", "weight": "15,9 kg"},
     "stock": {"S": 1, "M": 2, "L": 2, "XL": 1}},
    {"name": "Raymon Vamok Pro", "category": "ebike_mtb", "price_day": 60,
     "description": "E-MTB enduro biammortizzata con motore Bosch CX di ultima generazione (120 Nm) e batteria da 800 Wh. Sospensioni RockShox, cambio Deore XT e freni Magura a 4 pistoncini; ruote 29\"/27,5\" per grip e agilità sui sentieri.",
     "description_en": "Full-suspension enduro e-MTB with the latest Bosch CX motor (120 Nm) and 800 Wh battery. RockShox suspension, Deore XT drivetrain and 4-piston Magura brakes; 29\"/27.5\" mullet wheels for grip and agility on trails.",
     "image_url": "https://raymon.imgix.net/userdata/dcshop/images/676756_raymon-vamok-pro-smokelavenderblack-side.png" + IMG_PARAMS,
     "specs": {"frame": "Alluminio 6061 / 6061 aluminium", "motor": "Bosch Performance Line CX (Gen 5), 120 Nm",
               "battery": "Bosch PowerTube 800 Wh, estraibile / removable",
               "suspension": "RockShox Domain Gold R 160 mm – Super Deluxe Select 160 mm",
               "groupset": "Shimano Deore XT 12v (10-51T)", "brakes": "Magura Louise Elite 4 pistoncini, 203 mm / 4-piston, 203 mm",
               "wheels": "29\" – 27,5\" (mullet)", "weight": "25,9 kg"},
     "stock": {"S": 0, "M": 2, "L": 2, "XL": 0}},
]
# Previous demo bikes, replaced by the shop's real Raymon fleet.
DEMO_BIKE_NAMES = ["Bianchi Arcadex GRX", "Specialized Turbo Creo", "Specialized Turbo Creo 2", "Orbea Wild H30",
                   "Ghost E-Riot AM", "Cannondale Topstone 2", "Orbea Vibe H30"]


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.bikes.create_index("id", unique=True)
    await db.bookings.create_index("id", unique=True)
    await db.bookings.create_index([("bike_id", 1), ("start", 1)])
    await db.payment_transactions.create_index("session_id", unique=True)
    email = os.environ["ADMIN_EMAIL"].strip().lower()
    await db.users.update_one({"email": email}, {"$setOnInsert": {
        "id": new_id(), "email": email, "name": "Admin", "role": "admin",
        "password_hash": hash_pw(os.environ["ADMIN_PASSWORD"]), "created_at": now_iso()}}, upsert=True)
    # Migration: drop bikes from the old category set (gravel/ebike/gravel_muscolare era).
    if await db.bikes.count_documents({"$or": [{"category": {"$nin": CATEGORIES}}, {"price_hour": {"$exists": True}}]}):
        await db.bikes.delete_many({})
    await db.bikes.delete_many({"name": {"$in": DEMO_BIKE_NAMES}})
    # The shop's e-MTB is the Vamok Pro (was entered as Comp).
    pro = next(b for b in SEED_BIKES if b["name"] == "Raymon Vamok Pro")
    old = await db.bikes.find_one({"name": "Raymon Vamok Comp"}, {"_id": 0, "id": 1})
    if old:
        await db.bikes.update_one({"id": old["id"]}, {"$set": {k: pro[k] for k in ("name", "description", "description_en", "image_url", "specs")}})
        await db.bookings.update_many({"bike_id": old["id"]}, {"$set": {"bike_name": pro["name"], "bike_image": pro["image_url"]}})
    if await db.bikes.count_documents({}) == 0:
        for b in SEED_BIKES:
            await db.bikes.insert_one(Bike(**b).model_dump())
    asyncio.create_task(sheet_sync_loop())


app.include_router(api)

# ---------------- i18n for error messages ----------------
EN_ERRORS = {
    "Non autenticato": "Not authenticated",
    "Sessione scaduta": "Session expired",
    "Utente non trovato": "User not found",
    "Solo amministratori": "Administrators only",
    "Email non valida": "Invalid email",
    "Email già registrata": "Email already registered",
    "Email o password errati": "Wrong email or password",
    "Sessione Google non valida": "Invalid Google session",
    "Data non valida": "Invalid date",
    "Non puoi prenotare nel passato": "You cannot book in the past",
    "Indica ora di inizio e durata": "Please choose start time and duration",
    "Durata tra 1 e 30 giorni": "Duration must be between 1 and 30 days",
    "Bici non trovata": "Bike not found",
    "Prenotazione non trovata": "Booking not found",
    "Prenotazione non annullabile": "This booking cannot be cancelled",
    "Prenotazione non pagabile": "This booking cannot be paid",
    "Pagamento non trovato": "Payment not found",
    "Webhook non valido": "Invalid webhook",
    "Nessuna modifica": "No changes",
    "Foglio Google non raggiungibile": "Google Sheet not reachable",
}


def translate_error(msg: str) -> str:
    if msg in EN_ERRORS:
        return EN_ERRORS[msg]
    m = re.match(r"Taglia (\w+) non disponibile per il periodo scelto", msg)
    if m:
        return f"Size {m.group(1)} is not available for the selected period"
    m = re.match(r"Orario disponibile (.+)", msg)
    if m:
        return f"Opening hours {m.group(1)}"
    return msg


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, str) and request.headers.get("accept-language", "").lower().startswith("en"):
        detail = translate_error(detail)
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
