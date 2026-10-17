"""Booking confirmation emails via Emergent managed email (Resend)."""
import asyncio
import ipaddress
import logging
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from sheet_writer import push_booking

logger = logging.getLogger(__name__)

EMAIL_BASE_URL = "https://integrations.emergentagent.com"

# ---------------- Guardrail gate (from playbook, unchanged) ----------------
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str) -> bool:
    """Background-safe send: logs failures instead of raising."""
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": os.environ["EMAIL_FROM_NAME"]}
    if os.environ.get("EMAIL_REPLY_TO"):
        payload["contact_email"] = os.environ["EMAIL_REPLY_TO"]
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                             headers={"X-Email-Key": os.environ["EMERGENT_EMAIL_KEY"]}, json=payload)
        if r.status_code >= 400:
            try:
                info = r.json()
            except ValueError:
                info = r.text
            logger.warning("Email send failed (%s): %s", r.status_code, info)
            return False
        return True
    except Exception as e:
        logger.warning("Email send error: %s", e)
        return False


# ---------------- Booking confirmation ----------------
def _it(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


SHOP_ADDRESS = "Contrada Le Grazie 43, Tolentino (MC)"
SHOP_PHONE = "328 983 2243"
SHOP_TZ = ZoneInfo("Europe/Rome")
REMINDER_HOUR = 12
REVIEW_URL = "https://g.page/r/CRrkPKDBIM0oEBM/review"


def _rows(bk: dict, extra: list | None = None) -> list:
    days = int(bk.get("units") or 1)
    return [
        ("Codice prenotazione", bk.get("sheet_id")),
        *(extra or []),
        ("Bici", f'{bk["bike_name"]} – taglia {bk["size"]}'),
        ("Ritiro", f'{_it(bk["start"])} (dalle 9:00)'),
        ("Riconsegna", f'{_it(bk["end"])} (entro le 19:00)'),
        ("Durata", f'{days} giorn{"o" if days == 1 else "i"}'),
        ("Totale", f'€ {bk["total"]:.2f}'),
        ("Pagamento", "Pagato con carta ✅" if bk["payment_status"] == "paid" else "Da pagare in negozio al ritiro"),
    ]


def _card(title: str, intro: str, rows: list, outro: str = "") -> str:
    brand = escape(os.environ["EMAIL_FROM_NAME"])
    table = "".join(
        f'<tr><td style="padding:8px 0;color:#666;width:45%">{escape(k)}</td>'
        f'<td style="padding:8px 0;font-weight:bold;color:#111">{escape(str(v))}</td></tr>'
        for k, v in rows if v)
    return (
        '<table role="presentation" width="100%" style="background:#f4f4f4"><tr><td align="center" style="padding:24px">'
        '<table role="presentation" width="100%" style="max-width:560px;background:#ffffff;border-radius:12px;'
        'font-family:Arial,sans-serif;font-size:15px;color:#222">'
        f'<tr><td style="padding:24px 24px 0"><h2 style="margin:0;color:#111">{escape(title)}</h2></td></tr>'
        f'<tr><td style="padding:16px 24px"><p>{intro}</p>'
        f'<table role="presentation" width="100%" style="border-top:1px solid #eee;border-bottom:1px solid #eee">{table}</table>'
        f'{outro}</td></tr>'
        f'<tr><td style="padding:0 24px 24px;font-size:12px;color:#888">Inviato da {brand}. '
        f'Non ti chiederemo mai password o dati della carta via email.</td></tr>'
        '</table></td></tr></table>'
    )


def _contact() -> str:
    reply = os.environ.get("EMAIL_REPLY_TO", "")
    mail = f' · <a href="mailto:{escape(reply)}">{escape(reply)}</a>' if reply else ""
    return (f'<p><strong>Negozio:</strong> {escape(SHOP_ADDRESS)}<br>'
            f'<strong>Tel.</strong> <a href="tel:+39{SHOP_PHONE.replace(" ", "")}">{SHOP_PHONE}</a>{mail}</p>')


def _subject(prefix: str, bk: dict) -> str:
    code = bk.get("sheet_id")
    return f"{prefix}{' ' + code if code else ''} – {os.environ['EMAIL_FROM_NAME']}"


def booking_email(bk: dict) -> tuple[str, str]:
    brand = escape(os.environ["EMAIL_FROM_NAME"])
    html = _card("Prenotazione confermata 🚲",
                 f'Ciao {escape(bk["user_name"])}, grazie per aver prenotato con {brand}! Ecco il riepilogo:',
                 _rows(bk),
                 "<p>Hai accettato il contratto di noleggio in app. Porta con te un documento d'identità al momento del ritiro.</p>"
                 + _contact())
    return _subject("Prenotazione confermata", bk), html


def shop_email(bk: dict) -> tuple[str, str]:
    html = _card("Nuova prenotazione dall'app 📥",
                 "È arrivata una nuova prenotazione confermata:",
                 _rows(bk, [("Cliente", bk["user_name"]), ("Email cliente", bk["user_email"]),
                            ("Telefono", bk.get("phone")), ("Unità assegnata", bk.get("unit_id")),
                            ("Contratto", "Accettato in app ✅" if bk.get("contract_accepted_at") else None)]))
    return _subject("Nuova prenotazione", bk), html


def reminder_email(bk: dict) -> tuple[str, str]:
    html = _card("Domani si pedala! 🚴",
                 f'Ciao {escape(bk["user_name"])}, ti ricordiamo che domani ti aspettiamo per il ritiro della bici.',
                 _rows(bk),
                 "<p>Orari negozio: <strong>9:00 – 19:00</strong>. Porta con te un documento d'identità.</p>"
                 + _contact())
    return _subject("Promemoria ritiro domani", bk), html


def review_email(bk: dict) -> tuple[str, str]:
    brand = escape(os.environ["EMAIL_FROM_NAME"])
    btn = (f'<p style="text-align:center;margin:24px 0"><a href="{escape(REVIEW_URL)}" '
           'style="background:#1a8f3c;color:#ffffff;text-decoration:none;font-weight:bold;'
           'padding:14px 24px;border-radius:10px;display:inline-block">⭐ Lascia una recensione</a></p>')
    html = _card("Com'è andato il tuo giro? ⭐",
                 f'Ciao {escape(bk["user_name"])}, grazie per aver noleggiato con {brand}! '
                 'Ci farebbe molto piacere sapere com\'è andata: bastano 30 secondi.',
                 [("Bici", f'{bk["bike_name"]} – taglia {bk["size"]}'),
                  ("Noleggio", f'{_it(bk["start"])} – {_it(bk["end"])}')],
                 btn + "<p>La tua opinione aiuta altri ciclisti a scoprirci. Grazie e a presto in sella!</p>"
                 + _contact())
    return f"Com'è andato il tuo noleggio? – {os.environ['EMAIL_FROM_NAME']}", html


async def _send_once(db, booking_id: str, flag: str, query: dict, build, to_field: str | None) -> None:
    """Atomically claim `flag` on the booking, send, and release the claim if sending fails."""
    bk = await db.bookings.find_one_and_update({"id": booking_id, flag: {"$ne": True}, **query},
                                               {"$set": {flag: True}}, projection={"_id": 0})
    if not bk:
        return
    to = bk.get(to_field) if to_field else os.environ.get("SHOP_EMAIL")
    if not to:
        return
    subject, html = build(bk)
    if not await send_email(to=to, subject=subject, html=html):
        await db.bookings.update_one({"id": booking_id}, {"$set": {flag: False}})


async def on_booking_confirmed(db, booking_id: str):
    """Write the booking to the sheet (to get the NOL code), then email the customer and the shop once."""
    await push_booking(db, booking_id)
    q = {"status": "confirmed"}
    await _send_once(db, booking_id, "confirmation_email_sent", q, booking_email, "user_email")
    await _send_once(db, booking_id, "shop_email_sent", q, shop_email, None)


async def send_due_reminders(db) -> int:
    """From 12:00 (Italy time): remind customers whose pickup is tomorrow and
    ask for a review from those who returned the bike yesterday."""
    now = datetime.now(SHOP_TZ)
    if now.hour < REMINDER_HOUR:
        return 0
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    jobs = [
        ("reminder_email_sent", reminder_email,
         {"status": "confirmed", "source": "app", "start": {"$regex": f"^{tomorrow}"}}),
        ("review_email_sent", review_email,
         {"status": {"$in": ["confirmed", "completed"]}, "source": "app", "end": {"$regex": f"^{yesterday}"}}),
    ]
    sent = 0
    for flag, build, q in jobs:
        for bid in await db.bookings.distinct("id", {**q, flag: {"$ne": True}}):
            await _send_once(db, bid, flag, q, build, "user_email")
            sent += 1
    return sent


async def reminder_loop(db):
    while True:
        try:
            await send_due_reminders(db)
        except Exception as e:
            logger.warning("Reminder loop error: %s", e)
        await asyncio.sleep(600)
