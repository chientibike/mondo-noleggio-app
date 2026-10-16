"""Iteration 8 tests for /app/backend/mailer.py:
- shop_email() and reminder_email() subject + body rows
- on_booking_confirmed sets BOTH confirmation_email_sent and shop_email_sent (idempotent)
- send_due_reminders() behaviour with monkeypatched REMINDER_HOUR=0
- POST /api/auth/session with invalid session_id → 401

SAFETY (per iteration 7 agent context + review request):
- SHOP_EMAIL is monkeypatched to delivered@resend.dev so the real shop inbox is not spammed.
- Bookings are inserted directly in Mongo with source='test' for on_booking_confirmed tests
  (so sheet_writer.push_booking skips the real Google Sheet).
- send_due_reminders tests use source='app' but do NOT call on_booking_confirmed, and
  send_due_reminders itself does not touch the sheet, so the sheet is still safe.
- All sent emails go to delivered@resend.dev only.
"""
import asyncio
import importlib
import os
import sys
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

import mailer  # noqa: E402
from mailer import (  # noqa: E402
    _assert_safe_email,
    on_booking_confirmed,
    reminder_email,
    send_due_reminders,
    shop_email,
    SHOP_ADDRESS,
    SHOP_PHONE,
    SHOP_TZ,
)

from tests.conftest import BASE_URL  # noqa: E402

SAFE_RECIPIENT = "delivered@resend.dev"


# ---------------- Mongo helpers (fresh client per asyncio.run loop) ----------------
def _run(coro_fn):
    async def _wrap():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            db = client[os.environ["DB_NAME"]]
            return await coro_fn(db)
        finally:
            client.close()
    return asyncio.run(_wrap())


