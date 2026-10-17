"""Iteration 16 — Customer data + PDF contract.
Tests:
  (1) /api/bookings now requires customer data; missing -> 400, invalid -> 422 (live HTTPS, safe: rejected before insert).
  (2) In-process success flow (httpx.ASGITransport, on_booking_confirmed monkeypatched): booking persists customer + contract_accepted_at;
      GET /api/me/customer returns it; GET /api/bookings/{id}/contract.pdf authz paths; PDF text content.
  (3) Mailer: booking_email() renders the PDF link + acceptance date; contract_attachment() returns a base64 PDF; _send_once(with_contract=True)
      passes attachments to send_email (stubbed).
Cleanup: all TEST_* users/bookings deleted post-run. Real Google Sheet NOT touched.
"""
import asyncio
import base64
import os
import re
import sys
import uuid
from datetime import date, timedelta

import jwt
import pytest
import pytest_asyncio
import requests

sys.path.insert(0, "/app/backend")  # import server/mailer/contract_pdf

from .conftest import BASE_URL, h  # noqa: E402

ADMIN_EMAIL = "admin@noleggionuovo.it"
ADMIN_PASSWORD = "Admin2026!"

# Keep ONE event loop for the whole module so motor's AsyncIOMotorClient (bound at import time)
# and all async tests + fixtures share it.
pytestmark = pytest.mark.asyncio(loop_scope="module")


def _good_customer() -> dict:
    return {
        "full_name": "Mario Rossi",
        "tax_code": "RSSMRA80A01L191X",
        "birth_date": "1980-01-01",
        "address": "Via Roma 10",
        "city_zip": "Tolentino 62029",
        "nationality": "Italiana",
        "doc_type": "ci",
        "doc_number": "AX1234567",
        "doc_issuer_expiry": "Comune di Tolentino, 31/12/2030",
        "emergency_contact": "Luigi Bianchi 333 1112222",
    }


def _future_date() -> str:
    return (date.today() + timedelta(days=14)).isoformat()


# =============================================================================
# (1) LIVE HTTPS rejection tests — safe (never insert a booking)
# =============================================================================
class TestLiveRejections:
    """These are rejected before the DB insert, so no booking is created."""

    def test_missing_customer_returns_400(self, api, user_token):
        token, _ = user_token
        bike_id = api.get(f"{BASE_URL}/api/bikes").json()[0]["id"]
        contract = api.get(f"{BASE_URL}/api/contract").json()
        body = {
            "bike_id": bike_id, "size": "M", "date": _future_date(), "days": 1,
            "payment_method": "store", "phone": "3331234567",
            "contract_accepted": True, "clauses_approved": True, "privacy_accepted": True,
            "contract_version": contract["version"],
            # customer omitted on purpose
        }
        r = api.post(f"{BASE_URL}/api/bookings", json=body, headers=h(token))
        assert r.status_code == 400, r.text
        assert "contratto" in r.json()["detail"].lower() or "dati" in r.json()["detail"].lower()

    def test_invalid_customer_tax_code_returns_422(self, api, user_token):
        token, _ = user_token
        bike_id = api.get(f"{BASE_URL}/api/bikes").json()[0]["id"]
        contract = api.get(f"{BASE_URL}/api/contract").json()
        c = _good_customer()
        c["tax_code"] = "SHORT"  # fails min_length=11
        body = {
            "bike_id": bike_id, "size": "M", "date": _future_date(), "days": 1,
            "payment_method": "store", "phone": "3331234567",
            "contract_accepted": True, "clauses_approved": True, "privacy_accepted": True,
            "contract_version": contract["version"], "customer": c,
        }
        r = api.post(f"{BASE_URL}/api/bookings", json=body, headers=h(token))
        assert r.status_code == 422, r.text

    def test_invalid_customer_doc_type_returns_422(self, api, user_token):
        token, _ = user_token
        bike_id = api.get(f"{BASE_URL}/api/bikes").json()[0]["id"]
        contract = api.get(f"{BASE_URL}/api/contract").json()
        c = _good_customer()
        c["doc_type"] = "altro"  # not in Literal
        body = {
            "bike_id": bike_id, "size": "M", "date": _future_date(), "days": 1,
            "payment_method": "store", "phone": "3331234567",
            "contract_accepted": True, "clauses_approved": True, "privacy_accepted": True,
            "contract_version": contract["version"], "customer": c,
        }
        r = api.post(f"{BASE_URL}/api/bookings", json=body, headers=h(token))
        assert r.status_code == 422, r.text

    def test_invalid_birth_date_returns_422(self, api, user_token):
        token, _ = user_token
        bike_id = api.get(f"{BASE_URL}/api/bikes").json()[0]["id"]
        contract = api.get(f"{BASE_URL}/api/contract").json()
        c = _good_customer()
        c["birth_date"] = "01/01/1980"  # not YYYY-MM-DD
        body = {
            "bike_id": bike_id, "size": "M", "date": _future_date(), "days": 1,
            "payment_method": "store", "phone": "3331234567",
            "contract_accepted": True, "clauses_approved": True, "privacy_accepted": True,
            "contract_version": contract["version"], "customer": c,
        }
        r = api.post(f"{BASE_URL}/api/bookings", json=body, headers=h(token))
        assert r.status_code == 422, r.text

    def test_no_booking_created_after_rejections(self, api, user_token):
        """Verify none of the above calls created a booking for this test user."""
        token, _ = user_token
        bks = api.get(f"{BASE_URL}/api/bookings/me", headers=h(token)).json()
        assert bks == [], f"Expected no bookings, got {bks}"


