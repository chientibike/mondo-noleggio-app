"""Iteration 11: POST /api/admin/bikes/lookup — web search for photo/data; saves nothing."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://bici-disponibili.preview.emergentagent.com").rstrip("/")
FOCUS_SAM_ID = "3be9a93d650142a4a08580c6deec6b01"


def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Auth guards ----------------
class TestLookupAuth:
    def test_no_token_returns_401(self, api):
        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup",
                     json={"name": "Focus Sam 6.9", "category": "ebike_mtb"})
        assert r.status_code == 401, r.text

    def test_user_token_returns_403(self, api, user_token):
        token, _ = user_token
        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup",
                     headers=h(token),
                     json={"name": "Focus Sam 6.9", "category": "ebike_mtb"})
        assert r.status_code == 403, r.text


# ---------------- Validation ----------------
class TestLookupValidation:
    def test_invalid_category_422(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup",
                     headers=h(admin_token),
                     json={"name": "Focus Sam 6.9", "category": "road"})
        assert r.status_code == 422, r.text

    def test_short_name_422(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup",
                     headers=h(admin_token),
                     json={"name": "A", "category": "gravel"})
        assert r.status_code == 422, r.text

    def test_missing_category_422(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/admin/bikes/lookup",
                     headers=h(admin_token),
                     json={"name": "Focus Sam 6.9"})
        assert r.status_code == 422, r.text


# ---------------- Core behaviour: admin 200 + DB untouched ----------------
class TestLookupBehaviour:
    def test_admin_200_and_db_unchanged(self, api, admin_token):
        """Lookup must return data to review, and NEVER touch the bike doc.
        We snapshot Focus Sam 6.9 before, call lookup, and verify the bike is byte-identical after."""
        before = api.get(f"{BASE_URL}/api/bikes/{FOCUS_SAM_ID}")
        assert before.status_code == 200, before.text
        before_doc = before.json()
        before_doc.pop("available", None)  # computed, may vary by availability queries
        existing_image = before_doc.get("image_url", "")

        r = api.post(
            f"{BASE_URL}/api/admin/bikes/lookup",
            headers=h(admin_token),
            json={"name": "Focus Sam 6.9", "category": "ebike_mtb", "exclude_image": existing_image},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Shape
        assert set(["image_url", "source_url", "description", "description_en", "specs"]).issubset(data.keys())
        assert isinstance(data["specs"], dict)
        assert isinstance(data["image_url"], str)
        assert isinstance(data["source_url"], str)
        # Exclude image honored: when a new image is returned, it must differ from exclude_image
        if data["image_url"] and existing_image:
            assert data["image_url"] != existing_image, "image_url must differ from exclude_image"

        # DB untouched
        after = api.get(f"{BASE_URL}/api/bikes/{FOCUS_SAM_ID}")
        assert after.status_code == 200, after.text
        after_doc = after.json()
        after_doc.pop("available", None)
        assert after_doc == before_doc, f"Bike doc changed after lookup!\nBEFORE: {before_doc}\nAFTER: {after_doc}"

    def test_admin_lookup_without_exclude(self, api, admin_token):
        """Lookup with no exclude_image should also succeed and return populated fields."""
        r = api.post(
            f"{BASE_URL}/api/admin/bikes/lookup",
            headers=h(admin_token),
            json={"name": "Canyon Grail CF SL 7", "category": "gravel"},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # At least one of these should be populated — the LLM does web-grounded search
        assert any([data.get("description"), data.get("description_en"), data.get("specs")]), (
            f"Lookup returned empty payload: {data}"
        )
