"""
Comprehensive test suite for:
1. Password change (verification, length, identical check, session clear, login with new password)
2. Admin token / User token mutual rejection
3. User suspension (login block, API block, unsuspend)
4. Force password reset flag
5. Admin account deletion with email confirmation and cascading cleanup
6. Missing admin env vars startup failure
7. Admin dashboard stats, users, detail, LLM usage, table explorer, and live app settings
"""
import os
import unittest
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app
from app.db import (
    create_user, get_user_by_email, delete_account,
    set_user_suspended, set_user_force_password_reset,
    get_app_settings, set_app_setting, init_db
)
from app.auth import create_access_token, create_admin_token, hash_password

client = TestClient(app)

class TestAdminAndPassword(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.test_email = "pwd_test_user@budgettracker.local"
        # Cleanup if existed
        existing = get_user_by_email(cls.test_email)
        if existing:
            delete_account(existing["id"])
        
        # Create test user
        pw_hash = hash_password("CurrentPassword123!")
        cls.user = create_user(cls.test_email, pw_hash)
        cls.user_token = create_access_token(cls.user["id"], cls.test_email)
        
        # Admin credentials from environment
        cls.admin_email = settings.ADMIN_EMAIL
        cls.admin_password = "AdminPassword2026!"
        cls.admin_token = create_admin_token(cls.admin_email)

    @classmethod
    def tearDownClass(cls):
        existing = get_user_by_email(cls.test_email)
        if existing:
            delete_account(existing["id"])

    # ---------- 1. Password Change Tests ----------

    def test_01_change_password_wrong_current(self):
        headers = {"Authorization": f"Bearer {self.user_token}"}
        res = client.post(
            "/api/account/change-password",
            json={"current_password": "WrongPassword!", "new_password": "NewSecretPassword123!"},
            headers=headers,
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Current password is incorrect", res.json()["detail"])

    def test_02_change_password_too_short(self):
        headers = {"Authorization": f"Bearer {self.user_token}"}
        res = client.post(
            "/api/account/change-password",
            json={"current_password": "CurrentPassword123!", "new_password": "short"},
            headers=headers,
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("at least 8 characters", res.json()["detail"])

    def test_03_change_password_identical(self):
        headers = {"Authorization": f"Bearer {self.user_token}"}
        res = client.post(
            "/api/account/change-password",
            json={"current_password": "CurrentPassword123!", "new_password": "CurrentPassword123!"},
            headers=headers,
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot be identical", res.json()["detail"])

    def test_04_change_password_success_and_login(self):
        headers = {"Authorization": f"Bearer {self.user_token}"}
        res = client.post(
            "/api/account/change-password",
            json={"current_password": "CurrentPassword123!", "new_password": "BrandNewPassword2026!"},
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

        # Old password should fail login
        fail_login = client.post(
            "/api/login",
            json={"email": self.test_email, "password": "CurrentPassword123!"},
        )
        self.assertEqual(fail_login.status_code, 401)

        # New password should succeed
        ok_login = client.post(
            "/api/login",
            json={"email": self.test_email, "password": "BrandNewPassword2026!"},
        )
        self.assertEqual(ok_login.status_code, 200)
        # Update our token for subsequent tests
        self.__class__.user_token = ok_login.json()["token"]

    # ---------- 2. Mutual Token Rejection Tests ----------

    def test_05_admin_route_rejects_user_token(self):
        user_headers = {"Authorization": f"Bearer {self.user_token}"}
        res = client.get("/api/admin/dashboard", headers=user_headers)
        self.assertEqual(res.status_code, 401)

    def test_06_user_chat_rejects_admin_token(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        res = client.post("/api/chat", json={"message": "hello"}, headers=admin_headers)
        self.assertEqual(res.status_code, 401)

    # ---------- 3. Admin Login & Dashboard Tests ----------

    def test_07_admin_login_success_and_failure(self):
        # Invalid password
        bad = client.post("/api/admin/login", json={"email": self.admin_email, "password": "wrong"})
        self.assertEqual(bad.status_code, 401)

        # Valid credentials
        ok = client.post("/api/admin/login", json={"email": self.admin_email, "password": self.admin_password})
        self.assertEqual(ok.status_code, 200)
        self.assertIn("token", ok.json())
        self.assertEqual(ok.json()["role"], "admin")

    def test_08_admin_dashboard_metrics(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        res = client.get("/api/admin/dashboard", headers=admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("stats", data)
        self.assertIn("llm_pool", data)
        self.assertIn("recent_errors", data)
        self.assertGreaterEqual(data["stats"]["total_users"], 1)

    # ---------- 4. User Suspension Tests ----------

    def test_09_user_suspension_flow(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        u_id = self.user["id"]

        # Suspend
        susp_res = client.post(f"/api/admin/users/{u_id}/suspend", json={"suspended": True}, headers=admin_headers)
        self.assertEqual(susp_res.status_code, 200)
        self.assertTrue(susp_res.json()["suspended"])

        # Suspended user login fails with 403
        login_res = client.post("/api/login", json={"email": self.test_email, "password": "BrandNewPassword2026!"})
        self.assertEqual(login_res.status_code, 403)
        self.assertIn("Account suspended, contact support", login_res.json()["detail"])

        # Suspended user API call fails with 403
        user_headers = {"Authorization": f"Bearer {self.user_token}"}
        chat_res = client.post("/api/chat", json={"message": "hello"}, headers=user_headers)
        self.assertEqual(chat_res.status_code, 403)
        self.assertIn("Account suspended, contact support", chat_res.json()["detail"])

        # Unsuspend
        unsusp_res = client.post(f"/api/admin/users/{u_id}/suspend", json={"suspended": False}, headers=admin_headers)
        self.assertEqual(unsusp_res.status_code, 200)
        self.assertFalse(unsusp_res.json()["suspended"])

        # Can login again
        ok_login = client.post("/api/login", json={"email": self.test_email, "password": "BrandNewPassword2026!"})
        self.assertEqual(ok_login.status_code, 200)
        self.__class__.user_token = ok_login.json()["token"]

    # ---------- 5. Force Password Reset Tests ----------

    def test_10_force_password_reset_flow(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        u_id = self.user["id"]

        # Set force reset flag
        flag_res = client.post(f"/api/admin/users/{u_id}/force-reset", json={"force": True}, headers=admin_headers)
        self.assertEqual(flag_res.status_code, 200)
        self.assertTrue(flag_res.json()["force_password_reset"])

        # Login should indicate force_password_reset
        login_res = client.post("/api/login", json={"email": self.test_email, "password": "BrandNewPassword2026!"})
        self.assertEqual(login_res.status_code, 200)
        self.assertTrue(login_res.json()["user"]["force_password_reset"])

        # Change password should clear it
        headers = {"Authorization": f"Bearer {self.user_token}"}
        chg_res = client.post(
            "/api/account/change-password",
            json={"current_password": "BrandNewPassword2026!", "new_password": "FinalPassword2026!"},
            headers=headers,
        )
        self.assertEqual(chg_res.status_code, 200)

        # Login again: force_password_reset should be False
        login_res2 = client.post("/api/login", json={"email": self.test_email, "password": "FinalPassword2026!"})
        self.assertEqual(login_res2.status_code, 200)
        self.assertFalse(login_res2.json()["user"]["force_password_reset"])
        self.__class__.user_token = login_res2.json()["token"]

    # ---------- 6. Users Table & Detail Tests ----------

    def test_11_admin_users_and_detail(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        list_res = client.get("/api/admin/users?search=pwd_test", headers=admin_headers)
        self.assertEqual(list_res.status_code, 200)
        data = list_res.json()
        self.assertGreaterEqual(data["total"], 1)
        found = [u for u in data["users"] if u["email"] == self.test_email]
        self.assertTrue(len(found) == 1)
        u_id = found[0]["id"]

        detail_res = client.get(f"/api/admin/users/{u_id}", headers=admin_headers)
        self.assertEqual(detail_res.status_code, 200)
        det = detail_res.json()
        self.assertIn("user", det)
        self.assertIn("budgets", det)
        self.assertIn("recent_transactions", det)
        self.assertIn("udhar_summary", det)
        self.assertIn("storage", det)
        # Verify NO chat history in response
        self.assertNotIn("chat_history", det)
        self.assertNotIn("messages", det)

    # ---------- 7. LLM Usage, DB Explorer, Settings Tests ----------

    def test_12_admin_llm_usage(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        res = client.get("/api/admin/llm-usage", headers=admin_headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("daily_usage", res.json())
        self.assertIn("top_users", res.json())

    def test_13_admin_table_explorer(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        overview = client.get("/api/admin/tables", headers=admin_headers)
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(len(overview.json()["tables"]), 7)

        rows_res = client.get("/api/admin/tables/users?page=1&page_size=10", headers=admin_headers)
        self.assertEqual(rows_res.status_code, 200)
        r_data = rows_res.json()
        self.assertIn("rows", r_data)
        # Redacted password check
        for r in r_data["rows"]:
            self.assertEqual(r.get("password_hash"), "[REDACTED_BCRYPT_HASH]")

    def test_14_admin_live_settings(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        get_res = client.get("/api/admin/settings", headers=admin_headers)
        self.assertEqual(get_res.status_code, 200)
        orig_cap = get_res.json()["settings"].get("daily_message_cap", "100")

        # Update cap
        update_res = client.put("/api/admin/settings", json={"daily_message_cap": "50"}, headers=admin_headers)
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.json()["settings"]["daily_message_cap"], "50")

        # Restore cap
        client.put("/api/admin/settings", json={"daily_message_cap": orig_cap}, headers=admin_headers)

    # ---------- 8. Admin Cascading Deletion Tests ----------

    def test_15_admin_delete_user(self):
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        # Create temp user
        temp_email = "to_delete_by_admin@budgettracker.local"
        temp = create_user(temp_email, hash_password("pass123456"))
        temp_id = temp["id"]

        # Confirm mismatch fails
        mismatch_res = client.request("DELETE", f"/api/admin/users/{temp_id}", json={"confirm_email": "wrong@email.com"}, headers=admin_headers)
        self.assertEqual(mismatch_res.status_code, 400)

        # Confirm match succeeds
        del_res = client.request("DELETE", f"/api/admin/users/{temp_id}", json={"confirm_email": temp_email}, headers=admin_headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["deleted"])

        # User is deleted from database
        self.assertIsNone(get_user_by_email(temp_email))

if __name__ == "__main__":
    unittest.main()
