"""
Tests for Feature 1 (Persistent Login / Refresh Tokens) and
Feature 2 (Email Verification & OTP) in SAARTH backend.
"""
import secrets
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import (
    get_user_by_email,
    create_user,
    set_user_otp,
    verify_user_email,
    set_user_bypass_verification,
)
from app.auth import hash_password, create_access_token, create_refresh_token
from app.email import validate_email_address, DISPOSABLE_EMAIL_DOMAINS


@pytest.fixture(scope="module")
def client():
    return TestClient(app, base_url="https://api.saarthh.in")


# =====================================================================
# Feature 2 Tests: Email Validation, Disposable Blocklist, OTP, Bypass
# =====================================================================

class TestEmailValidationAndDisposableBlocklist:
    """Test standard regex check and disposable email provider blocking."""

    def test_valid_emails_pass(self):
        valid_cases = [
            "user@gmail.com",
            "jane.doe@outlook.com",
            "support@finance-corp.in",
            "developer+test@company.co",
        ]
        for email in valid_cases:
            valid, msg = validate_email_address(email)
            assert valid is True, f"Expected {email} to be valid, got error: {msg}"

    def test_disposable_domains_blocked(self):
        # Specifically requested disposable providers and top blocklist entries
        blocked_cases = [
            "user@mailinator.com",
            "test@tempmail.com",
            "attacker@guerrillamail.com",
            "fake@10minutemail.com",
            "temp@throwam.com",
            "junk@yopmail.com",
            "burner@trashmail.com",
            "user@sharklasers.com",
            "spam@dispostable.com",
        ]
        for email in blocked_cases:
            valid, msg = validate_email_address(email)
            assert valid is False, f"Expected {email} to be blocked as disposable"
            assert "Disposable email" in msg

    def test_invalid_email_regex_blocked(self):
        invalid_cases = [
            "notanemail",
            "user@",
            "@domain.com",
            "user@domain",
            "user@.com",
            "",
        ]
        for email in invalid_cases:
            valid, msg = validate_email_address(email)
            assert valid is False, f"Expected {email} to fail regex"

    def test_signup_endpoint_blocks_disposable_email(self, client):
        payload = {
            "email": "hacker@mailinator.com",
            "password": "Password123!",
        }
        res = client.post("/auth/signup", json=payload)
        assert res.status_code == 400
        assert "Disposable email" in res.json()["detail"]


class TestEmailVerificationFlow:
    """Test full registration, OTP generation, verification, and expiration."""

    def test_new_user_registration_requires_otp_and_blocks_unverified_login(self, client):
        test_email = f"new_user_otp_{secrets.token_hex(4)}@gmail.com"
        password = "SecurePassword123!"

        # Register new account
        res = client.post("/auth/signup", json={"email": test_email, "password": password})
        assert res.status_code == 200
        data = res.json()
        assert data.get("requires_verification") is True

        # Unverified user cannot log in yet
        login_res = client.post("/auth/login", json={"email": test_email, "password": password})
        assert login_res.status_code == 403
        assert "Email not verified" in login_res.json()["detail"]

        # Fetch stored OTP from DB
        user = get_user_by_email(test_email)
        assert user is not None
        assert user["email_verified"] is False
        assert user["bypass_verification"] is False
        assert user["otp"] is not None
        otp = user["otp"]

        # Test invalid OTP is rejected
        bad_verify = client.post("/auth/verify-otp", json={"email": test_email, "otp": "000000"})
        assert bad_verify.status_code == 400
        assert "Invalid verification code" in bad_verify.json()["detail"]

        # Test correct OTP verifies account and activates login
        ok_verify = client.post("/auth/verify-otp", json={"email": test_email, "otp": otp})
        assert ok_verify.status_code == 200
        verify_data = ok_verify.json()
        assert verify_data["status"] == "ok"
        assert "token" in verify_data
        assert "refresh_token" in ok_verify.cookies

        # User is now verified in DB
        updated_user = get_user_by_email(test_email)
        assert updated_user["email_verified"] is True
        assert updated_user["otp"] is None

        # Verified user can now log in normally
        ok_login = client.post("/auth/login", json={"email": test_email, "password": password})
        assert ok_login.status_code == 200
        assert "token" in ok_login.json()
        assert "refresh_token" in ok_login.cookies

    def test_otp_expires_after_10_min(self, client):
        test_email = f"otp_expiry_{secrets.token_hex(4)}@gmail.com"
        password = "SecurePassword123!"

        # Signup new user
        signup_res = client.post("/auth/signup", json={"email": test_email, "password": password})
        assert signup_res.status_code == 200
        user = get_user_by_email(test_email)
        assert user is not None
        otp = user["otp"]
        assert otp is not None

        # Simulate OTP expiration (set expiry to 11 minutes in the past)
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=1)
        set_user_otp(test_email, otp, expired_time)

        # Attempt verification with expired OTP -> rejected 400
        res = client.post("/auth/verify-otp", json={"email": test_email, "otp": otp})
        assert res.status_code == 400
        assert "expired" in res.json()["detail"].lower()

        # Resend OTP via /auth/send-otp
        resend_res = client.post("/auth/send-otp", json={"email": test_email})
        assert resend_res.status_code == 200
        new_user = get_user_by_email(test_email)
        new_otp = new_user["otp"]
        assert new_otp is not None

        # Verify with fresh OTP succeeds
        fresh_verify = client.post("/auth/verify-otp", json={"email": test_email, "otp": new_otp})
        assert fresh_verify.status_code == 200


