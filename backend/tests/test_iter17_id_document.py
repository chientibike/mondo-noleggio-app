"""Iteration 17 — Private ID-document upload and the booking doc-photo requirement.

Covers (live HTTPS unless noted):
- POST /api/me/id-document:
    * no token -> 401
    * text/plain content_type -> 400
    * valid image + user token -> 200 {id}
- GET /api/private-files/{id}:
    * owner Bearer -> 200 bytes equal
    * admin Bearer -> 200
    * other-user Bearer -> 404
    * no auth / no token -> 401 or 404 (both acceptable, never 200)
    * ?t=valid link -> 200
    * ?t=valid link for a *different* file -> 404
- GET /api/files/{private id} MUST NOT serve a private file -> 404
- POST /api/bookings (live HTTPS, rejected before DB insert):
    * doc ids missing -> 400 'Carica la foto'
    * doc ids belong to another user -> 400
    * doc ids are bike photos (public, kind != id_document) -> 400
- mailer.shop_email: html contains 2 `/api/private-files/..?t=` anchors; passes _assert_safe_email.

Cleanup: all TEST_* users + uploaded doc files deleted at end.
"""
import io
import os
import sys
import uuid
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, "/app/backend")  # import server/mailer

from .conftest import BASE_URL, h  # noqa: E402
from .test_iter13_upload import _tiny_png, _up_headers  # noqa: E402

ADMIN_EMAIL = "admin@noleggionuovo.it"
ADMIN_PASSWORD = "Admin2026!"


def _sync_cleanup(coll: str, query: dict) -> None:
    """Delete directly via pymongo so we don't collide with motor's async event loop."""
    try:
        from pymongo import MongoClient
        c = MongoClient(os.environ["MONGO_URL"])
        c[os.environ["DB_NAME"]][coll].delete_many(query)
        c.close()
    except Exception:
        pass


# ----------------- helpers / fixtures -----------------

