"""Iteration 10: enricher.py tests.
Covers:
  1) GET /api/bikes shows Focus Sam 6.9 with image/description/description_en/specs
  2) POST /api/admin/bikes/{id}/enrich auth: 401 (no token) / 403 (user) / 200 (admin)
  3) Admin enrich on a Raymon bike does NOT overwrite existing filled fields
  4) enrich_new_bikes(db) only processes sheet_model bikes with no enriched_at;
     inserts a TEST_ bike directly in Mongo and verifies fields are filled + enriched_at set
  5) Sheet sync regression: /api/admin/sheet/status still returns synced_at
SAFETY: no POST /api/bookings, no Stripe paid flag. Does not touch Raymon fields.
"""
import os
import sys
import asyncio
import uuid as _uuid
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from tests.conftest import BASE_URL, h

# Load backend .env
sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

FOCUS_ID = "3be9a93d650142a4a08580c6deec6b01"
SPEC_FIELDS = ["frame", "motor", "battery", "range", "suspension", "groupset", "brakes", "wheels", "weight"]


# --- feature 1: GET /api/bikes shows enriched Focus Sam 6.9 ---
class TestFocusSamEnriched:
    def test_focus_present_with_photo_desc_specs(self, api):
        r = api.get(f"{BASE_URL}/api/bikes")
        assert r.status_code == 200
        bikes = r.json()
        focus = next((b for b in bikes if b["id"] == FOCUS_ID), None)
        assert focus is not None, "Focus Sam 6.9 missing from /api/bikes"
        assert focus["name"].lower().startswith("focus sam")
        assert focus["category"] == "ebike_mtb"
        assert focus["image_url"].startswith("https://"), f"image_url={focus['image_url']}"
        assert len(focus["description"]) > 20, "description IT too short"
        assert len(focus["description_en"]) > 20, "description EN too short"
        assert isinstance(focus["specs"], dict)
        # at least frame + motor/battery expected for an ebike_mtb
        assert focus["specs"].get("frame"), "specs.frame missing"
        assert focus["specs"].get("motor"), "specs.motor missing"


# --- feature 2: POST /api/admin/bikes/{id}/enrich auth ---
class TestEnrichAuth:
    def test_enrich_no_token_401(self, api):
        r = api.post(f"{BASE_URL}/api/admin/bikes/{FOCUS_ID}/enrich")
        assert r.status_code == 401, r.text

    def test_enrich_user_token_403(self, api, user_token):
        token, _ = user_token
        r = api.post(f"{BASE_URL}/api/admin/bikes/{FOCUS_ID}/enrich", headers=h(token))
        assert r.status_code == 403, r.text


# --- feature 3: admin force enrich does NOT overwrite filled Raymon fields ---
class TestEnrichNoOverwrite:
    def test_enrich_raymon_preserves_fields(self, api, admin_token):
        # Pick the gravel Raymon bike (has filled description/image/specs)
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        raymon = next(b for b in bikes if b["name"] == "Raymon Soreno Comp")
        before = {
            "name": raymon["name"],
            "image_url": raymon["image_url"],
            "description": raymon["description"],
            "description_en": raymon["description_en"],
            "specs": dict(raymon["specs"]),
            "price_day": raymon["price_day"],
            "category": raymon["category"],
        }
        rid = raymon["id"]
        r = api.post(f"{BASE_URL}/api/admin/bikes/{rid}/enrich", headers=h(admin_token), timeout=180)
        assert r.status_code == 200, r.text
        js = r.json()
        assert js.get("ok") is True, js
        # Re-fetch and compare
        after = api.get(f"{BASE_URL}/api/bikes/{rid}").json()
        assert after["name"] == before["name"], "name was overwritten"
        assert after["image_url"] == before["image_url"], "image_url was overwritten"
        assert after["description"] == before["description"], "description was overwritten"
        assert after["description_en"] == before["description_en"], "description_en was overwritten"
        assert after["price_day"] == before["price_day"]
        assert after["category"] == before["category"]
        # Every originally-filled spec key must be preserved exactly
        for k, v in before["specs"].items():
            assert after["specs"].get(k) == v, f"specs.{k} overwritten: {v!r} -> {after['specs'].get(k)!r}"


# --- feature 4: enrich_new_bikes(db) processes TEST_ bike inserted directly ---
class TestEnrichNewBikes:
    @pytest.mark.timeout(240)
    def test_enrich_new_bikes_fills_fields(self):
        """Insert a TEST_ bike with sheet_model, no enriched_at, empty image/description;
        run enrich_new_bikes(db); verify fields filled + enriched_at set; delete."""
        from enricher import enrich_new_bikes

        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]

        async def _run():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            bike_id = "TEST_" + _uuid.uuid4().hex
            doc = {
                "id": bike_id,
                "name": "TEST Canyon Grizl",
                "sheet_model": "Canyon Grizl CF SL 8",
                "category": "gravel",
                "price_day": 40.0,
                "description": "",
                "description_en": "",
                "image_url": "",
                "specs": {},
                "stock": {"S": 0, "M": 0, "L": 0, "XL": 0},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.bikes.insert_one(doc)
            try:
                await enrich_new_bikes(db)
                after = await db.bikes.find_one({"id": bike_id}, {"_id": 0})
                assert after is not None
                # enriched_at must be set (always set at start of enrich_bike)
                assert after.get("enriched_at"), "enriched_at not set"
                # Must have at least description filled; image is best-effort
                has_desc = bool(after.get("description")) or bool(after.get("description_en"))
                has_specs = isinstance(after.get("specs"), dict) and any(
                    after["specs"].get(k) for k in SPEC_FIELDS
                )
                # If research succeeded we expect description + specs
                err = after.get("enrich_error")
                if err:
                    pytest.skip(f"Gemini research failed transiently: {err}")
                assert has_desc, f"no description filled: {after}"
                assert has_specs, f"no specs filled: {after}"
                return after
            finally:
                await db.bikes.delete_one({"id": bike_id})
                client.close()

        result = asyncio.run(_run())
        assert result is not None

    @pytest.mark.timeout(60)
    def test_enrich_new_bikes_skips_already_enriched(self):
        """A doc with enriched_at set must NOT be re-processed by enrich_new_bikes."""
        from enricher import enrich_new_bikes

        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]

        async def _run():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            bike_id = "TEST_skip_" + _uuid.uuid4().hex
            original_enriched_at = "2020-01-01T00:00:00+00:00"
            doc = {
                "id": bike_id,
                "name": "TEST SkipMe",
                "sheet_model": "Totally Fake Bike Model XYZ 9999",
                "category": "gravel",
                "price_day": 40.0,
                "description": "",
                "description_en": "",
                "image_url": "",
                "specs": {},
                "stock": {"S": 0, "M": 0, "L": 0, "XL": 0},
                "enriched_at": original_enriched_at,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.bikes.insert_one(doc)
            try:
                await enrich_new_bikes(db)
                after = await db.bikes.find_one({"id": bike_id}, {"_id": 0})
                # The filter requires enriched_at NOT to exist; this doc should be left untouched
                assert after.get("enriched_at") == original_enriched_at
                assert after.get("description") == ""
                assert after.get("image_url") == ""
            finally:
                await db.bikes.delete_one({"id": bike_id})
                client.close()

        asyncio.run(_run())


# --- feature 5: sheet sync regression ---
class TestSheetSyncRegression:
    def test_sheet_status_still_works(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/sheet/status", headers=h(admin_token))
        assert r.status_code == 200, r.text
        js = r.json()
        assert "synced_at" in js
        assert js.get("synced_at"), "synced_at should be set"
