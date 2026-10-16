"""Full backend regression test suite for Noleggio Nuovo"""
import os, uuid, datetime, requests, pytest
from conftest import BASE_URL, h

# ------------------- Health / meta -------------------
class TestMeta:
    def test_meta(self, api):
        r = api.get(f"{BASE_URL}/api/meta")
        assert r.status_code == 200
        data = r.json()
        assert data["sizes"] == ["S", "M", "L", "XL"]
        assert set(data["categories"]) == {"gravel", "ebike", "gravel_muscolare"}
        assert data["open_hour"] == 9 and data["close_hour"] == 19

# ------------------- Auth -------------------
class TestAuth:
    def test_register_login_me(self, api):
        email = f"TEST_auth_{uuid.uuid4().hex[:8]}@example.com"
        r = api.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "secret12", "name": "Mario"})
        assert r.status_code == 200
        token = r.json()["token"]
        assert r.json()["user"]["email"] == email.lower()
        # duplicate
        r2 = api.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "secret12", "name": "Mario"})
        assert r2.status_code == 409
        # login
        rl = api.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "secret12"})
        assert rl.status_code == 200
        # me
        rm = api.get(f"{BASE_URL}/api/auth/me", headers=h(token))
        assert rm.status_code == 200
        assert rm.json()["role"] == "user"

    def test_login_bad(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login", json={"email": "nope@x.com", "password": "x"})
        assert r.status_code == 401

    def test_me_requires_auth(self, api):
        r = api.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_admin_login(self, admin_token):
        assert admin_token

# ------------------- Bikes -------------------
class TestBikes:
    def test_list_all(self, api):
        r = api.get(f"{BASE_URL}/api/bikes")
        assert r.status_code == 200
        bikes = r.json()
        assert len(bikes) >= 1
        b = bikes[0]
        for k in ("id", "name", "category", "price_hour", "price_day", "stock", "available"):
            assert k in b, f"missing {k}"

    def test_filter_category(self, api):
        r = api.get(f"{BASE_URL}/api/bikes", params={"category": "ebike"})
        assert r.status_code == 200
        for b in r.json():
            assert b["category"] == "ebike"

    def test_get_detail(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        r = api.get(f"{BASE_URL}/api/bikes/{bid}")
        assert r.status_code == 200
        assert r.json()["id"] == bid

    def test_get_not_found(self, api):
        r = api.get(f"{BASE_URL}/api/bikes/nonexistent-id")
        assert r.status_code == 404

    def test_quote_hourly(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        r = api.post(f"{BASE_URL}/api/bikes/{bid}/quote", json={
            "bike_id": bid, "size": "M", "mode": "hourly",
            "date": tomorrow, "start_hour": 10, "hours": 3, "payment_method": "store"})
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["units"] == 3
        assert q["total"] == round(bikes[0]["price_hour"] * 3, 2)

    def test_quote_outside_hours(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        r = api.post(f"{BASE_URL}/api/bikes/{bid}/quote", json={
            "bike_id": bid, "size": "M", "mode": "hourly",
            "date": tomorrow, "start_hour": 18, "hours": 3, "payment_method": "store"})
        assert r.status_code == 422

    def test_quote_past_date(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        r = api.post(f"{BASE_URL}/api/bikes/{bid}/quote", json={
            "bike_id": bid, "size": "M", "mode": "hourly",
            "date": "2020-01-01", "start_hour": 10, "hours": 2, "payment_method": "store"})
        assert r.status_code == 422

# ------------------- Bookings -------------------
class TestBookings:
    def _create_booking(self, api, user_token, mode="daily", days=1, hours=None, start_hour=None, size="M"):
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        tomorrow = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
        payload = {"bike_id": bid, "size": size, "mode": mode, "date": tomorrow, "payment_method": "store"}
        if mode == "hourly":
            payload["start_hour"] = start_hour or 10
            payload["hours"] = hours or 2
        else:
            payload["days"] = days
        r = api.post(f"{BASE_URL}/api/bookings", json=payload, headers=h(token))
        return r, bid

    def test_create_daily_store(self, api, user_token):
        r, _ = self._create_booking(api, user_token, mode="daily", days=1)
        assert r.status_code == 200, r.text
        bk = r.json()
        assert bk["status"] == "confirmed"
        assert bk["payment_status"] == "to_pay_in_store"

    def test_create_hourly(self, api, user_token):
        r, _ = self._create_booking(api, user_token, mode="hourly", hours=2, start_hour=11)
        assert r.status_code == 200, r.text

    def test_create_requires_auth(self, api, user_token):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        r = api.post(f"{BASE_URL}/api/bookings", json={
            "bike_id": bid, "size": "M", "mode": "daily", "date": tomorrow, "days": 1, "payment_method": "store"})
        assert r.status_code == 401

    def test_stock_decreases_409_when_exhausted(self, api, user_token):
        """Book all XL stock then try one more -> 409"""
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        # Find a bike with low XL stock
        target = next((b for b in bikes if 0 < b["stock"].get("XL", 0) <= 2), None)
        if not target:
            pytest.skip("No bike with limited XL stock for test")
        bid = target["id"]
        xl_stock = target["stock"]["XL"]
        day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
        # Fill XL stock
        for _ in range(xl_stock):
            r = api.post(f"{BASE_URL}/api/bookings", json={
                "bike_id": bid, "size": "XL", "mode": "daily", "date": day, "days": 1,
                "payment_method": "store"}, headers=h(token))
            assert r.status_code == 200, r.text
        # One more should 409
        r = api.post(f"{BASE_URL}/api/bookings", json={
            "bike_id": bid, "size": "XL", "mode": "daily", "date": day, "days": 1,
            "payment_method": "store"}, headers=h(token))
        assert r.status_code == 409, r.text

    def test_my_bookings_and_cancel(self, api, user_token):
        token, _ = user_token
        r_create, _ = self._create_booking(api, user_token, mode="daily", days=1)
        bid = r_create.json()["id"]
        r = api.get(f"{BASE_URL}/api/bookings/me", headers=h(token))
        assert r.status_code == 200
        assert any(b["id"] == bid for b in r.json())
        # cancel
        rc = api.post(f"{BASE_URL}/api/bookings/{bid}/cancel", headers=h(token))
        assert rc.status_code == 200
        assert rc.json()["status"] == "cancelled"
        # cancel again -> 409
        rc2 = api.post(f"{BASE_URL}/api/bookings/{bid}/cancel", headers=h(token))
        assert rc2.status_code == 409

# ------------------- Stripe -------------------
class TestStripe:
    def test_checkout_creates_session(self, api, user_token):
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        day = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        rb = api.post(f"{BASE_URL}/api/bookings", json={
            "bike_id": bid, "size": "M", "mode": "daily", "date": day, "days": 1, "payment_method": "stripe"},
            headers=h(token))
        assert rb.status_code == 200, rb.text
        booking_id = rb.json()["id"]
        rc = api.post(f"{BASE_URL}/api/payments/stripe/checkout", json={
            "booking_id": booking_id, "return_url": f"{BASE_URL}/api/payments/return"}, headers=h(token))
        assert rc.status_code == 200, rc.text
        js = rc.json()
        assert "stripe.com" in js["url"]
        assert js["session_id"]
        # status
        rs = api.get(f"{BASE_URL}/api/payments/stripe/status/{js['session_id']}", headers=h(token))
        assert rs.status_code == 200
        assert "payment_status" in rs.json()

# ------------------- Admin -------------------
class TestAdmin:
    def test_stats(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/stats", headers=h(admin_token))
        assert r.status_code == 200
        for k in ("bike_models", "total_units", "active_bookings", "today_bookings", "revenue_paid"):
            assert k in r.json()

    def test_stats_forbidden_for_user(self, api, user_token):
        token, _ = user_token
        r = api.get(f"{BASE_URL}/api/admin/stats", headers=h(token))
        assert r.status_code == 403

    def test_admin_bookings_list(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/bookings", headers=h(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_bookings_filter(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/bookings", headers=h(admin_token), params={"status": "confirmed"})
        assert r.status_code == 200
        for b in r.json():
            assert b["status"] == "confirmed"

    def test_admin_bike_crud(self, api, admin_token):
        payload = {"name": "TEST_Bike", "category": "gravel", "description": "test",
                   "image_url": "https://x.com/i.jpg", "price_hour": 5, "price_day": 20,
                   "stock": {"S": 1, "M": 1, "L": 1, "XL": 1}}
        rc = api.post(f"{BASE_URL}/api/admin/bikes", json=payload, headers=h(admin_token))
        assert rc.status_code == 200, rc.text
        bid = rc.json()["id"]
        # update
        payload["price_hour"] = 9
        ru = api.put(f"{BASE_URL}/api/admin/bikes/{bid}", json=payload, headers=h(admin_token))
        assert ru.status_code == 200
        assert ru.json()["price_hour"] == 9
        # verify via GET
        rg = api.get(f"{BASE_URL}/api/bikes/{bid}")
        assert rg.status_code == 200 and rg.json()["price_hour"] == 9
        # delete
        rd = api.delete(f"{BASE_URL}/api/admin/bikes/{bid}", headers=h(admin_token))
        assert rd.status_code == 200
        # verify deleted
        rg2 = api.get(f"{BASE_URL}/api/bikes/{bid}")
        assert rg2.status_code == 404

    def test_admin_bike_forbidden_for_user(self, api, user_token):
        token, _ = user_token
        r = api.post(f"{BASE_URL}/api/admin/bikes", json={
            "name": "X", "category": "gravel", "price_hour": 1, "price_day": 1,
            "stock": {"S": 0, "M": 0, "L": 0, "XL": 0}}, headers=h(token))
        assert r.status_code == 403

    def test_admin_patch_booking(self, api, admin_token, user_token):
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        day = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()
        rb = api.post(f"{BASE_URL}/api/bookings", json={
            "bike_id": bid, "size": "S", "mode": "daily", "date": day, "days": 1, "payment_method": "store"},
            headers=h(token))
        assert rb.status_code == 200
        booking_id = rb.json()["id"]
        rp = api.patch(f"{BASE_URL}/api/admin/bookings/{booking_id}", json={"payment_status": "paid"},
                       headers=h(admin_token))
        assert rp.status_code == 200
        assert rp.json()["payment_status"] == "paid"
