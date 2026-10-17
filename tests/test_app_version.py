"""
Unit and integration tests for App Version Management API endpoints.
- Public endpoint: GET /api/app/version (no auth)
- Admin endpoint: POST /api/admin/app/version (admin auth required)
- Admin read endpoint: GET /api/admin/app/version (admin auth required)
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import create_admin_token
from app.config import settings
from app.db import create_app_version, get_latest_app_version


@pytest.fixture(scope="module")
def client():
    with TestClient(app, base_url="https://api.saarthh.in") as test_client:
        yield test_client


@pytest.fixture(scope="module")
def admin_token():
    return create_admin_token(settings.ADMIN_EMAIL)


class TestAppVersionEndpoints:
    def test_get_app_version_no_auth_required(self, client):
        """GET /api/app/version should return latest version without any auth header."""
        res = client.get("/api/app/version")
        assert res.status_code == 200
        data = res.json()
        assert "version" in data
        assert "download_url" in data
        assert "changelog" in data
        assert "is_forced" in data
        assert "platform" in data
        assert isinstance(data["is_forced"], bool)
        assert data["platform"] == "android"

    def test_admin_post_version_requires_auth(self, client):
        """POST /api/admin/app/version should reject requests without admin credentials."""
        res = client.post(
            "/api/admin/app/version",
            json={
                "version": "1.0.2",
                "download_url": "https://saarthh.in/download/saarth-v1.0.2.apk",
                "changelog": "Test update without auth",
                "is_forced": False,
            },
        )
        assert res.status_code in (401, 403)

    def test_admin_post_version_success_and_retrieval(self, client, admin_token):
        """Admin can post a new version with is_forced flag and public endpoint reflects it."""
        new_version_payload = {
            "version": "1.2.0",
            "download_url": "https://saarthh.in/download/saarth-v1.2.0.apk",
            "changelog": "Critical security release",
            "is_forced": True,
            "platform": "android",
        }
        res = client.post(
            "/api/admin/app/version",
            json=new_version_payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["version"] == "1.2.0"
        assert data["download_url"] == "https://saarthh.in/download/saarth-v1.2.0.apk"
        assert data["changelog"] == "Critical security release"
        assert data["is_forced"] is True
        assert data["platform"] == "android"

        # Verify public endpoint immediately returns this latest version
        pub_res = client.get("/api/app/version")
        assert pub_res.status_code == 200
        pub_data = pub_res.json()
        assert pub_data["version"] == "1.2.0"
        assert pub_data["download_url"] == "https://saarthh.in/download/saarth-v1.2.0.apk"
        assert pub_data["is_forced"] is True

        # Clean up: restore 1.0.0 as latest
        create_app_version(
            version="1.0.0",
            download_url="https://saarthh.in/download/saarth-v1.0.0.apk",
            changelog="First release of SAARTH!",
            is_forced=False,
            platform="android",
        )

    def test_admin_post_version_validation(self, client, admin_token):
        """Validation fails if version or download_url are empty."""
        res_empty_ver = client.post(
            "/api/admin/app/version",
            json={"version": " ", "download_url": "https://saarthh.in/download.apk"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_empty_ver.status_code == 400

        res_empty_url = client.post(
            "/api/admin/app/version",
            json={"version": "1.0.3", "download_url": " "},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_empty_url.status_code == 400

    def test_sms_ingest_endpoint(self, client):
        """Test POST /api/sms/ingest requires auth and processes bank SMS."""
        # Unauthenticated request fails
        unauth = client.post("/api/sms/ingest", json={"sender": "HDFCBK", "body": "Paid Rs 250 to Starbucks on 16-10-2026"})
        assert unauth.status_code in (401, 403)

        # Authenticated user request
        from app.auth import create_access_token
        user_token = create_access_token(1, "test@saarthh.in")
        auth_res = client.post(
            "/api/sms/ingest",
            json={
                "sender": "HDFCBK",
                "body": "Paid Rs 250 to Starbucks on 16-10-2026",
                "timestamp": 1729080000000,
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert auth_res.status_code == 200
        data = auth_res.json()
        assert data["status"] == "ok"
        assert "imported" in data
        assert "duplicates" in data

