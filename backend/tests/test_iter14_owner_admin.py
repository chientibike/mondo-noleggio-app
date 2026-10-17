"""Iteration 14 — owner email (info@chientibike.it) becomes admin on Google sign-in.

Covers:
- Register with owner email (any case) -> 409
- Register random email -> 200
- Google session (mocked httpx) for owner -> role=admin, me/admin routes work
- Promotion of pre-existing non-admin owner doc, with password_hash removed
- Non-owner Google email (mocked) -> role=user
- Invalid session_id (real call) -> 401
- Regression: admin@noleggionuovo.it login still works
- CLEANUP: delete every info@chientibike.it doc at the end
"""
import asyncio
import os
import uuid

import httpx
import pytest
import requests
import respx
from motor.motor_asyncio import AsyncIOMotorClient

# Make sure server reads the env (same vars supervisor uses)
os.environ.setdefault("OWNER_ADMIN_EMAILS", "info@chientibike.it")

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://bici-disponibili.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = "info@chientibike.it"


# ----------------- Mongo cleanup helper -----------------
def _mongo_db():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return cli, cli[os.environ["DB_NAME"]]


async def _delete_owner_users():
    cli, db = _mongo_db()
    try:
        res = await db.users.delete_many({"email": OWNER_EMAIL})
        return res.deleted_count
    finally:
        cli.close()


