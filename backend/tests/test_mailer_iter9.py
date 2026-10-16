"""Iteration 9 tests for /app/backend/mailer.py:
- review_email(bk): subject, review URL, button label, guardrail-safe
- send_due_reminders(db): review flow (end=yesterday) with REMINDER_HOUR=0
  * confirmed source='app' end=yesterday → review_email_sent=True
  * completed source='app' end=yesterday → review_email_sent=True
  * cancelled end=yesterday → NOT sent
  * end=today → NOT sent
  * not resent on second pass
  * iteration-8 reminder path still works (start=tomorrow)

SAFETY:
- All test bookings are inserted directly in Mongo. source='app' is required by
  send_due_reminders filter, but send_due_reminders never calls sheet_writer
  so the real Google Sheet is NOT touched.
- send_email is stubbed to True in all tests to avoid real sends.
- All recipients are delivered@resend.dev.
- Cleanup fixture deletes inserted bookings by id after each test.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

import mailer  # noqa: E402
from mailer import (  # noqa: E402
    _assert_safe_email,
    review_email,
    send_due_reminders,
    REVIEW_URL,
    SHOP_TZ,
)

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


def _bk(sheet_id="NOL-IT9", status="confirmed", source="app",
        start=None, end=None, bid=None):
    return {
        "id": bid or ("test_" + uuid.uuid4().hex),
        "user_id": "test_user",
        "user_email": SAFE_RECIPIENT,
        "user_name": "Mario Rossi",
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
        "payment_status": "to_pay_in_store",
        "status": status,
        "source": source,
        "sheet_id": sheet_id,
        "unit_id": "GR-008",
        "phone": "+39 333 1234567",
        "created_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------- review_email() ----------------
class TestReviewEmail:
    def test_subject(self):
        subject, _ = review_email(_bk(sheet_id="NOL-RV1"))
        assert subject == "Com'è andato il tuo noleggio? – Mondo Noleggio"

    def test_contains_review_url_and_label(self):
        subject, html = review_email(_bk(sheet_id="NOL-RV1"))
        assert REVIEW_URL == "https://g.page/r/CRrkPKDBIM0oEBM/review"
        assert REVIEW_URL in html
        assert "Lascia una recensione" in html
        # Button is an anchor pointing to review URL
        assert f'href="{REVIEW_URL}"' in html

    def test_passes_safe_email_guardrails(self):
        subject, html = review_email(_bk(sheet_id="NOL-RV1"))
        # Should not raise
        _assert_safe_email(subject, html)

    def test_rows_include_bike_and_rental_dates(self):
        _, html = review_email(_bk(sheet_id="NOL-RV1",
                                   start="2026-07-10T09:00",
                                   end="2026-07-12T19:00"))
        assert "Raymon Soreno Comp" in html
        assert "10/07/2026" in html
        assert "12/07/2026" in html


# ---------------- send_due_reminders(): review flow ----------------
class TestSendDueReminders_Review:
    @pytest.fixture(autouse=True)
    def _env_and_cleanup(self, monkeypatch):
        # Deterministic: ignore wall-clock hour gate
        monkeypatch.setattr(mailer, "REMINDER_HOUR", 0)

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

    def test_confirmed_end_yesterday_gets_review(self):
        yesterday = self._rome_date_plus(-1)
        bk = _bk(sheet_id="NOL-RV-C1", status="confirmed", source="app",
                 start=f"{self._rome_date_plus(-3)}T09:00",
                 end=f"{yesterday}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("review_email_sent") is True

    def test_completed_end_yesterday_gets_review(self):
        yesterday = self._rome_date_plus(-1)
        bk = _bk(sheet_id="NOL-RV-C2", status="completed", source="app",
                 start=f"{self._rome_date_plus(-3)}T09:00",
                 end=f"{yesterday}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("review_email_sent") is True

    def test_cancelled_end_yesterday_skipped(self):
        yesterday = self._rome_date_plus(-1)
        bk = _bk(sheet_id="NOL-RV-C3", status="cancelled", source="app",
                 start=f"{self._rome_date_plus(-3)}T09:00",
                 end=f"{yesterday}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("review_email_sent") in (None, False), \
            "Cancelled booking must NOT get a review email"

    def test_end_today_skipped(self):
        today = self._rome_date_plus(0)
        bk = _bk(sheet_id="NOL-RV-C4", status="confirmed", source="app",
                 start=f"{self._rome_date_plus(-2)}T09:00",
                 end=f"{today}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("review_email_sent") in (None, False), \
            "Booking ending today must NOT get a review email yet"

    def test_review_not_resent(self):
        yesterday = self._rome_date_plus(-1)
        bk = _bk(sheet_id="NOL-RV-C5", status="confirmed", source="app",
                 start=f"{self._rome_date_plus(-3)}T09:00",
                 end=f"{yesterday}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("review_email_sent") is True

    def test_iter8_reminder_still_works(self):
        """Regression: start=tomorrow confirmed source=app still gets reminder."""
        tomorrow = self._rome_date_plus(1)
        bk = _bk(sheet_id="NOL-RV-C6", status="confirmed", source="app",
                 start=f"{tomorrow}T09:00",
                 end=f"{tomorrow}T19:00")
        self._insert(bk)
        _run(lambda db: send_due_reminders(db))
        stored = _run(lambda db: db.bookings.find_one({"id": bk["id"]}, {"_id": 0}))
        assert stored.get("reminder_email_sent") is True