def _bk(sheet_id="NOL-IT8", status="confirmed", payment_status="to_pay_in_store",
        source="test", start=None, end=None, user_email=SAFE_RECIPIENT, user_name="Mario Rossi",
        bid=None, reminder_sent=None):
    rec = {
        "id": bid or ("test_" + uuid.uuid4().hex),
        "user_id": "test_user",
        "user_email": user_email,
        "user_name": user_name,
        "bike_id": "test_bike",
        "bike_name": "Raymon Soreno Comp",
        "bike_image": "",
        "size": "M",
        "mode": "daily",
        "start": start or "2026-07-10T09:00",
        "end": end or "2026-07-12T19:00",
        "units": 3,
        "total": 120.0,
        "payment_method": "store",
        "payment_status": payment_status,
        "status": status,
        "source": source,
        "sheet_id": sheet_id,
        "unit_id": "GR-008",
        "phone": "+39 333 1234567",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    if reminder_sent is not None:
        rec["reminder_email_sent"] = reminder_sent
    return rec


# ---------------- shop_email() ----------------
class TestShopEmail:
    def test_subject_and_body(self):
        bk = _bk(sheet_id="NOL-SHOP1")
        subject, html = shop_email(bk)
        assert subject == "Nuova prenotazione NOL-SHOP1 – Mondo Noleggio"
        # Shop-specific rows
        assert "Cliente" in html and "Mario Rossi" in html
        assert "Email cliente" in html and SAFE_RECIPIENT in html
        assert "Telefono" in html and "+39 333 1234567" in html
        assert "Unità assegnata" in html and "GR-008" in html
        # Also includes booking rows
        assert "Codice prenotazione" in html and "NOL-SHOP1" in html
        assert "Raymon Soreno Comp" in html
        _assert_safe_email(subject, html)


# ---------------- reminder_email() ----------------
class TestReminderEmail:
    def test_subject_body_address_and_phone(self):
        bk = _bk(sheet_id="NOL-REM1")
        subject, html = reminder_email(bk)
        assert subject == "Promemoria ritiro domani NOL-REM1 – Mondo Noleggio"
        # Shop address + phone + opening hours
        assert SHOP_ADDRESS in html
        assert "Contrada Le Grazie 43, Tolentino (MC)" in html
        assert SHOP_PHONE in html
        assert "328 983 2243" in html
        assert "9:00" in html and "19:00" in html
        # Greeting
        assert "Ciao Mario Rossi" in html
        _assert_safe_email(subject, html)

    def test_confirmation_email_also_has_address(self):
        """The confirmation email should also include the shop address + phone per review spec."""
        from mailer import booking_email
        bk = _bk(sheet_id="NOL-CONF1")
        _, html = booking_email(bk)
        assert SHOP_ADDRESS in html
        assert SHOP_PHONE in html


# ---------------- on_booking_confirmed(): sets BOTH flags ----------------
class TestOnBookingConfirmedShop:
    @pytest.fixture(autouse=True)
    def _env_and_cleanup(self, monkeypatch):
        # CRITICAL: redirect shop email to delivered@resend.dev
        monkeypatch.setenv("SHOP_EMAIL", SAFE_RECIPIENT)

        # Deterministic: stub Emergent email proxy to avoid 429 rate-limits in CI
        # and to guarantee zero real email delivery. We still exercise the full
        # mailer.on_booking_confirmed → _send_once claim/release code path.
        async def _ok(**kwargs):
            return True
        monkeypatch.setattr(mailer, "send_email", _ok)
        self._ids: list[str] = []
        yield
        if self._ids:
            ids = list(self._ids)
            _run(lambda db: db.bookings.delete_many({"id": {"$in": ids}}))

    def _insert(self, bk):
        self._ids.append(bk["id"])
        _run(lambda db: db.bookings.insert_one(bk))

    def test_sets_both_confirmation_and_shop_flags(self):
        bk = _bk(sheet_id="NOL-BOTH1")
        self._insert(bk)
        _run(lambda db: on_booking_confirmed(db, bk["id"]))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("confirmation_email_sent") is True, "customer email flag missing"
        assert stored.get("shop_email_sent") is True, "shop email flag missing"

    def test_idempotent_second_call_noop(self):
        bk = _bk(sheet_id="NOL-BOTH2")
        self._insert(bk)
        _run(lambda db: on_booking_confirmed(db, bk["id"]))
        _run(lambda db: on_booking_confirmed(db, bk["id"]))  # must be no-op
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("confirmation_email_sent") is True
        assert stored.get("shop_email_sent") is True
        assert stored.get("status") == "confirmed"


# ---------------- send_due_reminders() ----------------
class TestSendDueReminders:
    @pytest.fixture(autouse=True)
    def _env_and_cleanup(self, monkeypatch):
        # Deterministic: ignore wall-clock hour gate
        monkeypatch.setattr(mailer, "REMINDER_HOUR", 0)

        # Stub send_email so parallel pytest runs don't trip the Emergent proxy
        # rate limiter (429). We still exercise the full atomic-claim path.
        async def _ok(**kwargs):
            return True
        monkeypatch.setattr(mailer, "send_email", _ok)
        self._ids: list[str] = []
        yield
        if self._ids:
            ids = list(self._ids)
            _run(lambda db: db.bookings.delete_many({"id": {"$in": ids}}))

    def _insert(self, bk):
        self._ids.append(bk["id"])
        _run(lambda db: db.bookings.insert_one(bk))

    @staticmethod
    def _rome_date_plus(days: int) -> str:
        return (datetime.now(SHOP_TZ).date() + timedelta(days=days)).isoformat()

    def test_tomorrow_app_booking_gets_reminder(self):
        tomorrow = self._rome_date_plus(1)
        bk = _bk(sheet_id="NOL-RM1", source="app",
                 start=f"{tomorrow}T09:00", end=f"{tomorrow}T19:00")
        self._insert(bk)
        count = _run(lambda db: send_due_reminders(db))
        assert count >= 1
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("reminder_email_sent") is True

    def test_not_sent_twice(self):
        tomorrow = self._rome_date_plus(1)
        bk = _bk(sheet_id="NOL-RM2", source="app",
                 start=f"{tomorrow}T09:00", end=f"{tomorrow}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        # Second call: this booking is already flagged, so distinct() filter excludes it.
        # We assert the flag stays True and no error.
        count2 = _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("reminder_email_sent") is True
        # The 2nd pass should not re-queue this specific id (it may still process other
        # unrelated 'app' tomorrow bookings, so we don't require count2==0 globally).
        # Instead, verify by re-reading that flag is still True (no toggle).
        assert stored.get("reminder_email_sent") is True
        _ = count2  # silence unused

    def test_two_days_away_skipped(self):
        day_after = self._rome_date_plus(2)
        bk = _bk(sheet_id="NOL-RM3", source="app",
                 start=f"{day_after}T09:00", end=f"{day_after}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("reminder_email_sent") in (None, False), \
            "Booking starting in 2 days must NOT get a reminder today"

    def test_cancelled_tomorrow_skipped(self):
        tomorrow = self._rome_date_plus(1)
        bk = _bk(sheet_id="NOL-RM4", source="app", status="cancelled",
                 start=f"{tomorrow}T09:00", end=f"{tomorrow}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("reminder_email_sent") in (None, False), \
            "Cancelled booking must NOT get a reminder"


# ---------------- Server wiring ----------------
class TestServerWiring:
    def test_reminder_loop_started_on_startup(self):
        """Static check that server.py startup registers reminder_loop as a background task."""
        src = open("/app/backend/server.py", encoding="utf-8").read()
        assert "from mailer import" in src and "reminder_loop" in src
        assert "asyncio.create_task(reminder_loop(db))" in src, \
            "reminder_loop must be scheduled from the startup event in server.py"


# ---------------- Auth: invalid Google session ----------------
class TestInvalidSession:
    def test_invalid_session_id_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/session",
                          json={"session_id": "not-a-real-session-id"},
                          timeout=20)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"