@pytest.fixture(scope="module")
def shared_loop():
    """One asyncio loop for the whole module; motor binds to the first loop it's used in."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup_owner(shared_loop):
    """Delete every info@chientibike.it user and any leaked test_iter14_* user before and after."""
    async def _cleanup_all():
        cli, db = _mongo_db()
        try:
            o = await db.users.delete_many({"email": OWNER_EMAIL})
            import re as _re
            t = await db.users.delete_many({"email": {"$regex": _re.compile(r"^test_iter14_")}})
            return o.deleted_count, t.deleted_count
        finally:
            cli.close()
    shared_loop.run_until_complete(_cleanup_all())
    yield
    owner_c, test_c = shared_loop.run_until_complete(_cleanup_all())
    print(f"\n[CLEANUP] Removed {owner_c} info@chientibike.it + {test_c} test_iter14_* user doc(s) after tests.")


# ----------------- 1. Register with owner email (live backend) -----------------
class TestRegisterOwnerBlocked:
    def test_register_owner_lowercase_409(self):
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": OWNER_EMAIL, "password": "whatever123", "name": "Owner",
        }, timeout=15)
        assert r.status_code == 409, r.text
        assert "Continua con Google" in r.json()["detail"]

    def test_register_owner_uppercase_409(self):
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": "INFO@ChientiBike.IT", "password": "whatever123", "name": "Owner",
        }, timeout=15)
        assert r.status_code == 409, r.text
        assert "Continua con Google" in r.json()["detail"]

    def test_register_random_email_200_role_user(self):
        # backend lowercases via .strip().lower()
        email = f"test_iter14_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": "whatever123", "name": "Rand",
        }, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user"]["role"] == "user"
        assert body["user"]["email"] == email
        assert "token" in body

        # Cleanup this test user
        async def _rm():
            cli, db = _mongo_db()
            try:
                await db.users.delete_one({"email": email})
            finally:
                cli.close()
        asyncio.get_event_loop().run_until_complete(_rm())


# ----------------- 2. Invalid session_id (real call to real Emergent) -----------------
def test_invalid_session_id_401_live():
    r = requests.post(f"{BASE_URL}/api/auth/session",
                      json={"session_id": "definitely-not-a-real-session-" + uuid.uuid4().hex},
                      timeout=20)
    assert r.status_code == 401, r.text
    assert "Google" in r.json()["detail"] or "non valid" in r.json()["detail"].lower()


# ----------------- 3. Regression: admin login still works -----------------
def test_admin_login_regression():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@noleggionuovo.it", "password": "Admin2026!"},
                      timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["role"] == "admin"
    assert body["user"]["email"] == "admin@noleggionuovo.it"

    # Verify token works on an admin route
    tok = body["token"]
    stats = requests.get(f"{BASE_URL}/api/admin/stats",
                        headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert stats.status_code == 200, stats.text


# ----------------- 4. Mocked Google session via ASGI transport -----------------
# Build the FastAPI app in-process. Mock httpx.AsyncClient inside server module so
# the google_session call to demobackend.emergentagent.com returns our fixture.

@pytest.fixture(scope="module")
def server_mod():
    """Import the server module once per module."""
    import importlib, sys, os as _os
    _os.environ["OWNER_ADMIN_EMAILS"] = "info@chientibike.it"
    # Reload to make sure OWNER_ADMIN_EMAILS is picked up (is_owner_email reads env every call -> no reload needed)
    if "server" in sys.modules:
        return sys.modules["server"]
    sys.path.insert(0, "/app/backend")
    return importlib.import_module("server")


SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


async def _call_session(server_mod, session_id: str):
    transport = httpx.ASGITransport(app=server_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/api/auth/session", json={"session_id": session_id})


async def _call_me(server_mod, token: str):
    transport = httpx.ASGITransport(app=server_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})


async def _call_admin_stats(server_mod, token: str):
    transport = httpx.ASGITransport(app=server_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token}"})


class TestGoogleSessionOwnerBecomesAdmin:
    def test_new_owner_signs_in_with_google_becomes_admin(self, server_mod, shared_loop):
        loop = shared_loop
        try:
            with respx.mock(assert_all_called=False) as mock:
                mock.get(SESSION_URL).mock(return_value=httpx.Response(200, json={"email": OWNER_EMAIL, "name": "Chienti Bike", "picture": None}))
                # Allow ASGI calls to pass through
                mock.route(host="testserver").pass_through()
                r = loop.run_until_complete(_call_session(server_mod, "mock-session-id-owner"))
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["user"]["email"] == OWNER_EMAIL
                assert body["user"]["role"] == "admin", f"owner must be admin, got {body['user']}"
                token = body["session_token"]
                assert token

                # /auth/me returns admin
                r2 = loop.run_until_complete(_call_me(server_mod, token))
                assert r2.status_code == 200, r2.text
                assert r2.json()["role"] == "admin"

                # Admin route works
                r3 = loop.run_until_complete(_call_admin_stats(server_mod, token))
                assert r3.status_code == 200, r3.text
                data = r3.json()
                assert "bike_models" in data and "active_bookings" in data
        finally:
            pass  # shared loop
            pass

    def test_promotion_removes_password_hash(self, server_mod, shared_loop):
        """Pre-insert a user doc with role=user + password_hash; after mocked Google session
        the account must be role=admin and the password_hash must be gone (so login fails)."""
        async def _seed():
            cli, db = _mongo_db()
            try:
                await db.users.delete_many({"email": OWNER_EMAIL})
                import bcrypt
                await db.users.insert_one({
                    "id": uuid.uuid4().hex,
                    "email": OWNER_EMAIL,
                    "name": "Owner",
                    "role": "user",
                    "password_hash": bcrypt.hashpw(b"OldPass123!", bcrypt.gensalt()).decode(),
                    "created_at": "2026-01-01T00:00:00+00:00",
                })
            finally:
                cli.close()
        asyncio.get_event_loop().run_until_complete(_seed())

        # Confirm login works with the seeded password BEFORE Google promotion
        r_before = requests.post(f"{BASE_URL}/api/auth/login",
                                 json={"email": OWNER_EMAIL, "password": "OldPass123!"},
                                 timeout=15)
        assert r_before.status_code == 200, f"seed password should work before promotion: {r_before.text}"

        loop = shared_loop
        try:
            with respx.mock(assert_all_called=False) as mock:
                mock.get(SESSION_URL).mock(return_value=httpx.Response(200, json={"email": OWNER_EMAIL, "name": "Chienti Bike", "picture": None}))
                mock.route(host="testserver").pass_through()
                r = loop.run_until_complete(_call_session(server_mod, "mock-session-id-promote"))
                assert r.status_code == 200, r.text
                assert r.json()["user"]["role"] == "admin"
        finally:
            pass  # shared loop
            pass

        # Login with the old password must now fail (password_hash was unset)
        r_after = requests.post(f"{BASE_URL}/api/auth/login",
                                json={"email": OWNER_EMAIL, "password": "OldPass123!"},
                                timeout=15)
        assert r_after.status_code == 401, f"old password must stop working after promotion, got {r_after.status_code} {r_after.text}"

        # Verify Mongo: role=admin, no password_hash
        async def _check():
            cli, db = _mongo_db()
            try:
                return await db.users.find_one({"email": OWNER_EMAIL}, {"_id": 0})
            finally:
                cli.close()
        doc = asyncio.get_event_loop().run_until_complete(_check())
        assert doc is not None
        assert doc["role"] == "admin"
        assert "password_hash" not in doc, f"password_hash must be unset after promotion, got keys={list(doc.keys())}"


class TestGoogleSessionNonOwnerStaysUser:
    def test_non_owner_google_email_role_user(self, server_mod, shared_loop):
        test_email = f"test_iter14_g_{uuid.uuid4().hex[:8]}@example.com"
        loop = shared_loop
        try:
            with respx.mock(assert_all_called=False) as mock:
                mock.get(SESSION_URL).mock(return_value=httpx.Response(200, json={"email": test_email, "name": "Random Google User", "picture": None}))
                mock.route(host="testserver").pass_through()
                r = loop.run_until_complete(_call_session(server_mod, "mock-session-id-user"))
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["user"]["email"] == test_email
                assert body["user"]["role"] == "user"
        finally:
            pass  # shared loop
            pass

        # Cleanup
        async def _rm():
            cli, db = _mongo_db()
            try:
                await db.users.delete_one({"email": test_email})
            finally:
                cli.close()
        asyncio.get_event_loop().run_until_complete(_rm())


class TestGoogleSessionInvalidMocked:
    def test_mocked_401_from_emergent_returns_401(self, server_mod, shared_loop):
        loop = shared_loop
        try:
            with respx.mock(assert_all_called=False) as mock:
                mock.get(SESSION_URL).mock(return_value=httpx.Response(401, json={"detail": "no"}))
                mock.route(host="testserver").pass_through()
                r = loop.run_until_complete(_call_session(server_mod, "mock-session-id-bad"))
                assert r.status_code == 401, r.text
        finally:
            pass  # shared loop
            pass
