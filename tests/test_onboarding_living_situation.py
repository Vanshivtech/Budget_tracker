"""
Tests for onboarding living_situation validation and sanitizer in SAARTH backend.
Covers:
1. Canonical enum values: 'with_family', 'alone', 'with_roommates', 'with_partner'
2. Human-readable string sanitization ('With family', 'With roommates', etc.)
3. Rejection of invalid values with clear error message
4. End-to-end API tests for POST /api/onboarding/complete and GET /api/onboarding/defaults
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app, OnboardingCompleteRequest, OnboardingCategoryItem
from app.db import (
    VALID_LIVING_SITUATIONS,
    sanitize_living_situation,
    get_user_profile,
    get_user_by_email,
    create_user,
)
from app.auth import create_access_token


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    test_email = "living_situation_test@example.com"
    user = get_user_by_email(test_email)
    if not user:
        created = create_user(test_email, "TestPassword123!")
        user_id = created["id"]
    else:
        user_id = user["id"]
    token = create_access_token(user_id=user_id, email=test_email)
    return {"Authorization": f"Bearer {token}"}, user_id


class TestLivingSituationSanitizer:
    """Test unit-level normalization and sanitization."""

    def test_all_four_canonical_values(self):
        for canonical in ("with_family", "alone", "with_roommates", "with_partner"):
            assert sanitize_living_situation(canonical) == canonical
            assert canonical in VALID_LIVING_SITUATIONS

    def test_human_readable_transformations(self):
        cases = {
            "With family": "with_family",
            "with family": "with_family",
            "Living with family": "with_family",
            "family": "with_family",
            "WITH_FAMILY": "with_family",
            "Alone": "alone",
            "living alone": "alone",
            "Living alone / renting": "alone",
            "With roommates": "with_roommates",
            "with roommates": "with_roommates",
            "roommates": "with_roommates",
            "With partner": "with_partner",
            "with partner": "with_partner",
            "partner": "with_partner",
            "with-partner": "with_partner",
        }
        for raw, expected in cases.items():
            assert sanitize_living_situation(raw) == expected, f"Failed for {raw}"

    def test_invalid_values_return_none(self):
        invalid_cases = ["on_mars", "unknown", "invalid", "", None, 123, "hotel"]
        for val in invalid_cases:
            assert sanitize_living_situation(val) is None


class TestOnboardingModelValidation:
    """Test OnboardingCompleteRequest Pydantic model validation and sanitization."""

    def test_model_accepts_canonical_values(self):
        categories = [OnboardingCategoryItem(name="groceries", amount=5000, enabled=True)]
        for canonical in ("with_family", "alone", "with_roommates", "with_partner"):
            req = OnboardingCompleteRequest(
                living_situation=canonical,
                monthly_income=50000,
                categories=categories,
            )
            assert req.living_situation == canonical

    def test_model_sanitizes_human_readable_strings(self):
        categories = [OnboardingCategoryItem(name="groceries", amount=5000, enabled=True)]
        req1 = OnboardingCompleteRequest(
            living_situation="With family",
            monthly_income=50000,
            categories=categories,
        )
        assert req1.living_situation == "with_family"

        req2 = OnboardingCompleteRequest(
            living_situation="With roommates",
            monthly_income=50000,
            categories=categories,
        )
        assert req2.living_situation == "with_roommates"

        req3 = OnboardingCompleteRequest(
            living_situation="With partner",
            monthly_income=50000,
            categories=categories,
        )
        assert req3.living_situation == "with_partner"


class TestOnboardingCompleteAPI:
    """Test POST /api/onboarding/complete API endpoint."""

    @pytest.mark.parametrize("situation", ["with_family", "alone", "with_roommates", "with_partner"])
    def test_api_accepts_all_four_canonical_values(self, client, auth_headers, situation):
        headers, user_id = auth_headers
        payload = {
            "living_situation": situation,
            "monthly_income": 60000,
            "categories": [
                {"name": "groceries", "amount": 6000, "enabled": True},
                {"name": "travel", "amount": 3000, "enabled": True},
            ],
        }
        res = client.post("/api/onboarding/complete", json=payload, headers=headers)
        assert res.status_code == 200, f"Failed for {situation}: {res.text}"
        data = res.json()
        assert data.get("status") == "ok"
        profile = get_user_profile(user_id)
        assert profile.get("living_situation") == situation

    def test_api_accepts_human_readable_with_family(self, client, auth_headers):
        headers, user_id = auth_headers
        payload = {
            "living_situation": "With family",
            "monthly_income": 70000,
            "categories": [{"name": "groceries", "amount": 7000, "enabled": True}],
        }
        res = client.post("/api/onboarding/complete", json=payload, headers=headers)
        assert res.status_code == 200, f"Error: {res.text}"
        profile = get_user_profile(user_id)
        assert profile.get("living_situation") == "with_family"

    def test_api_accepts_human_readable_with_partner(self, client, auth_headers):
        headers, user_id = auth_headers
        payload = {
            "living_situation": "With partner",
            "monthly_income": 70000,
            "categories": [{"name": "groceries", "amount": 7000, "enabled": True}],
        }
        res = client.post("/api/onboarding/complete", json=payload, headers=headers)
        assert res.status_code == 200, f"Error: {res.text}"
        profile = get_user_profile(user_id)
        assert profile.get("living_situation") == "with_partner"

    def test_api_rejects_invalid_living_situation(self, client, auth_headers):
        headers, _ = auth_headers
        payload = {
            "living_situation": "on_mars",
            "monthly_income": 50000,
            "categories": [{"name": "groceries", "amount": 5000, "enabled": True}],
        }
        res = client.post("/api/onboarding/complete", json=payload, headers=headers)
        assert res.status_code == 400
        data = res.json()
        assert "Invalid living_situation" in data["detail"]
        assert "with_family" in data["detail"]
        assert "with_roommates" in data["detail"]
        assert "with_partner" in data["detail"]

    @pytest.mark.parametrize(
        "raw_sit,expected_sit",
        [
            ("with_family", "with_family"),
            ("alone", "alone"),
            ("with_roommates", "with_roommates"),
            ("with_partner", "with_partner"),
            ("With family", "with_family"),
            ("With roommates", "with_roommates"),
        ],
    )
    def test_onboarding_defaults_endpoint(self, client, raw_sit, expected_sit):
        res = client.get(f"/api/onboarding/defaults?income=50000&living_situation={raw_sit}")
        assert res.status_code == 200
        data = res.json()
        assert data["living_situation"] == expected_sit
        assert "defaults" in data
        assert isinstance(data["defaults"], dict)