class TestGrandfatheredAndBypassUsers:
    """Test that old users and shiv@gmail.com / admin accounts bypass verification."""

    def test_old_user_can_still_login_without_otp(self, client):
        # Create an existing user marked as grandfathered (email_verified=True, bypass_verification=False)
        old_email = "grandfathered_old_user_2026@gmail.com"
        password = "OldUserPassword123!"
        existing = get_user_by_email(old_email)
        if not existing:
            create_user(
                email=old_email,
                password_hash=hash_password(password),
                email_verified=True,
                bypass_verification=False,
            )
        else:
            verify_user_email(old_email)

        # Old grandfathered user logs in directly without OTP
        login_res = client.post("/auth/login", json={"email": old_email, "password": password})
        assert login_res.status_code == 200
        assert "token" in login_res.json()
        assert "refresh_token" in login_res.cookies

    def test_shiv_bypasses_verification(self, client):
        # 1. Verify shiv@gmail.com has bypass_verification=True in DB
        shiv_user = get_user_by_email("shiv@gmail.com")
        assert shiv_user is not None
        assert shiv_user.get("bypass_verification") is True

        # 2. Test that any account with bypass_verification=True bypasses OTP check completely (even if email_verified=False)
        bypass_test_email = "bypass_unverified_tester@test.com"
        bypass_pwd = "BypassPassword123!"
        existing = get_user_by_email(bypass_test_email)
        if not existing:
            create_user(
                email=bypass_test_email,
                password_hash=hash_password(bypass_pwd),
                email_verified=False,
                bypass_verification=True,
            )
        else:
            set_user_bypass_verification(bypass_test_email, True)

        # User logs in directly without requiring OTP
        login_res = client.post("/auth/login", json={"email": bypass_test_email, "password": bypass_pwd})
        assert login_res.status_code == 200
        assert "token" in login_res.json()
        assert "refresh_token" in login_res.cookies


# =====================================================================
# Feature 1 Tests: Persistent Login (Refresh Token Auth & Rotation)
# =====================================================================

