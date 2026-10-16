"""Tests for /app/backend/mailer.py booking confirmation emails.

CRITICAL safety rules observed:
- Only use delivered@resend.dev as recipient.
- Direct Mongo inserts with source='test' so push_booking() skips the real Google Sheet
  (sheet_writer.push_booking returns early when source != 'app').
- Test bookings are cleaned up after each test.
"""
import asyncio
import os
import sys
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Make /app/backend importable so we can import mailer directly
sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from mailer import booking_email, on_booking_confirmed, send_email, _assert_safe_email  # noqa: E402

from tests.conftest import BASE_URL, h  # noqa: E402


SAFE_RECIPIENT = "delivered@resend.dev"


# ---------------- shared Mongo helpers ----------------
# Motor binds its client to the current event loop at creation. Since every
# test opens a fresh loop via asyncio.run(), we build the client inside each
# coroutine instead of a module-scoped fixture.
def _run(coro_fn):
    """Run async coroutine with a fresh Motor client bound to this loop."""
    async def _wrap():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            db = client[os.environ["DB_NAME"]]
            return await coro_fn(db)
        finally:
            client.close()
    return asyncio.run(_wrap())


def _make_test_booking(sheet_id: str | None = "NOL-TEST001",
                       status: str = "confirmed",
                       payment_status: str = "to_pay_in_store") -> dict:
    return {
        "id": "test_" + uuid.uuid4().hex,
        "user_id": "test_user",
        "user_email": SAFE_RECIPIENT,
        "user_name": "Mario Rossi",
        "bike_id": "test_bike",
        "bike_name": "Raymon Soreno Comp",
        "bike_image": "",
        "size": "M",
        "mode": "daily",
        "start": "2026-07-10T09:00",
        "end": "2026-07-12T19:00",
        "units": 3,
        "total": 120.0,
        "payment_method": "store",
        "payment_status": payment_status,
        "status": status,
        "source": "test",      # <-- prevents push_booking from touching real sheet
        "sheet_id": sheet_id,
        "unit_id": "GR-008",
        "phone": "+39 333 1234567",
        "created_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------- booking_email() ----------------
class TestBookingEmail:
    def test_subject_and_rows_with_code(self):
        bk = _make_test_booking(sheet_id="NOL-123")
        subject, html = booking_email(bk)
        # Italian subject with code and brand
        assert subject == "Prenotazione confermata NOL-123 – Mondo Noleggio"
        # Italian section rows (store payment)
        assert "Codice prenotazione" in html and "NOL-123" in html
        assert "Bici" in html and "Raymon Soreno Comp – taglia M" in html
        assert "Ritiro" in html and "10/07/2026 (dalle 9:00)" in html
        assert "Riconsegna" in html and "12/07/2026 (entro le 19:00)" in html
        assert "Durata" in html and "3 giorni" in html
        assert "Totale" in html and "€ 120.00" in html
        assert "Pagamento" in html and "Da pagare in negozio al ritiro" in html
        # Greeting with user name and brand
        assert "Ciao Mario Rossi" in html
        assert "Mondo Noleggio" in html
        # Guardrails pass
        _assert_safe_email(subject, html)

    def test_subject_without_code_omits_code_row(self):
        bk = _make_test_booking(sheet_id=None)
        subject, html = booking_email(bk)
        # No " NOL-xxx" segment in the subject
        assert subject == "Prenotazione confermata – Mondo Noleggio"
        # Code row omitted
        assert "Codice prenotazione" not in html
        # Other rows still present
        assert "Bici" in html
        _assert_safe_email(subject, html)

    def test_paid_row_when_payment_status_paid(self):
        bk = _make_test_booking(sheet_id="NOL-999", payment_status="paid")
        bk["payment_method"] = "stripe"
        _, html = booking_email(bk)
        assert "Pagato con carta" in html
        assert "Da pagare in negozio" not in html

    def test_singular_day_label(self):
        bk = _make_test_booking()
        bk["units"] = 1
        bk["start"] = "2026-07-10T09:00"
        bk["end"] = "2026-07-10T19:00"
        _, html = booking_email(bk)
        assert "1 giorno" in html
        assert "1 giorni" not in html


# ---------------- send_email() ----------------
class TestSendEmail:
    def test_send_email_delivered_resend(self):
        subject, html = booking_email(_make_test_booking(sheet_id="NOL-SEND"))
        ok = asyncio.run(send_email(to=SAFE_RECIPIENT, subject=subject, html=html))
        assert ok is True, "Emergent email proxy should accept delivered@resend.dev"


# ---------------- on_booking_confirmed() ----------------
class TestOnBookingConfirmed:
    @pytest.fixture(autouse=True)
    def _cleanup(self):
        self._created_ids: list[str] = []
        yield
        if self._created_ids:
            ids = list(self._created_ids)
            _run(lambda db: db.bookings.delete_many({"id": {"$in": ids}}))

    def _insert(self, bk: dict):
        self._created_ids.append(bk["id"])
        _run(lambda db: db.bookings.insert_one(bk))

    def test_confirmed_booking_is_emailed_and_marked(self):
        bk = _make_test_booking(sheet_id="NOL-ONC1")
        self._insert(bk)
        _run(lambda db: on_booking_confirmed(db, bk["id"]))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored is not None
        assert stored.get("confirmation_email_sent") is True

    def test_idempotent_no_resend(self):
        bk = _make_test_booking(sheet_id="NOL-ONC2")
        self._insert(bk)
        _run(lambda db: on_booking_confirmed(db, bk["id"]))
        before = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert before.get("confirmation_email_sent") is True
        # Second call must be a no-op (idempotent) — flag stays True, status unchanged.
        _run(lambda db: on_booking_confirmed(db, bk["id"]))
        after = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert after.get("confirmation_email_sent") is True
        assert after.get("status") == "confirmed"

    def test_pending_payment_is_not_emailed(self):
        bk = _make_test_booking(sheet_id="NOL-ONC3",
                                status="pending_payment",
                                payment_status="pending")
        self._insert(bk)
        _run(lambda db: on_booking_confirmed(db, bk["id"]))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        # claim gate requires status == 'confirmed', so flag must NOT be set
        assert stored.get("confirmation_email_sent") in (None, False)


# ---------------- Regression ----------------
class TestRegression:
    def test_get_bikes_still_works(self):
        r = requests.get(f"{BASE_URL}/api/bikes", timeout=20)
        assert r.status_code == 200
        bikes = r.json()
        assert isinstance(bikes, list) and len(bikes) >= 1

    def test_auth_login_admin(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "admin@noleggionuovo.it",
                                "password": "Admin2026!"},
                          timeout=20)
        assert r.status_code == 200
        assert "token" in r.json()
        assert r.json()["user"]["role"] == "admin"
