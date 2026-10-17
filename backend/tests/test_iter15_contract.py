"""Iteration 15: Rental contract endpoint and booking contract acceptance gating.

Covers:
- GET /api/contract -> 200 with 16-hex version and lines[]; first line contains 'CONTRATTO DI NOLEGGIO'
- POST /api/bookings rejections (NO booking created):
    * payment_method=stripe -> 400 'a breve'
    * store without contract_accepted -> 400
    * all consents true but clauses_approved/privacy_accepted false -> 400
    * all consents true but contract_version='deadbeef' -> 409
- Success path IN-PROCESS ONLY (asgi, on_booking_confirmed monkeypatched to no-op):
    store booking with all consents + real version -> 200
    booking doc has contract_version and contract_accepted_at
    then DELETE the booking doc from Mongo (direct, so nothing hits the real sheet)
"""
import asyncio
import os
import re
import uuid
import pytest
import requests
import httpx

from .conftest import BASE_URL, h

HEX16 = re.compile(r"^[0-9a-f]{16}$")


# ---------- live HTTP tests (safe: no booking is ever created) ----------

class TestContractEndpoint:
    def test_contract_shape(self, api):
        r = api.get(f"{BASE_URL}/api/contract")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "version" in data and "lines" in data
        assert isinstance(data["version"], str)
        assert HEX16.match(data["version"]), f"version must be 16 hex chars, got {data['version']!r}"
        assert isinstance(data["lines"], list) and len(data["lines"]) >= 3
        assert "CONTRATTO DI NOLEGGIO" in data["lines"][0], f"first line was: {data['lines'][0]!r}"


class TestBookingRejections:
    """These must all FAIL — if they return 200 we have a leak into the real Google Sheet."""

    def _payload(self, bike_id, **overrides):
        from datetime import date, timedelta
        p = {
            "bike_id": bike_id,
            "size": "M",
            "mode": "daily",
            "date": (date.today() + timedelta(days=14)).isoformat(),
            "days": 1,
            "payment_method": "store",
            "phone": "3331234567",
            "contract_accepted": True,
            "clauses_approved": True,
            "privacy_accepted": True,
            "contract_version": None,
        }
        p.update(overrides)
        return p

    @pytest.fixture
    def bike_id(self, api):
        r = api.get(f"{BASE_URL}/api/bikes")
        assert r.status_code == 200, r.text
        bikes = r.json()
        assert bikes, "no bikes seeded"
        # pick one with available M stock
        for b in bikes:
            if int(b.get("stock", {}).get("M", 0)) > 0:
                return b["id"]
        return bikes[0]["id"]

    @pytest.fixture
    def real_version(self, api):
        return api.get(f"{BASE_URL}/api/contract").json()["version"]

    def test_stripe_rejected(self, api, user_token, bike_id, real_version):
        token, _ = user_token
        payload = self._payload(bike_id, payment_method="stripe", contract_version=real_version)
        r = api.post(f"{BASE_URL}/api/bookings", json=payload, headers=h(token))
        assert r.status_code == 400, r.text
        assert "a breve" in r.json()["detail"].lower(), r.text

    def test_store_without_contract_accepted(self, api, user_token, bike_id, real_version):
        token, _ = user_token
        payload = self._payload(bike_id, contract_accepted=False, contract_version=real_version)
        r = api.post(f"{BASE_URL}/api/bookings", json=payload, headers=h(token))
        assert r.status_code == 400, r.text
        assert "contratto" in r.json()["detail"].lower()

    def test_store_without_clauses(self, api, user_token, bike_id, real_version):
        token, _ = user_token
        payload = self._payload(bike_id, clauses_approved=False, contract_version=real_version)
        r = api.post(f"{BASE_URL}/api/bookings", json=payload, headers=h(token))
        assert r.status_code == 400, r.text

    def test_store_without_privacy(self, api, user_token, bike_id, real_version):
        token, _ = user_token
        payload = self._payload(bike_id, privacy_accepted=False, contract_version=real_version)
        r = api.post(f"{BASE_URL}/api/bookings", json=payload, headers=h(token))
        assert r.status_code == 400, r.text

    def test_store_bad_contract_version(self, api, user_token, bike_id):
        token, _ = user_token
        payload = self._payload(bike_id, contract_version="deadbeef")
        r = api.post(f"{BASE_URL}/api/bookings", json=payload, headers=h(token))
        assert r.status_code == 409, r.text
        assert "contratto" in r.json()["detail"].lower()

    def test_store_missing_contract_version(self, api, user_token, bike_id):
        token, _ = user_token
        payload = self._payload(bike_id, contract_version=None)
        r = api.post(f"{BASE_URL}/api/bookings", json=payload, headers=h(token))
        assert r.status_code == 400, r.text

    def test_no_booking_leaked_to_real_sheet(self, api, user_token):
        """After all rejection tests, the test user must have ZERO bookings in Mongo."""
        token, _ = user_token
        r = api.get(f"{BASE_URL}/api/bookings/me", headers=h(token))
        assert r.status_code == 200, r.text
        assert r.json() == [], f"LEAK: a rejection test created a booking: {r.json()}"