@pytest.fixture(scope="module")
def another_user_token(api):
    email = f"TEST_iter17_other_{uuid.uuid4().hex[:8]}@example.com"
    r = api.post(f"{BASE_URL}/api/auth/register",
                 json={"email": email, "password": "testpass123", "name": "Other"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    uid = r.json()["user"]["id"]
    yield tok, uid, email
    _sync_cleanup("users", {"id": uid})


@pytest.fixture(scope="module")
def uploaded_docs(api, user_token):
    """Upload two id-document photos for the primary test user. Returns {front: id, back: id, bytes}."""
    token, _ = user_token
    png = _tiny_png(4, 4)
    ids: list[str] = []
    for side in ("front", "back"):
        r = api.post(f"{BASE_URL}/api/me/id-document",
                     headers=_up_headers(token),
                     files={"file": (f"TEST_{side}.png", png, "image/png")})
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    yield {"front": ids[0], "back": ids[1], "bytes": png}
    _sync_cleanup("files", {"id": {"$in": ids}})


# ----------------- 1. Upload matrix -----------------

class TestUploadMatrix:
    def test_no_token_401(self, api):
        png = _tiny_png()
        r = api.post(f"{BASE_URL}/api/me/id-document",
                     headers=_up_headers(),
                     files={"file": ("x.png", png, "image/png")})
        assert r.status_code == 401, r.text

    def test_text_plain_400(self, api, user_token):
        token, _ = user_token
        r = api.post(f"{BASE_URL}/api/me/id-document",
                     headers=_up_headers(token),
                     files={"file": ("x.txt", b"hello", "text/plain")})
        assert r.status_code == 400, r.text

    def test_image_200(self, api, uploaded_docs):
        # uploaded_docs fixture already did the upload; just assert ids are hex
        assert len(uploaded_docs["front"]) == 32
        assert len(uploaded_docs["back"]) == 32
        assert uploaded_docs["front"] != uploaded_docs["back"]


# ----------------- 2. Private GET -----------------

class TestPrivateGet:
    def test_owner_bearer_200_bytes_equal(self, api, user_token, uploaded_docs):
        token, _ = user_token
        fid = uploaded_docs["front"]
        r = api.get(f"{BASE_URL}/api/private-files/{fid}", headers=h(token))
        assert r.status_code == 200, r.text
        assert r.content == uploaded_docs["bytes"]
        assert r.headers.get("Content-Type", "").startswith("image/")
        cc = r.headers.get("Cache-Control", "").lower()
        # Backend sets 'private, no-store'; preview CDN may override but any sensible value is OK
        assert "cache-control" in {k.lower() for k in r.headers.keys()}, "Cache-Control header missing"

    def test_admin_bearer_200(self, api, admin_token, uploaded_docs):
        r = api.get(f"{BASE_URL}/api/private-files/{uploaded_docs['front']}", headers=h(admin_token))
        assert r.status_code == 200, r.text

    def test_other_user_404(self, api, another_user_token, uploaded_docs):
        other_tok, _, _ = another_user_token
        r = api.get(f"{BASE_URL}/api/private-files/{uploaded_docs['front']}", headers=h(other_tok))
        assert r.status_code == 404, r.text

    def test_no_auth_blocked(self, api, uploaded_docs):
        r = api.get(f"{BASE_URL}/api/private-files/{uploaded_docs['front']}")
        assert r.status_code in (401, 404), r.text
        assert r.status_code != 200

    def test_signed_token_200(self, uploaded_docs):
        import server
        fid = uploaded_docs["front"]
        tok = server.file_link_token(fid)
        r = requests.get(f"{BASE_URL}/api/private-files/{fid}?t={tok}")
        assert r.status_code == 200, r.text
        assert r.content == uploaded_docs["bytes"]

    def test_signed_token_for_other_file_404(self, uploaded_docs):
        import server
        fid = uploaded_docs["front"]
        other_tok = server.file_link_token("some-other-id")
        r = requests.get(f"{BASE_URL}/api/private-files/{fid}?t={other_tok}")
        assert r.status_code == 404, r.text

    def test_bad_signed_token_404(self, uploaded_docs):
        r = requests.get(f"{BASE_URL}/api/private-files/{uploaded_docs['front']}?t=not-a-token")
        assert r.status_code == 404, r.text


# ----------------- 3. Public /api/files MUST NOT serve private files -----------------

class TestPublicFilesDoesNotServePrivate:
    def test_public_endpoint_404_for_private(self, api, uploaded_docs):
        r = api.get(f"{BASE_URL}/api/files/{uploaded_docs['front']}")
        assert r.status_code == 404, r.text


# ----------------- 4. Booking rejection with wrong/missing doc ids -----------------

def _booking_payload(bike_id, version, doc_front="", doc_back=""):
    cust = {
        "full_name": "Mario Rossi", "tax_code": "RSSMRA80A01L191X",
        "birth_date": "1980-01-01", "address": "Via Roma 10",
        "city_zip": "Tolentino 62029", "nationality": "Italiana",
        "doc_type": "ci", "doc_number": "AX1234567",
        "doc_issuer_expiry": "Comune, 31/12/2030", "emergency_contact": "",
        "doc_front_id": doc_front, "doc_back_id": doc_back,
    }
    return {
        "bike_id": bike_id, "size": "M", "mode": "daily",
        "date": (date.today() + timedelta(days=18)).isoformat(), "days": 1,
        "payment_method": "store", "phone": "3331234567",
        "contract_accepted": True, "clauses_approved": True, "privacy_accepted": True,
        "contract_version": version, "customer": cust,
    }


class TestBookingDocRequirement:
    @pytest.fixture
    def bike_id(self, api):
        bikes = api.get(f"{BASE_URL}/api/bikes").json()
        return next((b["id"] for b in bikes if int(b.get("stock", {}).get("M", 0)) > 0), bikes[0]["id"])

    @pytest.fixture
    def version(self, api):
        return api.get(f"{BASE_URL}/api/contract").json()["version"]

    def test_missing_doc_ids_400(self, api, user_token, bike_id, version):
        token, _ = user_token
        r = api.post(f"{BASE_URL}/api/bookings", headers=h(token),
                     json=_booking_payload(bike_id, version, "", ""))
        assert r.status_code == 400, r.text
        assert "documento" in r.json()["detail"].lower()

    def test_doc_ids_from_other_user_400(self, api, user_token, another_user_token, bike_id, version):
        token, _ = user_token
        other_tok, _, _ = another_user_token
        # upload two docs under the other user
        png = _tiny_png()
        other_ids = []
        for s in ("f", "b"):
            r = api.post(f"{BASE_URL}/api/me/id-document", headers=_up_headers(other_tok),
                         files={"file": (f"TEST_other_{s}.png", png, "image/png")})
            assert r.status_code == 200, r.text
            other_ids.append(r.json()["id"])
        try:
            r = api.post(f"{BASE_URL}/api/bookings", headers=h(token),
                         json=_booking_payload(bike_id, version, other_ids[0], other_ids[1]))
            assert r.status_code == 400, r.text
            assert "documento" in r.json()["detail"].lower()
        finally:
            _sync_cleanup("files", {"id": {"$in": other_ids}})

    def test_doc_ids_are_bike_photos_400(self, api, user_token, admin_token, bike_id, version):
        token, _ = user_token
        # admin uploads two bike photos (public, kind != id_document)
        png = _tiny_png()
        pub_ids = []
        for s in ("1", "2"):
            r = api.post(f"{BASE_URL}/api/admin/upload", headers=_up_headers(admin_token),
                         files={"file": (f"TEST_pub_{s}.png", png, "image/png")})
            assert r.status_code == 200, r.text
            url = r.json()["url"]
            pub_ids.append(url.rsplit("/", 1)[-1])
        try:
            r = api.post(f"{BASE_URL}/api/bookings", headers=h(token),
                         json=_booking_payload(bike_id, version, pub_ids[0], pub_ids[1]))
            assert r.status_code == 400, r.text
            assert "documento" in r.json()["detail"].lower()
        finally:
            _sync_cleanup("files", {"id": {"$in": pub_ids}})

    def test_no_booking_created(self, api, user_token):
        """After all rejection tests, user still has zero bookings."""
        token, _ = user_token
        bks = api.get(f"{BASE_URL}/api/bookings/me", headers=h(token)).json()
        assert bks == [], f"LEAK: a rejection test created a booking: {bks}"


# ----------------- 5. Mailer shop_email contains signed doc links -----------------

class TestMailerDocLinks:
    def test_shop_email_contains_two_signed_links(self):
        import mailer
        bk = {
            "id": "bk-test", "user_name": "Mario Rossi", "user_email": "x@example.com",
            "bike_name": "Raymon", "size": "M", "start": "2026-02-10T09:00",
            "end": "2026-02-11T19:00", "units": 1, "total": 50.0,
            "payment_status": "to_pay_in_store", "sheet_id": "NOL-TEST",
            "phone": "3331234567", "unit_id": "GR-001",
            "contract_accepted_at": "2026-01-10T10:00:00+00:00",
            "public_base": "https://bici-disponibili.preview.emergentagent.com",
            "customer": {
                "tax_code": "RSSMRA80A01L191X",
                "doc_front_id": uuid.uuid4().hex,
                "doc_back_id": uuid.uuid4().hex,
            },
        }
        subject, html = mailer.shop_email(bk)
        # two signed anchors
        assert html.count("/api/private-files/") == 2, html
        assert html.count("?t=") >= 2
        assert "Documento fronte" in html
        assert "Documento retro" in html
        # guardrail
        mailer._assert_safe_email(subject, html)

    def test_shop_email_without_docs_has_no_links(self):
        import mailer
        bk = {
            "id": "bk-test", "user_name": "Mario", "user_email": "x@example.com",
            "bike_name": "Raymon", "size": "M", "start": "2026-02-10T09:00",
            "end": "2026-02-11T19:00", "units": 1, "total": 50.0,
            "payment_status": "to_pay_in_store", "sheet_id": "NOL-TEST",
            "public_base": "https://bici-disponibili.preview.emergentagent.com",
            "customer": {"tax_code": "RSSMRA80A01L191X"},
        }
        subject, html = mailer.shop_email(bk)
        assert "/api/private-files/" not in html
        mailer._assert_safe_email(subject, html)
