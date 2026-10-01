"""
End-to-end HTTP integration verification test against live server on port 8000.
"""
import io
import json
import urllib.request
import urllib.parse
import unittest

BASE_URL = "http://127.0.0.1:8000"

class TestE2EEndpoints(unittest.TestCase):
    def request(self, path, method="GET", data=None, token=None, content_type="application/json"):
        url = BASE_URL + path
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        body = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body = json.dumps(data).encode("utf-8")
            else:
                body = data
                
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read()
                try:
                    return resp.status, json.loads(resp_body.decode("utf-8")), resp.headers
                except Exception:
                    return resp.status, resp_body, resp.headers
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            try:
                return e.code, json.loads(resp_body.decode("utf-8")), e.headers
            except Exception:
                return e.code, resp_body, e.headers

    def setUp(self):
        # Authenticate test user
        email = "e2e_tier3_tester@example.com"
        password = "strongpassword123"
        status, res, _ = self.request("/api/signup", method="POST", data={"email": email, "password": password})
        if status != 200:
            status, res, _ = self.request("/api/login", method="POST", data={"email": email, "password": password})
            
        self.assertEqual(status, 200)
        self.token = res["token"]
        self.user_id = res["user"]["id"]

    def test_01_health_and_frontend(self):
        status, body, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"ABT", body)
        self.assertIn(b"view-calendar", body)
        self.assertIn(b"view-bills", body)
        self.assertIn(b"view-import", body)
        self.assertIn(b"view-settings", body)
        self.assertIn(b"modal-udhar-reminder", body)

    def test_02_calendar_endpoint(self):
        status, data, _ = self.request("/api/calendar?month=2026-10", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(data["month"], "2026-10")
        self.assertIn("days", data)
        self.assertIn("kpis", data)
        self.assertEqual(len(data["days"]), 31)

    def test_03_import_preview_and_confirm(self):
        # 1. Preview text import
        sample_text = "Paid Rs 350 to Swiggy on 12-10-2026\nCredited INR 15000 from Client on 10-10-2026"
        status, data, _ = self.request("/api/import/preview", method="POST", data={"text": sample_text}, token=self.token)
        self.assertEqual(status, 200)
        self.assertIn("rows", data)
        self.assertIn("summary", data)
        self.assertEqual(data["summary"]["total_rows"], 2)

        # 2. Confirm import
        rows_to_save = [
            {
                "date": "2026-10-12",
                "amount": 350.0,
                "category": "eating out",
                "note": "Paid to Swiggy",
                "merchant": "Swiggy",
                "is_credit": False,
                "import_credit": False,
            }
        ]
        status, conf_res, _ = self.request("/api/import/confirm", method="POST", data={"rows": rows_to_save}, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(conf_res["imported_transactions"], 1)

    def test_04_user_display_and_categories(self):
        # 1. Get user display
        status, disp, _ = self.request("/api/user/display", token=self.token)
        self.assertEqual(status, 200)
        self.assertIn("email", disp)

        # 2. Set username
        status, u_res, _ = self.request("/api/user/username", method="POST", data={"username": "shiv_tracker"}, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(u_res["username"], "shiv_tracker")

        # 3. Set avatar
        status, av_res, _ = self.request("/api/user/avatar", method="POST", data={"avatar_id": 4}, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(av_res["avatar_id"], 4)

        # 4. Custom categories
        status, cat_res, _ = self.request("/api/categories", token=self.token)
        self.assertEqual(status, 200)
        self.assertIn("categories", cat_res)

        # Add category
        status, add_cat, _ = self.request("/api/categories", method="POST", data={"name": "Gaming"}, token=self.token)
        self.assertEqual(status, 200)

        # Delete category
        status, del_cat, _ = self.request("/api/categories/gaming", method="DELETE", token=self.token)
        self.assertEqual(status, 200)

    def test_05_push_vapid_key_endpoint(self):
        status, res, _ = self.request("/api/push/vapid-key")
        self.assertEqual(status, 200)
        self.assertIn("public_key", res)
        self.assertTrue(len(res["public_key"]) > 20)

    def test_06_projections_endpoint(self):
        status, res, _ = self.request("/api/projections", token=self.token)
        self.assertEqual(status, 200)
        self.assertIn("projections", res)
        self.assertIsInstance(res["projections"], list)

if __name__ == "__main__":
    unittest.main()