# =============================================================================
# (2) In-process ASGI success + PDF authorization + PDF text
# =============================================================================
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def inproc_setup(monkeymodule):
    """Spin up ASGITransport against server.app, monkeypatch on_booking_confirmed to a no-op,
    register a TEST user, create a booking (store payment). Tear down booking + user at end.
    """
    import server
    import httpx

    hook_calls = {"n": 0}

    async def _noop(db, booking_id):
        hook_calls["n"] += 1

    monkeymodule.setattr(server, "on_booking_confirmed", _noop)

    transport = httpx.ASGITransport(app=server.app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    # register fresh user
    email = f"TEST_iter16_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/api/auth/register", json={"email": email, "password": "testpass123", "name": "Mario Rossi"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    user_id = r.json()["user"]["id"]

    bikes = (await client.get("/api/bikes")).json()
    bike_id = bikes[0]["id"]
    contract = (await client.get("/api/contract")).json()
    cust = _good_customer()
    body = {
        "bike_id": bike_id, "size": "M", "date": _future_date(), "days": 2,
        "payment_method": "store", "phone": "3331234567",
        "contract_accepted": True, "clauses_approved": True, "privacy_accepted": True,
        "contract_version": contract["version"], "customer": cust,
    }
    r = await client.post("/api/bookings", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    booking = r.json()

    yield {
        "client": client, "token": token, "user_id": user_id, "email": email,
        "booking": booking, "customer": cust, "hook_calls": hook_calls,
    }

    # Teardown: delete booking + user directly from Mongo
    await server.db.bookings.delete_one({"id": booking["id"]})
    await server.db.users.delete_one({"id": user_id})
    await client.aclose()


@pytest.fixture(scope="module")
def monkeymodule():
    from _pytest.monkeypatch import MonkeyPatch
    m = MonkeyPatch()
    yield m
    m.undo()


class TestInProcSuccess:


    async def test_booking_persists_customer_and_accepted_at(self, inproc_setup):
        bk = inproc_setup["booking"]
        assert bk["status"] == "confirmed"
        assert bk["payment_status"] == "to_pay_in_store"
        assert bk["contract_accepted_at"]
        assert bk["contract_version"]
        assert bk["customer"]["tax_code"] == "RSSMRA80A01L191X"
        assert bk["customer"]["full_name"] == "Mario Rossi"
        assert bk["customer"]["doc_type"] == "ci"
        # hook was invoked
        assert inproc_setup["hook_calls"]["n"] == 1


    async def test_me_customer_returns_saved(self, inproc_setup):
        c = inproc_setup["client"]
        r = await c.get("/api/me/customer", headers={"Authorization": f"Bearer {inproc_setup['token']}"})
        assert r.status_code == 200
        data = r.json()
        assert data["tax_code"] == "RSSMRA80A01L191X"
        assert data["birth_date"] == "1980-01-01"
        assert data["doc_type"] == "ci"


class TestPdfAuthz:


    async def test_owner_bearer_gets_pdf(self, inproc_setup):
        c = inproc_setup["client"]
        r = await c.get(f"/api/bookings/{inproc_setup['booking']['id']}/contract.pdf",
                        headers={"Authorization": f"Bearer {inproc_setup['token']}"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


    async def test_admin_bearer_gets_pdf(self, inproc_setup):
        c = inproc_setup["client"]
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        admin_tok = r.json()["token"]
        r = await c.get(f"/api/bookings/{inproc_setup['booking']['id']}/contract.pdf",
                        headers={"Authorization": f"Bearer {admin_tok}"})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


    async def test_other_user_gets_404(self, inproc_setup):
        c = inproc_setup["client"]
        other_email = f"TEST_iter16_other_{uuid.uuid4().hex[:8]}@example.com"
        r = await c.post("/api/auth/register", json={"email": other_email, "password": "testpass123", "name": "Other"})
        assert r.status_code == 200
        other_tok = r.json()["token"]
        other_uid = r.json()["user"]["id"]
        try:
            r = await c.get(f"/api/bookings/{inproc_setup['booking']['id']}/contract.pdf",
                            headers={"Authorization": f"Bearer {other_tok}"})
            assert r.status_code == 404
        finally:
            import server
            await server.db.users.delete_one({"id": other_uid})


    async def test_contract_link_token_grants_access(self, inproc_setup):
        import server
        c = inproc_setup["client"]
        bid = inproc_setup["booking"]["id"]
        tok = server.contract_link_token(bid)
        r = await c.get(f"/api/bookings/{bid}/contract.pdf?t={tok}")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


    async def test_bad_link_token_returns_404(self, inproc_setup):
        c = inproc_setup["client"]
        bid = inproc_setup["booking"]["id"]
        r = await c.get(f"/api/bookings/{bid}/contract.pdf?t=not-a-token")
        assert r.status_code == 404


    async def test_other_booking_token_returns_404(self, inproc_setup):
        import server
        c = inproc_setup["client"]
        bid = inproc_setup["booking"]["id"]
        tok_for_other = server.contract_link_token("some-other-booking-id-xyz")
        r = await c.get(f"/api/bookings/{bid}/contract.pdf?t={tok_for_other}")
        assert r.status_code == 404


    async def test_contract_token_rejected_as_bearer(self, inproc_setup):
        import server
        c = inproc_setup["client"]
        bid = inproc_setup["booking"]["id"]
        tok = server.contract_link_token(bid)
        r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401


class TestPdfContent:


    async def test_pdf_text_contains_customer_and_acceptance(self, inproc_setup):
        from pypdf import PdfReader
        import io
        c = inproc_setup["client"]
        bid = inproc_setup["booking"]["id"]
        r = await c.get(f"/api/bookings/{bid}/contract.pdf",
                        headers={"Authorization": f"Bearer {inproc_setup['token']}"})
        assert r.status_code == 200
        reader = PdfReader(io.BytesIO(r.content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        assert "Mario Rossi" in text
        assert "RSSMRA80A01L191X" in text
        assert "ACCETTAZIONE ELETTRONICA IN APP" in text
        # Acceptance date in Europe/Rome; must match DD/MM/YYYY pattern
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ts = datetime.fromisoformat(inproc_setup["booking"]["contract_accepted_at"]).astimezone(ZoneInfo("Europe/Rome"))
        day = ts.strftime("%d/%m/%Y")
        assert day in text, f"Expected acceptance date {day} in PDF"


# =============================================================================
# (3) Mailer tests
# =============================================================================
class TestMailer:


    async def test_booking_email_includes_pdf_link_and_date(self, inproc_setup):
        import mailer, server
        # fetch the booking as it is in the DB (has public_base saved)
        bk = await server.db.bookings.find_one({"id": inproc_setup["booking"]["id"]}, {"_id": 0})
        # Force a public_base so contract_url builds a link
        bk["public_base"] = "https://bici-disponibili.preview.emergentagent.com"
        subject, html = mailer.booking_email(bk)
        assert "Scarica il contratto (PDF)" in html
        assert f"/api/bookings/{bk['id']}/contract.pdf?t=" in html
        from datetime import datetime
        from zoneinfo import ZoneInfo
        day = datetime.fromisoformat(bk["contract_accepted_at"]).astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y")
        assert day in html


    async def test_contract_attachment_returns_pdf(self, inproc_setup):
        import mailer, server
        bk = await server.db.bookings.find_one({"id": inproc_setup["booking"]["id"]}, {"_id": 0})
        contract = await server.db.contracts.find_one({"version": bk["contract_version"]}, {"_id": 0, "lines": 1})
        atts = mailer.contract_attachment(bk, contract["lines"])
        assert len(atts) == 1
        assert atts[0]["filename"].startswith("contratto-")
        assert atts[0]["filename"].endswith(".pdf")
        decoded = base64.b64decode(atts[0]["content"])
        assert decoded[:4] == b"%PDF"


    async def test_send_once_passes_attachments(self, inproc_setup, monkeypatch):
        """_send_once with with_contract=True must forward attachments to send_email."""
        import mailer, server
        bid = inproc_setup["booking"]["id"]
        # Reset flag so _send_once will actually run
        await server.db.bookings.update_one({"id": bid}, {"$set": {"confirmation_email_sent": False}})

        captured = {}

        async def stub_send_email(*, to, subject, html, attachments=None):
            captured["to"] = to
            captured["subject"] = subject
            captured["html"] = html
            captured["attachments"] = attachments or []
            return True

        monkeypatch.setattr(mailer, "send_email", stub_send_email)

        await mailer._send_once(server.db, bid, "confirmation_email_sent", {"status": "confirmed"},
                                mailer.booking_email, "user_email", with_contract=True)

        assert captured.get("to", "").lower() == inproc_setup["email"].lower()
        assert len(captured.get("attachments", [])) == 1
        att = captured["attachments"][0]
        assert att["filename"].endswith(".pdf")
        assert base64.b64decode(att["content"])[:4] == b"%PDF"
