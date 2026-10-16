"""Full backend regression test suite for Noleggio Nuovo - daily-only + specs (iter 3)"""
import uuid
import datetime
import pytest
import requests
from tests.conftest import BASE_URL, h


# ------------------- Meta -------------------
class TestMeta:
    def test_meta(self, api):
        r = api.get(f"{BASE_URL}/api/meta")
        assert r.status_code == 200
        data = r.json()
        assert data["sizes"] == ["S", "M", "L", "XL"]
        assert set(data["categories"]) == {"gravel", "egravel", "ebike_mtb"}
        assert data["category_prices"] == {"gravel": 40.0, "egravel": 50.0, "ebike_mtb": 60.0}
        assert data["open_hour"] == 9 and data["close_hour"] == 19


# ------------------- Auth -------------------
class TestAuth:
    def test_register_login_me(self, api):
        email = f"TEST_auth_{uuid.uuid4().hex[:8]}@example.com"
        r = api.post(f"{BASE_URL}/api/auth/register",
                     json={"email": email, "password": "secret12", "name": "Mario"})
        assert r.status_code == 200
        token = r.json()["token"]
        assert r.json()["user"]["email"] == email.lower()
        r2 = api.post(f"{BASE_URL}/api/auth/register",
                      json={"email": email, "password": "secret12", "name": "Mario"})
        assert r2.status_code == 409
        rl = api.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "secret12"})
        assert rl.status_code == 200
        rm = api.get(f"{BASE_URL}/api/auth/me", headers=h(token))
        assert rm.status_code == 200
        assert rm.json()["role"] == "user"

    def test_login_bad_it(self, api):
        """Default (no Accept-Language) returns Italian error"""
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": "nope@example.com", "password": "x"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Email o password errati"

    def test_login_bad_en(self, api):
        """Accept-Language: en translates HTTPException detail"""
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": "nope@example.com", "password": "x"},
                     headers={"Accept-Language": "en"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Wrong email or password"

    def test_me_requires_auth(self, api):
        r = api.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_me_unauth_en(self, api):
        r = api.get(f"{BASE_URL}/api/auth/me", headers={"Accept-Language": "en"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Not authenticated"


# ------------------- Bikes (seed check) -------------------
class TestBikes:
    def test_seed_three_bikes(self, api):
        r = api.get(f"{BASE_URL}/api/bikes")
        assert r.status_code == 200
        bikes = r.json()
        assert len(bikes) == 3, f"Expected 3 seeded bikes, got {len(bikes)}"
        cats = {b["category"]: b for b in bikes}
        assert set(cats.keys()) == {"gravel", "egravel", "ebike_mtb"}
        assert cats["gravel"]["price_day"] == 40
        assert cats["egravel"]["price_day"] == 50
        assert cats["ebike_mtb"]["price_day"] == 60
        for b in bikes:
            assert "price_hour" not in b, "price_hour must not exist"
            for k in ("id", "name", "category", "price_day", "stock", "available"):
                assert k in b

    def test_filter_category(self, api):
        r = api.get(f"{BASE_URL}/api/bikes", params={"category": "egravel"})
        assert r.status_code == 200
        for b in r.json():
            assert b["category"] == "egravel"

    def test_get_detail(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        r = api.get(f"{BASE_URL}/api/bikes/{bid}")
        assert r.status_code == 200
        assert r.json()["id"] == bid
        assert "price_hour" not in r.json()

    def test_get_not_found(self, api):
        r = api.get(f"{BASE_URL}/api/bikes/nonexistent-id")
        assert r.status_code == 404

    # ---- iter 3: specs + bilingual descriptions ----
    def test_seed_bikes_have_specs_and_description_en(self, api):
        """Each seeded bike has specs dict with required keys, description_en, and reachable image_url."""
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        by_cat = {b["category"]: b for b in bikes}
        # names match the iter 3 seed
        assert by_cat["gravel"]["name"] == "Raymon Soreno Comp"
        assert by_cat["egravel"]["name"] == "Raymon Norza Comp"
        assert by_cat["ebike_mtb"]["name"] == "Raymon Vamok Comp"
        for b in bikes:
            assert isinstance(b.get("specs"), dict) and len(b["specs"]) > 0, f"{b['name']} missing specs"
            assert b.get("description") and b.get("description_en"), f"{b['name']} missing bilingual desc"
            # specs values with ' / ' separator (IT / EN)
            frame = b["specs"].get("frame")
            assert frame, f"{b['name']} missing spec_frame"
        # expected keys present on at least one bike per the seed
        assert "motor" in by_cat["egravel"]["specs"] and "battery" in by_cat["egravel"]["specs"]
        assert "suspension" in by_cat["ebike_mtb"]["specs"]
        # image urls reachable
        for b in bikes:
            ri = requests.get(b["image_url"], timeout=20, allow_redirects=True)
            assert ri.status_code == 200, f"{b['name']} image {b['image_url']} -> {ri.status_code}"

    def test_admin_bike_crud_with_specs_and_description_en(self, api, admin_token):
        """POST/PUT /api/admin/bikes accepts specs + description_en and persists them."""
        payload = {
            "name": "TEST_Spec_Bike", "category": "gravel",
            "description": "IT desc", "description_en": "EN desc",
            "image_url": "https://x.com/i.jpg", "price_day": 42,
            "stock": {"S": 0, "M": 1, "L": 0, "XL": 0},
            "specs": {"frame": "Alluminio / Aluminium", "groupset": "GRX 2x11", "weight": "9,5 kg"},
        }
        rc = api.post(f"{BASE_URL}/api/admin/bikes", json=payload, headers=h(admin_token))
        assert rc.status_code == 200, rc.text
        bid = rc.json()["id"]
        body = rc.json()
        assert body["description_en"] == "EN desc"
        assert body["specs"]["frame"] == "Alluminio / Aluminium"
        assert body["specs"]["weight"] == "9,5 kg"
        # GET verifies persistence
        rg = api.get(f"{BASE_URL}/api/bikes/{bid}").json()
        assert rg["description_en"] == "EN desc"
        assert rg["specs"] == payload["specs"]
        # PUT updates specs + description_en
        payload["description_en"] = "EN desc v2"
        payload["specs"] = {"frame": "Carbonio / Carbon", "motor": "SL 1.2"}
        ru = api.put(f"{BASE_URL}/api/admin/bikes/{bid}", json=payload, headers=h(admin_token))
        assert ru.status_code == 200
        rg2 = api.get(f"{BASE_URL}/api/bikes/{bid}").json()
        assert rg2["description_en"] == "EN desc v2"
        assert rg2["specs"] == {"frame": "Carbonio / Carbon", "motor": "SL 1.2"}
        api.delete(f"{BASE_URL}/api/admin/bikes/{bid}", headers=h(admin_token))

    def test_quote_daily_default_mode(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        gravel = next(b for b in bikes if b["category"] == "gravel")
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        # omit mode -> defaults to daily
        r = api.post(f"{BASE_URL}/api/bikes/{gravel['id']}/quote",
                     json={"bike_id": gravel["id"], "size": "M",
                           "date": tomorrow, "days": 2, "payment_method": "store"})
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["units"] == 2
        assert q["total"] == 80.0
        # start 09:00 first day, end 19:00 last day
        assert q["start"].endswith("T09:00")
        assert q["end"].endswith("T19:00")
        end_date = datetime.date.fromisoformat(q["end"].split("T")[0])
        start_date = datetime.date.fromisoformat(q["start"].split("T")[0])
        assert (end_date - start_date).days == 1  # 2 days span = +1

    def test_quote_hourly_rejected(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        r = api.post(f"{BASE_URL}/api/bikes/{bid}/quote",
                     json={"bike_id": bid, "size": "M", "mode": "hourly",
                           "date": tomorrow, "days": 1, "payment_method": "store"})
        assert r.status_code == 422, r.text

    def test_quote_past_date(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        r = api.post(f"{BASE_URL}/api/bikes/{bid}/quote",
                     json={"bike_id": bid, "size": "M",
                           "date": "2020-01-01", "days": 1, "payment_method": "store"})
        assert r.status_code == 422

    def test_quote_too_long(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        r = api.post(f"{BASE_URL}/api/bikes/{bid}/quote",
                     json={"bike_id": bid, "size": "M",
                           "date": tomorrow, "days": 31, "payment_method": "store"})
        assert r.status_code == 422


# ------------------- Bookings -------------------
class TestBookings:
    def _book(self, api, user_token, days=1, size="M", pay="store", offset=2):
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        # Find a date where this size is still available
        chosen = None
        for off in (offset, offset + 10, offset + 20, offset + 25):
            d = (datetime.date.today() + datetime.timedelta(days=off)).isoformat()
            av = api.post(f"{BASE_URL}/api/bikes/{bid}/quote",
                          json={"bike_id": bid, "size": size, "date": d,
                                "days": days, "payment_method": pay}).json().get("available", {})
            if av.get(size, 0) > 0:
                chosen = d
                break
        d = chosen or (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()
        payload = {"bike_id": bid, "size": size, "date": d, "days": days, "payment_method": pay}
        r = api.post(f"{BASE_URL}/api/bookings", json=payload, headers=h(token))
        return r, bid, bikes[0]

    def test_create_daily_store(self, api, user_token):
        r, _, bike = self._book(api, user_token, days=2)
        assert r.status_code == 200, r.text
        bk = r.json()
        assert bk["status"] == "confirmed"
        assert bk["payment_status"] == "to_pay_in_store"
        assert bk["mode"] == "daily"
        assert bk["units"] == 2
        assert bk["total"] == round(bike["price_day"] * 2, 2)
        assert bk["start"].endswith("T09:00")
        assert bk["end"].endswith("T19:00")

    def test_create_hourly_rejected(self, api, user_token):
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        d = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        r = api.post(f"{BASE_URL}/api/bookings",
                     json={"bike_id": bid, "size": "M", "mode": "hourly",
                           "date": d, "days": 1, "payment_method": "store"},
                     headers=h(token))
        assert r.status_code == 422

    def test_create_requires_auth(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        d = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        r = api.post(f"{BASE_URL}/api/bookings",
                     json={"bike_id": bid, "size": "M", "date": d, "days": 1, "payment_method": "store"})
        assert r.status_code == 401

    def test_stock_exhaustion_409(self, api, user_token):
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        # Use a far-future unique date so prior runs don't pollute availability
        day = (datetime.date.today() + datetime.timedelta(days=25)).isoformat()
        # Pick a bike with limited XL stock using the per-day availability
        target = None
        for b in bikes:
            avail = api.post(f"{BASE_URL}/api/bikes/{b['id']}/quote",
                             json={"bike_id": b["id"], "size": "XL", "date": day,
                                   "days": 1, "payment_method": "store"}).json().get("available", {})
            if 0 < avail.get("XL", 0) <= 2:
                target = (b, avail["XL"])
                break
        if not target:
            pytest.skip("No bike with limited XL stock")
        bike, cap = target
        for _ in range(cap):
            r = api.post(f"{BASE_URL}/api/bookings",
                         json={"bike_id": bike["id"], "size": "XL", "date": day,
                               "days": 1, "payment_method": "store"}, headers=h(token))
            assert r.status_code == 200, r.text
        r = api.post(f"{BASE_URL}/api/bookings",
                     json={"bike_id": bike["id"], "size": "XL", "date": day,
                           "days": 1, "payment_method": "store"}, headers=h(token))
        assert r.status_code == 409

    def test_my_bookings_and_cancel(self, api, user_token):
        token, _ = user_token
        rb, _, _ = self._book(api, user_token, days=1, offset=5)
        assert rb.status_code == 200
        bid = rb.json()["id"]
        r = api.get(f"{BASE_URL}/api/bookings/me", headers=h(token))
        assert r.status_code == 200
        assert any(b["id"] == bid for b in r.json())
        rc = api.post(f"{BASE_URL}/api/bookings/{bid}/cancel", headers=h(token))
        assert rc.status_code == 200 and rc.json()["status"] == "cancelled"
        rc2 = api.post(f"{BASE_URL}/api/bookings/{bid}/cancel", headers=h(token))
        assert rc2.status_code == 409


# ------------------- Stripe -------------------
class TestStripe:
    def test_checkout_creates_session(self, api, user_token):
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        day = None
        for off in (6, 11, 16, 21, 29):
            d = (datetime.date.today() + datetime.timedelta(days=off)).isoformat()
            av = api.post(f"{BASE_URL}/api/bikes/{bid}/quote",
                          json={"bike_id": bid, "size": "M", "date": d,
                                "days": 1, "payment_method": "stripe"}).json().get("available", {})
            if av.get("M", 0) > 0:
                day = d
                break
        assert day, "No M-availability window found"
        rb = api.post(f"{BASE_URL}/api/bookings",
                      json={"bike_id": bid, "size": "M", "date": day,
                            "days": 1, "payment_method": "stripe"}, headers=h(token))
        assert rb.status_code == 200, rb.text
        booking_id = rb.json()["id"]
        rc = api.post(f"{BASE_URL}/api/payments/stripe/checkout",
                      json={"booking_id": booking_id, "return_url": f"{BASE_URL}/api/payments/return"},
                      headers=h(token))
        assert rc.status_code == 200, rc.text
        js = rc.json()
        assert "stripe.com" in js["url"]
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

    def test_stats_forbidden_en(self, api, user_token):
        token, _ = user_token
        r = api.get(f"{BASE_URL}/api/admin/stats",
                    headers={**h(token), "Accept-Language": "en"})
        assert r.status_code == 403
        assert r.json()["detail"] == "Administrators only"

    def test_admin_bookings_list(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/bookings", headers=h(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_bike_crud_price_day_only(self, api, admin_token):
        """Create/update admin bike with price_day only (no price_hour)"""
        payload = {"name": "TEST_Bike_Gravel", "category": "gravel", "description": "test",
                   "image_url": "https://x.com/i.jpg", "price_day": 40,
                   "stock": {"S": 1, "M": 1, "L": 1, "XL": 1}}
        rc = api.post(f"{BASE_URL}/api/admin/bikes", json=payload, headers=h(admin_token))
        assert rc.status_code == 200, rc.text
        bid = rc.json()["id"]
        assert rc.json()["price_day"] == 40
        assert "price_hour" not in rc.json()
        # update
        payload["price_day"] = 45
        ru = api.put(f"{BASE_URL}/api/admin/bikes/{bid}", json=payload, headers=h(admin_token))
        assert ru.status_code == 200
        assert ru.json()["price_day"] == 45
        rg = api.get(f"{BASE_URL}/api/bikes/{bid}")
        assert rg.status_code == 200 and rg.json()["price_day"] == 45
        rd = api.delete(f"{BASE_URL}/api/admin/bikes/{bid}", headers=h(admin_token))
        assert rd.status_code == 200
        assert api.get(f"{BASE_URL}/api/bikes/{bid}").status_code == 404

    def test_admin_bike_old_category_rejected(self, api, admin_token):
        """Old 'ebike' category must be rejected 422 (new set is gravel/egravel/ebike_mtb)"""
        payload = {"name": "TEST_old_cat", "category": "ebike", "price_day": 50,
                   "stock": {"S": 0, "M": 1, "L": 0, "XL": 0}}
        r = api.post(f"{BASE_URL}/api/admin/bikes", json=payload, headers=h(admin_token))
        assert r.status_code == 422

    def test_admin_bike_new_categories_accepted(self, api, admin_token):
        """All three new categories work with price_day only"""
        for cat, price in [("gravel", 40), ("egravel", 50), ("ebike_mtb", 60)]:
            payload = {"name": f"TEST_{cat}", "category": cat, "price_day": price,
                       "stock": {"S": 0, "M": 1, "L": 0, "XL": 0}}
            r = api.post(f"{BASE_URL}/api/admin/bikes", json=payload, headers=h(admin_token))
            assert r.status_code == 200, f"{cat}: {r.text}"
            bid = r.json()["id"]
            api.delete(f"{BASE_URL}/api/admin/bikes/{bid}", headers=h(admin_token))

    def test_admin_bike_forbidden_for_user(self, api, user_token):
        token, _ = user_token
        r = api.post(f"{BASE_URL}/api/admin/bikes", json={
            "name": "X", "category": "gravel", "price_day": 10,
            "stock": {"S": 0, "M": 0, "L": 0, "XL": 0}}, headers=h(token))
        assert r.status_code == 403

    def test_admin_patch_booking(self, api, admin_token, user_token):
        token, _ = user_token
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        bid = bikes[0]["id"]
        # Pick a far-future offset where S is still available
        day = None
        for off in (18, 19, 20, 21, 22, 23, 24, 26, 27, 28):
            d = (datetime.date.today() + datetime.timedelta(days=off)).isoformat()
            av = api.post(f"{BASE_URL}/api/bikes/{bid}/quote",
                          json={"bike_id": bid, "size": "S", "date": d,
                                "days": 1, "payment_method": "store"}).json().get("available", {})
            if av.get("S", 0) > 0:
                day = d
                break
        assert day, "No S-availability window found"
        rb = api.post(f"{BASE_URL}/api/bookings",
                      json={"bike_id": bid, "size": "S", "date": day, "days": 1, "payment_method": "store"},
                      headers=h(token))
        assert rb.status_code == 200, rb.text
        booking_id = rb.json()["id"]
        rp = api.patch(f"{BASE_URL}/api/admin/bookings/{booking_id}",
                       json={"payment_status": "paid"}, headers=h(admin_token))
        assert rp.status_code == 200
        assert rp.json()["payment_status"] == "paid"



# ------------------- Sheet Sync (iter 4) -------------------
class TestSheetSync:
    def test_sheet_sync_admin(self, api, admin_token):
        """POST /api/admin/sheet/sync returns expected units/rentals/stock."""
        r = api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(admin_token))
        assert r.status_code == 200, r.text
        js = r.json()
        assert js["units"] == 16, f"units={js['units']}"
        assert js["rentals"] == 11, f"rentals={js['rentals']}"
        stock = js["stock"]
        assert stock["egravel"] == {"S": 1, "M": 2, "L": 2, "XL": 1}, stock["egravel"]
        assert stock["gravel"] == {"S": 1, "M": 2, "L": 2, "XL": 1}, stock["gravel"]
        assert stock["ebike_mtb"] == {"S": 0, "M": 2, "L": 2, "XL": 0}, stock["ebike_mtb"]
        assert js.get("synced_at")
        assert js.get("error") is None

    def test_sheet_sync_forbidden_for_user(self, api, user_token):
        token, _ = user_token
        r = api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(token))
        assert r.status_code == 403

    def test_sheet_status_forbidden_for_user(self, api, user_token):
        token, _ = user_token
        r = api.get(f"{BASE_URL}/api/admin/sheet/status", headers=h(token))
        assert r.status_code == 403

    def test_sheet_status_returns_synced_at(self, api, admin_token):
        api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(admin_token))
        r = api.get(f"{BASE_URL}/api/admin/sheet/status", headers=h(admin_token))
        assert r.status_code == 200, r.text
        js = r.json()
        assert js.get("synced_at")
        assert js.get("rentals") == 11

    def test_sheet_sync_idempotent(self, api, admin_token):
        """Re-running sync does not create duplicate sheet bookings."""
        api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(admin_token))
        first = api.get(f"{BASE_URL}/api/admin/bookings", headers=h(admin_token)).json()
        sheet_first = [b for b in first if b.get("source") == "sheet"]
        api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(admin_token))
        second = api.get(f"{BASE_URL}/api/admin/bookings", headers=h(admin_token)).json()
        sheet_second = [b for b in second if b.get("source") == "sheet"]
        ids_first = sorted(b.get("sheet_id") for b in sheet_first)
        ids_second = sorted(b.get("sheet_id") for b in sheet_second)
        assert ids_first == ids_second
        # no duplicate sheet_id
        assert len(ids_second) == len(set(ids_second))
        # expected 11 rentals from sheet
        assert len(sheet_second) == 11

    def test_bikes_stock_matches_sheet(self, api, admin_token):
        """After sync, GET /api/bikes stock matches sheet counts."""
        api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(admin_token))
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        by_cat = {b["category"]: b for b in bikes}
        assert by_cat["gravel"]["stock"] == {"S": 1, "M": 2, "L": 2, "XL": 1}
        assert by_cat["egravel"]["stock"] == {"S": 1, "M": 2, "L": 2, "XL": 1}
        assert by_cat["ebike_mtb"]["stock"] == {"S": 0, "M": 2, "L": 2, "XL": 0}

    def test_sheet_booking_blocks_availability(self, api, admin_token):
        """Raymon Soreno Comp size L on 2026-10-18 -> L available 0 (GR-010 & GR-011 booked)."""
        api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(admin_token))
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        gravel = next(b for b in bikes if b["name"] == "Raymon Soreno Comp")
        r = api.post(f"{BASE_URL}/api/bikes/{gravel['id']}/quote",
                     json={"bike_id": gravel["id"], "size": "L",
                           "date": "2026-10-18", "days": 1, "payment_method": "store"})
        assert r.status_code == 200, r.text
        assert r.json()["available"]["L"] == 0, r.json()["available"]

    def test_sheet_bookings_not_in_user_me(self, api, user_token, admin_token):
        """Sheet bookings do NOT appear in a normal user's /api/bookings/me."""
        token, _ = user_token
        api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(admin_token))
        r = api.get(f"{BASE_URL}/api/bookings/me", headers=h(token))
        assert r.status_code == 200
        for b in r.json():
            assert b.get("source") != "sheet"
            assert not b.get("sheet_id")

    def test_sheet_bookings_in_admin_bookings(self, api, admin_token):
        """Sheet bookings DO appear in /api/admin/bookings with source=sheet and NOL-xxx id."""
        api.post(f"{BASE_URL}/api/admin/sheet/sync", headers=h(admin_token))
        r = api.get(f"{BASE_URL}/api/admin/bookings", headers=h(admin_token))
        assert r.status_code == 200
        sheet = [b for b in r.json() if b.get("source") == "sheet"]
        assert len(sheet) == 11, f"expected 11, got {len(sheet)}"
        for b in sheet:
            assert b.get("sheet_id", "").startswith("NOL-"), b.get("sheet_id")
            assert b.get("unit_id"), f"missing unit_id in {b.get('sheet_id')}"


# ------------------- Phone field (iter 4) -------------------
class TestPhone:
    def test_booking_saves_phone_on_user_and_booking(self, api):
        import uuid as _u
        email = f"TEST_phone_{_u.uuid4().hex[:8]}@example.com"
        r = api.post(f"{BASE_URL}/api/auth/register",
                     json={"email": email, "password": "secret12", "name": "Phone User"})
        assert r.status_code == 200
        token = r.json()["token"]
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        # Find a date where M is available on bike[0]
        bid = bikes[0]["id"]
        chosen = None
        for off in (3, 7, 12, 20, 27):
            d = (datetime.date.today() + datetime.timedelta(days=off)).isoformat()
            av = api.post(f"{BASE_URL}/api/bikes/{bid}/quote",
                          json={"bike_id": bid, "size": "M", "date": d,
                                "days": 1, "payment_method": "store"}).json().get("available", {})
            if av.get("M", 0) > 0:
                chosen = d
                break
        assert chosen, "no M-availability window"
        rb = api.post(f"{BASE_URL}/api/bookings",
                      json={"bike_id": bid, "size": "M", "date": chosen, "days": 1,
                            "payment_method": "store", "phone": "+39 333 1234567"},
                      headers=h(token))
        assert rb.status_code == 200, rb.text
        assert rb.json()["phone"] == "+39 333 1234567"
        # /api/auth/me returns phone
        rm = api.get(f"{BASE_URL}/api/auth/me", headers=h(token))
        assert rm.status_code == 200
        assert rm.json()["phone"] == "+39 333 1234567"
        # Cleanup
        api.post(f"{BASE_URL}/api/bookings/{rb.json()['id']}/cancel", headers=h(token))