# ---------- in-process success path (ASGI + monkeypatched mailer) ----------

@pytest.mark.asyncio
async def test_in_process_success_store_booking(monkeypatch):
    """Create a store booking in-process so we can monkeypatch on_booking_confirmed
    (prevents any Google-Sheet write and any email). Clean up the booking doc directly from Mongo."""
    import sys
    sys.path.insert(0, "/app/backend")
    import server  # noqa: E402

    noop_called = {"n": 0}

    async def _noop(db, booking_id):
        noop_called["n"] += 1

    monkeypatch.setattr(server, "on_booking_confirmed", _noop)

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        # 1) create a fresh user via live register endpoint (in-process)
        email = f"TEST_iter15_{uuid.uuid4().hex[:8]}@example.com"
        r = await c.post("/api/auth/register",
                         json={"email": email, "password": "testpass123", "name": "Iter15 Tester"})
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        # 2) get a bike with M stock
        bikes = (await c.get("/api/bikes")).json()
        bike = next((b for b in bikes if int(b.get("stock", {}).get("M", 0)) > 0), bikes[0])

        # 3) get real contract version
        version = (await c.get("/api/contract")).json()["version"]

        # 3b) upload the two mandatory ID document photos
        from .test_iter13_upload import _tiny_png
        png = _tiny_png()
        doc_ids = []
        for side in ("front", "back"):
            r = await c.post("/api/me/id-document",
                             files={"file": (f"{side}.png", png, "image/png")},
                             headers=auth)
            assert r.status_code == 200, r.text
            doc_ids.append(r.json()["id"])

        customer = {
            "full_name": "Mario Rossi", "tax_code": "RSSMRA80A01L191X",
            "birth_date": "1980-01-01", "address": "Via Roma 10",
            "city_zip": "Tolentino 62029", "nationality": "Italiana",
            "doc_type": "ci", "doc_number": "AX1234567",
            "doc_issuer_expiry": "Comune, 31/12/2030", "emergency_contact": "",
            "doc_front_id": doc_ids[0], "doc_back_id": doc_ids[1],
        }

        # 4) book
        from datetime import date, timedelta
        payload = {
            "bike_id": bike["id"],
            "size": "M",
            "mode": "daily",
            "date": (date.today() + timedelta(days=20)).isoformat(),
            "days": 1,
            "payment_method": "store",
            "phone": "3339876543",
            "contract_accepted": True,
            "clauses_approved": True,
            "privacy_accepted": True,
            "contract_version": version,
            "customer": customer,
        }
        r = await c.post("/api/bookings", json=payload, headers=auth)
        assert r.status_code == 200, r.text
        booking = r.json()
        assert booking["contract_version"] == version
        assert booking["contract_accepted_at"], "contract_accepted_at must be set"
        assert booking["status"] == "confirmed"
        assert booking["payment_status"] == "to_pay_in_store"
        booking_id = booking["id"]

    # 5) give the create_task(on_booking_confirmed) a tick to run (it's our no-op)
    await asyncio.sleep(0.1)
    assert noop_called["n"] == 1, "on_booking_confirmed monkeypatch was NOT invoked"

    # Teardown: delete booking doc + the test user + uploaded docs directly from Mongo
    res = await server.db.bookings.delete_one({"id": booking_id})
    assert res.deleted_count == 1
    await server.db.users.delete_one({"email": email})
    await server.db.files.delete_many({"id": {"$in": doc_ids}})

    # 7) verify DB truly clean
    assert await server.db.bookings.find_one({"id": booking_id}) is None
    assert await server.db.users.find_one({"email": email}) is None
