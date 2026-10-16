import os, requests, pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://bici-disponibili.preview.emergentagent.com").rstrip("/")

@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

@pytest.fixture(scope="session")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@noleggionuovo.it", "password": "Admin2026!"})
    assert r.status_code == 200, r.text
    return r.json()["token"]

@pytest.fixture(scope="session")
def user_token(api):
    import uuid
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@example.com"
    r = api.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123", "name": "Test User"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    yield token, email
    # Cleanup: cancel any still-active bookings created by this test user
    try:
        bks = api.get(f"{BASE_URL}/api/bookings/me", headers=h(token)).json()
        for b in bks:
            if b.get("status") in ("pending_payment", "confirmed"):
                api.post(f"{BASE_URL}/api/bookings/{b['id']}/cancel", headers=h(token))
    except Exception:
        pass

def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
