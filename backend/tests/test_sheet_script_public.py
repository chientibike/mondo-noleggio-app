"""Tests for public Apps Script code pages (/api/codice and /api/sheet-script/{token})."""
import os
import requests
import pytest

BASE_URL = "https://bici-disponibili.preview.emergentagent.com"
TOKEN = "021dee45385e24db3f807670a1957c32"
ADMIN_EMAIL = "admin@noleggionuovo.it"
ADMIN_PASSWORD = "Admin2026!"


def _assert_html_page(html: str):
    assert "Codice da incollare in Apps Script" in html, "Missing H2 title"
    assert "Copia codice" in html, "Missing Copia codice button text"
    assert 'id="c"' in html, "Missing <pre id='c'>"
    assert f"const TOKEN = &#x27;{TOKEN}&#x27;" in html or f"const TOKEN = '{TOKEN}'" in html, (
        "TOKEN constant with current SHEET_SCRIPT_TOKEN not present in page"
    )
    assert "function doPost" in html, "Missing function doPost in Apps Script"


class TestPublicCodicePage:
    def test_codice_returns_200_html(self):
        r = requests.get(f"{BASE_URL}/api/codice", timeout=20)
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
        ctype = r.headers.get("content-type", "")
        assert "text/html" in ctype, f"content-type={ctype}"
        _assert_html_page(r.text)

    def test_sheet_script_with_valid_token(self):
        r = requests.get(f"{BASE_URL}/api/sheet-script/{TOKEN}", timeout=20)
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
        assert "text/html" in r.headers.get("content-type", "")
        _assert_html_page(r.text)

    def test_sheet_script_wrong_token_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/sheet-script/wrongtoken", timeout=20)
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"


class TestAdminSheetScript:
    @pytest.fixture(scope="class")
    def admin_token(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        tok = data.get("token") or data.get("access_token")
        assert tok, f"no token in login response: {data}"
        return tok

    def test_admin_sheet_script_still_works(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/sheet/script",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "script" in body and isinstance(body["script"], str)
        assert f"const TOKEN = '{TOKEN}'" in body["script"], "TOKEN not injected in script"
        assert "function doPost" in body["script"]
        assert "url" in body  # may be None/empty, just key present