class TestPersistentLoginRefreshToken:
    """Test JWT refresh token auth, rotation, cookie storage, and logout."""

    def test_refresh_token_rotation_and_logout_flow(self, client):
        test_email = "refresh_tester_2026@gmail.com"
        password = "RefreshPassword123!"
        user = get_user_by_email(test_email)
        if not user:
            user = create_user(
                email=test_email,
                password_hash=hash_password(password),
                email_verified=True,
                bypass_verification=True,
            )
        else:
            verify_user_email(test_email)

        # 1. Login sets 30-day httpOnly refresh_token cookie
        login_res = client.post("/auth/login", json={"email": test_email, "password": password})
        assert login_res.status_code == 200
        initial_access_token = login_res.json()["token"]
        assert "refresh_token" in login_res.cookies
        initial_refresh_cookie = login_res.cookies["refresh_token"]

        # 2. POST /auth/refresh with refresh_token cookie issues new access token & rotates refresh token
        client.cookies.set("refresh_token", initial_refresh_cookie)
        refresh_res = client.post("/auth/refresh")
        assert refresh_res.status_code == 200
        refresh_data = refresh_res.json()
        new_access_token = refresh_data["token"]
        assert new_access_token != ""
        # Access token was refreshed
        assert "refresh_token" in refresh_res.cookies
        rotated_refresh_cookie = refresh_res.cookies["refresh_token"]
        # Rotated refresh token is different from the initial one (rotation best practice)
        assert rotated_refresh_cookie != initial_refresh_cookie

        # 3. POST /auth/logout clears refresh_token cookie
        logout_res = client.post("/auth/logout")
        assert logout_res.status_code == 200
        assert logout_res.json()["status"] == "ok"
        # Cookie cleared / expired
        cookie_header = logout_res.headers.get("set-cookie", "")
        assert "refresh_token=" in cookie_header
        assert "Max-Age=0" in cookie_header or "expires=" in cookie_header.lower()

    def test_refresh_token_invalid_or_missing_rejected(self, client):
        # Missing refresh token returns 401
        client.cookies.clear()
        res_no_cookie = client.post("/auth/refresh")
        assert res_no_cookie.status_code == 401

        # Invalid refresh token returns 401
        client.cookies.set("refresh_token", "invalid.garbage.jwt")
        res_bad_cookie = client.post("/auth/refresh")
        assert res_bad_cookie.status_code == 401

    def test_cors_and_cookie_domain_configuration(self, client):
        """Test CORS headers and refresh_token cookie attributes for saarthh.in domain."""
        origins = [
            "https://saarthh.in",
            "https://www.saarthh.in",
            "http://localhost:5173",
            "http://localhost:3000",
        ]
        for origin in origins:
            res = client.options(
                "/api/app-status",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert res.headers.get("access-control-allow-origin") == origin
            assert res.headers.get("access-control-allow-credentials") == "true"

        # Verify debug endpoint reports domain and allowed origins
        debug_res = client.get("/api/debug/cookies", headers={"Origin": "https://saarthh.in"})
        assert debug_res.status_code == 200
        data = debug_res.json()
        assert data["is_origin_allowed"] is True
        assert data["cookie_settings"]["domain"] == ".saarthh.in"
        assert data["cookie_settings"]["samesite"].lower() == "none"
        assert data["cookie_settings"]["secure"] is True
        assert "https://saarthh.in" in data["configured_allowed_origins"]


class TestAdminPortalDomainUpdates:
    """Test admin portal domain updates for saarthh.in and api.saarthh.in."""

    def test_admin_allowed_origins(self):
        from app.main import ADMIN_ALLOWED_ORIGINS
        expected = [
            "https://saarthh.in",
            "https://www.saarthh.in",
            "https://api.saarthh.in",
            "http://localhost:5173",
            "http://localhost:8000",
        ]
        for origin in expected:
            assert origin in ADMIN_ALLOWED_ORIGINS, f"{origin} must be in ADMIN_ALLOWED_ORIGINS"

    def test_admin_login_cors_and_cookie(self, client):
        from app.config import settings
        import bcrypt

        # Ensure valid admin credentials for test
        raw_pw = "AdminPass123!"
        settings.ADMIN_PASSWORD_HASH = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        settings.ADMIN_EMAIL = "admin@saarthh.in"

        origins = [
            "https://saarthh.in",
            "https://www.saarthh.in",
            "https://api.saarthh.in",
            "http://localhost:5173",
            "http://localhost:8000",
        ]

        for orig in origins:
            res = client.post(
                "/api/admin/login",
                json={"email": "admin@saarthh.in", "password": raw_pw},
                headers={"Origin": orig},
            )
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == orig
            assert res.headers.get("access-control-allow-credentials") == "true"

            # Check admin_token cookie settings
            set_cookie = res.headers.get("set-cookie", "")
            assert "admin_token=" in set_cookie
            assert "Domain=.saarthh.in" in set_cookie
            assert "HttpOnly" in set_cookie
            assert "Secure" in set_cookie
            assert "SameSite=None" in set_cookie

    def test_admin_cookie_authenticates_dashboard(self, client):
        from app.config import settings
        import bcrypt

        raw_pw = "AdminPass123!"
        settings.ADMIN_PASSWORD_HASH = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        settings.ADMIN_EMAIL = "admin@saarthh.in"

        # Login to receive cookie
        login_res = client.post(
            "/api/admin/login",
            json={"email": "admin@saarthh.in", "password": raw_pw},
        )
        assert login_res.status_code == 200
        admin_token_cookie = login_res.cookies.get("admin_token")
        assert admin_token_cookie is not None

        # Call dashboard with cookie (no Authorization header)
        client.cookies.set("admin_token", admin_token_cookie)
        dash_res = client.get("/api/admin/dashboard")
        assert dash_res.status_code == 200
        assert "stats" in dash_res.json()

        # Logout clears cookie
        logout_res = client.post("/api/admin/logout")
        assert logout_res.status_code == 200
        cookie_header = logout_res.headers.get("set-cookie", "")
        assert "admin_token=" in cookie_header
        assert "Max-Age=0" in cookie_header or "expires=" in cookie_header.lower()


class TestLovableCorsAndPreflightConnectivity:
    """Test CORS, preflight OPTIONS, connectivity /api/ping, and unauthenticated signup/login from Lovable."""

    def test_lovable_in_allow_origins(self):
        from app.main import allowed_origins
        assert "https://saarthai.lovable.app" in allowed_origins

    def test_ping_connectivity_endpoint(self, client):
        res = client.get("/api/ping", headers={"Origin": "https://saarthai.lovable.app"})
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["service"] == "SAARTH"
        assert "timestamp" in data
        assert res.headers.get("access-control-allow-origin") == "https://saarthai.lovable.app"
        assert res.headers.get("access-control-allow-credentials") == "true"

    def test_health_endpoint_cors(self, client):
        res = client.get("/api/health", headers={"Origin": "https://saarthai.lovable.app"})
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}
        assert res.headers.get("access-control-allow-origin") == "https://saarthai.lovable.app"

    def test_options_preflight_handler(self, client):
        routes_to_test = [
            "/api/signup",
            "/api/login",
            "/api/ping",
            "/api/expenses",
            "/api/transactions",
            "/some/arbitrary/path",
        ]
        for route in routes_to_test:
            # Preflight with CORS headers
            res = client.options(
                route,
                headers={
                    "Origin": "https://saarthai.lovable.app",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Content-Type, Authorization, Accept",
                },
            )
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == "https://saarthai.lovable.app"
            assert res.headers.get("access-control-allow-credentials") == "true"
            allow_headers = res.headers.get("access-control-allow-headers", "").lower()
            assert "content-type" in allow_headers

    def test_signup_has_no_auth_dependency(self, client):
        """Ensure POST /api/signup works without any auth token from https://saarthai.lovable.app."""
        email = f"lovable_test_{secrets.token_hex(4)}@gmail.com"
        res = client.post(
            "/api/signup",
            headers={"Origin": "https://saarthai.lovable.app"},
            json={
                "email": email,
                "password": "ValidPassword123!",
                "username": "LovableUser",
            },
        )
        # Should reach the handler and return 200 (OTP sent) with CORS headers
        assert res.status_code == 200
        data = res.json()
        assert data.get("requires_verification") is True
        assert res.headers.get("access-control-allow-origin") == "https://saarthai.lovable.app"
        assert res.headers.get("access-control-allow-credentials") == "true"

    def test_login_has_no_auth_dependency(self, client):
        """Ensure POST /api/login works without any auth token from https://saarthai.lovable.app."""
        res = client.post(
            "/api/login",
            headers={"Origin": "https://saarthai.lovable.app"},
            json={
                "email": "nonexistent@gmail.com",
                "password": "Password123!",
            },
        )
        # Should return 401 Invalid email or password, NOT 403 Forbidden / Not Authenticated
        assert res.status_code == 401
        assert res.json().get("detail") == "Invalid email or password."
        assert res.headers.get("access-control-allow-origin") == "https://saarthai.lovable.app"
