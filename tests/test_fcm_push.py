import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import get_current_user

client = TestClient(app)


def test_fcm_token_registration_unauthenticated():
    # Clear any dependency overrides
    app.dependency_overrides.clear()
    res = client.post("/api/push/fcm-token", json={"token": "test_token_123", "platform": "android"})
    assert res.status_code == 401


def test_fcm_token_registration_authenticated(monkeypatch):
    test_user = {"id": 99999, "email": "fcm_test@saarthh.in", "role": "user"}
    app.dependency_overrides[get_current_user] = lambda: test_user

    saved = {}
    def mock_save_fcm_token(user_id, token, platform="android"):
        saved["user_id"] = user_id
        saved["token"] = token
        saved["platform"] = platform
        return {
            "id": 1,
            "user_id": user_id,
            "endpoint": token,
            "type": "fcm",
            "preferences": {"budget_alerts": True},
            "created_at": "2026-10-18T10:00:00Z"
        }

    monkeypatch.setattr("app.main.save_fcm_token", mock_save_fcm_token)

    try:
        res = client.post(
            "/api/push/fcm-token",
            json={"token": "sample_firebase_device_token_abc123", "platform": "android"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["subscription"]["endpoint"] == "sample_firebase_device_token_abc123"
        assert data["subscription"]["type"] == "fcm"
        assert saved["token"] == "sample_firebase_device_token_abc123"
    finally:
        app.dependency_overrides.clear()


def test_fcm_token_empty_validation():
    test_user = {"id": 99999, "email": "fcm_test@saarthh.in", "role": "user"}
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        res = client.post(
            "/api/push/fcm-token",
            json={"token": "   ", "platform": "android"}
        )
        assert res.status_code == 400
        assert "Missing or empty" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_fcm_send_fallback_when_unconfigured(monkeypatch):
    from app.push import send_fcm_notification
    monkeypatch.setattr("app.push.get_firebase_app", lambda: False)
    success, err = send_fcm_notification(
        token="dummy_token",
        title="Test Title",
        body="Test Body"
    )
    assert success is False
    assert "Firebase not configured" in err
