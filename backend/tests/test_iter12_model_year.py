"""Iteration 12: model_year on bikes, lookup with year, enricher year filters, PUT model_year preservation."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://bici-disponibili.preview.emergentagent.com").rstrip("/")
FOCUS_SAM_ID = "3be9a93d650142a4a08580c6deec6b01"


def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- GET /api/bikes includes model_year ----------------
class TestBikesModelYear:
    def test_bikes_have_model_year(self, api):
        r = api.get(f"{BASE_URL}/api/bikes")
        assert r.status_code == 200, r.text
        bikes = r.json()
        assert isinstance(bikes, list) and bikes, "no bikes returned"
        # Each bike should include model_year key (may be None/"" but field present)
        for b in bikes:
            assert "model_year" in b, f"missing model_year on {b.get('name')}"

    def test_raymon_bikes_model_year_2027(self, api):
        r = api.get(f"{BASE_URL}/api/bikes")
        assert r.status_code == 200
        bikes = r.json()
        raymon = [b for b in bikes if "Raymon" in b["name"] and any(k in b["name"] for k in ("Soreno", "Norza", "Vamok"))]
        assert raymon, "no Raymon bikes found"
        for b in raymon:
            assert b.get("model_year") == "2027", f"{b['name']}: expected '2027', got {b.get('model_year')!r}"

    def test_focus_sam_6_9_model_year_2026(self, api):
        r = api.get(f"{BASE_URL}/api/bikes/{FOCUS_SAM_ID}")
        assert r.status_code == 200, r.text
        bike = r.json()
        assert "Focus" in bike["name"] and "6.9" in bike["name"], f"unexpected bike at FOCUS_SAM_ID: {bike['name']}"
        assert bike.get("model_year") == "2026", f"Focus Sam 6.9 model_year: expected '2026', got {bike.get('model_year')!r}"


# ---------------- Lookup year validation ----------------
class TestLookupYearValidation:
    def test_no_token_401(self, api):
        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup",
                     json={"name": "Focus Sam 6.9", "category": "ebike_mtb", "year": "2026"})
        assert r.status_code == 401, r.text

    def test_user_403(self, api, user_token):
        token, _ = user_token
        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup", headers=h(token),
                     json={"name": "Focus Sam 6.9", "category": "ebike_mtb", "year": "2026"})
        assert r.status_code == 403, r.text

    def test_bad_year_422(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup", headers=h(admin_token),
                     json={"name": "Focus Sam 6.9", "category": "ebike_mtb", "year": "abcd"})
        assert r.status_code == 422, r.text


# ---------------- Lookup with year: shape + DB untouched ----------------
class TestLookupWithYear:
    def test_focus_sam_lookup_year_2026(self, api, admin_token):
        """Lookup Focus Sam 6.9 with year='2026': returns 200 with year='2026', year_confirmed bool, specs dict.
        Must NOT mutate the DB."""
        before = api.get(f"{BASE_URL}/api/bikes/{FOCUS_SAM_ID}")
        assert before.status_code == 200
        before_doc = before.json()
        before_doc.pop("available", None)

        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup", headers=h(admin_token),
                     json={"name": "Focus Sam 6.9", "category": "ebike_mtb", "year": "2026"},
                     timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        # Shape
        for key in ("image_url", "source_url", "description", "description_en", "specs", "year", "year_confirmed"):
            assert key in data, f"missing key {key} in response: {data}"
        assert data["year"] == "2026", f"expected year='2026', got {data['year']!r}"
        assert isinstance(data["year_confirmed"], bool), f"year_confirmed must be bool, got {type(data['year_confirmed'])}"
        assert isinstance(data["specs"], dict)
        # If year not confirmed, specs must be empty
        if not data["year_confirmed"]:
            assert data["specs"] == {}, f"specs must be empty when year_confirmed=False, got {data['specs']}"

        # DB untouched
        after = api.get(f"{BASE_URL}/api/bikes/{FOCUS_SAM_ID}")
        assert after.status_code == 200
        after_doc = after.json()
        after_doc.pop("available", None)
        assert after_doc == before_doc, f"Bike doc changed!\nBEFORE: {before_doc}\nAFTER: {after_doc}"


# ---------------- PUT admin/bikes: model_year preservation (TEST bike) ----------------
class TestPutModelYear:
    @pytest.fixture
    def test_bike(self, api, admin_token):
        """Create a throwaway bike, yield, delete after. Does NOT touch real bikes."""
        payload = {
            "name": "TEST_IT12_bike", "category": "gravel",
            "description": "test", "description_en": "test",
            "image_url": "", "price_day": 40.0, "specs": {},
            "stock": {"S": 0, "M": 0, "L": 0, "XL": 0},
            "model_year": "2026",
        }
        r = api.post(f"{BASE_URL}/api/admin/bikes", headers=h(admin_token), json=payload)
        assert r.status_code == 200, r.text
        bike = r.json()
        assert bike["model_year"] == "2026", f"creation didn't persist model_year: {bike}"
        yield bike
        try:
            api.delete(f"{BASE_URL}/api/admin/bikes/{bike['id']}", headers=h(admin_token))
        except Exception:
            pass

    def test_put_keeps_model_year_when_sent(self, api, admin_token, test_bike):
        payload = {
            "name": test_bike["name"], "category": test_bike["category"],
            "description": test_bike["description"], "description_en": test_bike["description_en"],
            "image_url": test_bike["image_url"], "price_day": test_bike["price_day"],
            "specs": test_bike["specs"], "stock": test_bike["stock"],
            "model_year": "2027",
        }
        r = api.put(f"{BASE_URL}/api/admin/bikes/{test_bike['id']}", headers=h(admin_token), json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["model_year"] == "2027"
        # Verify via GET
        g = api.get(f"{BASE_URL}/api/bikes/{test_bike['id']}")
        assert g.json()["model_year"] == "2027"

    def test_put_without_model_year_keeps_existing(self, api, admin_token, test_bike):
        """Omitting model_year from the PUT body must keep the current value (model_year defaults to None in
        BikeIn, but admin_update_bike only sets it when body.model_year is not None)."""
        payload = {
            "name": test_bike["name"], "category": test_bike["category"],
            "description": "updated desc", "description_en": test_bike["description_en"],
            "image_url": test_bike["image_url"], "price_day": 42.0,
            "specs": test_bike["specs"], "stock": test_bike["stock"],
            # model_year intentionally omitted
        }
        r = api.put(f"{BASE_URL}/api/admin/bikes/{test_bike['id']}", headers=h(admin_token), json=payload)
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["model_year"] == "2026", f"model_year should be preserved as '2026', got {got.get('model_year')!r}"
        assert got["description"] == "updated desc"
        assert got["price_day"] == 42.0


# ---------------- Enricher unit tests ----------------
class TestEnricherYear:
    def test_other_year_detects_different_year_in_url(self):
        from enricher import _other_year
        assert _other_year("https://x.com/2024/review", "2026") is True

    def test_other_year_false_when_no_year_token(self):
        from enricher import _other_year
        assert _other_year("https://x.com/sam-6-9", "2026") is False

    def test_other_year_false_when_target_year_present(self):
        from enricher import _other_year
        assert _other_year("https://x.com/2026/review", "2026") is False

    def test_other_year_true_with_my_shorthand_skipped(self):
        from enricher import _other_year
        # my25 is not a 20YY token in _other_year regex: should NOT trigger as a different year
        assert _other_year("https://x.com/my25-bike", "2026") is False

    def test_find_photo_rejects_wrong_year_image_from_unrelated_page(self, monkeypatch):
        """When year='2026', an image URL that only mentions 2025 from a page without 2026 in URL/title
        must be rejected."""
        import enricher

        class FakeResp:
            def __init__(self, text="", status_code=200, url="https://brand.com/sam-6-9", content=b"\x89PNG" + b"\x00" * 20000,
                         ctype="image/jpeg"):
                self.text = text
                self.status_code = status_code
                self.url = type("U", (), {"host": "brand.com", "__str__": lambda s: url})()
                self.content = content
                self.headers = {"content-type": ctype}

        class FakeClient:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

            async def get(self, url, headers=None):
                if url == "https://brand.com/img-2025.jpg":
                    return FakeResp(url=url)
                if url == "https://brand.com/sam-6-9":
                    html = ('<html><head><title>Sam 6.9 review</title>'
                            '<meta property="og:image" content="https://brand.com/img-2025.jpg"/>'
                            '</head><body></body></html>')
                    return FakeResp(text=html, url=url, content=b"<html/>", ctype="text/html")
                return FakeResp(url=url)

        monkeypatch.setattr(enricher.httpx, "AsyncClient", FakeClient)
        import asyncio
        photo, page = asyncio.run(enricher._find_photo(
            images=["https://brand.com/img-2025.jpg"],
            pages=["https://brand.com/sam-6-9"],
            brand="focus",
            exclude=None,
            year="2026",
        ))
        # The image URL mentions only 2025; the page URL/title also don't mention 2026 → reject.
        assert photo is None, f"expected rejection, got {photo}"
