import sys
import os
sys.path.insert(0, ".")

import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.db import create_user, delete_account, get_user_by_email, get_recent_expenses, get_udhar_summary
from app.agent import check_budget_status
from app.auth import hash_password, create_access_token

class TestManualManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        
        # User 1
        cls.u1_email = "manual_u1@budgettracker.local"
        ex1 = get_user_by_email(cls.u1_email)
        if ex1:
            delete_account(ex1["id"])
        cls.u1 = create_user(cls.u1_email, hash_password("Password123!"))
        cls.t1 = create_access_token(cls.u1["id"], cls.u1_email)
        cls.h1 = {"Authorization": f"Bearer {cls.t1}"}

        # User 2 (for isolation testing)
        cls.u2_email = "manual_u2@budgettracker.local"
        ex2 = get_user_by_email(cls.u2_email)
        if ex2:
            delete_account(ex2["id"])
        cls.u2 = create_user(cls.u2_email, hash_password("Password123!"))
        cls.t2 = create_access_token(cls.u2["id"], cls.u2_email)
        cls.h2 = {"Authorization": f"Bearer {cls.t2}"}

    @classmethod
    def tearDownClass(cls):
        delete_account(cls.u1["id"])
        delete_account(cls.u2["id"])

    def test_01_manual_expense_crud_and_agent_reflection(self):
        # 1. Add expense manually
        resp = self.client.post("/api/transactions", headers=self.h1, json={
            "amount": 450.0,
            "category": "Food",
            "note": "Office lunch cafeteria",
            "date": "2026-10-01T12:30:00Z",
            "tag": "office",
            "merchant": "Cafeteria"
        })
        self.assertEqual(resp.status_code, 200)
        tx = resp.json()
        tx_id = tx["id"]
        self.assertEqual(tx["amount"], 450.0)
        self.assertEqual(tx["category"], "food")
        self.assertIn("office", tx["tags"])

        # Confirm appears in chat agent's get_recent_expenses
        agent_expenses = get_recent_expenses(self.u1["id"], limit=5)
        found = any(e["id"] == tx_id and e["amount"] == 450.0 for e in agent_expenses)
        self.assertTrue(found, "Manual expense not found in get_recent_expenses")

        # Confirm isolation: User 2 cannot see it
        u2_txs = self.client.get("/api/transactions", headers=self.h2).json()["transactions"]
        self.assertFalse(any(e["id"] == tx_id for e in u2_txs))

        # 2. Edit expense manually
        resp_edit = self.client.put(f"/api/transactions/{tx_id}", headers=self.h1, json={
            "amount": 550.0,
            "category": "Food",
            "note": "Office lunch buffet",
            "date": "2026-10-01T13:00:00Z",
            "tags": ["office", "buffet"],
            "merchant": "Buffet Express"
        })
        self.assertEqual(resp_edit.status_code, 200)
        updated_tx = resp_edit.json()
        self.assertEqual(updated_tx["amount"], 550.0)
        self.assertEqual(updated_tx["note"], "Office lunch buffet")
        self.assertIn("buffet", updated_tx["tags"])

        # User 2 cannot edit User 1's transaction
        u2_edit = self.client.put(f"/api/transactions/{tx_id}", headers=self.h2, json={"amount": 999.0})
        self.assertEqual(u2_edit.status_code, 404)

        # Confirm chat agent's check_budget_status reflects updated amount
        status_text = check_budget_status.invoke({"category": "food"}, config={"configurable": {"user_id": self.u1["id"]}})
        self.assertIn("550", status_text)

        # 3. Add second transaction and test bulk delete
        resp_tx2 = self.client.post("/api/transactions", headers=self.h1, json={
            "amount": 120.0,
            "category": "Transport",
            "note": "Metro card"
        })
        tx2_id = resp_tx2.json()["id"]

        bulk_resp = self.client.post("/api/transactions/bulk-delete", headers=self.h1, json={
            "transaction_ids": [tx_id, tx2_id]
        })
        self.assertEqual(bulk_resp.status_code, 200)
        self.assertEqual(bulk_resp.json()["deleted_count"], 2)

        # Confirm deleted
        check_del = self.client.get("/api/transactions", headers=self.h1).json()["transactions"]
        self.assertFalse(any(e["id"] in (tx_id, tx2_id) for e in check_del))

    def test_02_budget_manager_crud(self):
        # 1. Fetch budgets manager
        res = self.client.get("/api/budgets", headers=self.h1)
        self.assertEqual(res.status_code, 200)
        budgets = res.json()["budgets"]
        self.assertIsInstance(budgets, list)
        self.assertTrue(any(b["category"] == "food" for b in budgets))

        # 2. Add / set budget for a new category
        res_add = self.client.post("/api/budgets", headers=self.h1, json={
            "category": "Gaming",
            "monthly_limit": 4000.0,
            "rollover_enabled": True
        })
        self.assertEqual(res_add.status_code, 200)
        self.assertEqual(res_add.json()["monthly_limit"], 4000.0)

        # 3. Inline update via PATCH
        res_patch = self.client.patch("/api/budgets/gaming", headers=self.h1, json={
            "monthly_limit": 5500.0
        })
        self.assertEqual(res_patch.status_code, 200)

        # Confirm updated in manager list
        res_list = self.client.get("/api/budgets", headers=self.h1).json()["budgets"]
        gaming_b = next((b for b in res_list if b["category"] == "gaming"), None)
        self.assertIsNotNone(gaming_b)
        self.assertEqual(gaming_b["monthly_limit"], 5500.0)
        self.assertTrue(gaming_b["has_budget"])

        # User 2 isolation: User 2 has no gaming budget set
        u2_list = self.client.get("/api/budgets", headers=self.h2).json()["budgets"]
        u2_gaming = next((b for b in u2_list if b["category"] == "gaming"), None)
        if u2_gaming:
            self.assertFalse(u2_gaming["has_budget"])

        # 4. Delete budget row
        res_del = self.client.delete("/api/budgets/gaming", headers=self.h1)
        self.assertEqual(res_del.status_code, 200)

        # Confirm deleted
        res_after = self.client.get("/api/budgets", headers=self.h1).json()["budgets"]
        after_gaming = next((b for b in res_after if b["category"] == "gaming"), None)
        self.assertTrue(after_gaming is None or not after_gaming["has_budget"])

    def test_03_udhar_manual_entry_and_management(self):
        # 1. Add Lent entry
        resp1 = self.client.post("/api/udhar", headers=self.h1, json={
            "person_name": "Rohan",
            "kind": "lent",
            "amount": 2000.0,
            "note": "Concert ticket",
            "due_date": "2026-10-15T00:00:00Z"
        })
        self.assertEqual(resp1.status_code, 200)
        entry1_id = resp1.json()["id"]

        summary1 = get_udhar_summary(self.u1["id"])
        rohan1 = next(p for p in summary1["persons"] if p["key"] == "rohan")
        self.assertEqual(rohan1["net"], 2000.0)

        # 2. Add Received Back entry (reduces net balance)
        resp2 = self.client.post("/api/udhar", headers=self.h1, json={
            "person_name": "Rohan",
            "kind": "received_back",
            "amount": 800.0,
            "note": "Cash repayment"
        })
        self.assertEqual(resp2.status_code, 200)
        entry2_id = resp2.json()["id"]

        summary2 = get_udhar_summary(self.u1["id"])
        rohan2 = next(p for p in summary2["persons"] if p["key"] == "rohan")
        self.assertEqual(rohan2["net"], 1200.0)

        # 3. Edit entry
        resp_edit = self.client.put(f"/api/udhar/{entry1_id}", headers=self.h1, json={
            "amount": 2500.0,
            "note": "Concert ticket VIP"
        })
        self.assertEqual(resp_edit.status_code, 200)
        self.assertEqual(resp_edit.json()["amount"], 2500.0)

        summary3 = get_udhar_summary(self.u1["id"])
        rohan3 = next(p for p in summary3["persons"] if p["key"] == "rohan")
        self.assertEqual(rohan3["net"], 1700.0)

        # 4. Resolve due date
        resp_res = self.client.post(f"/api/udhar/{entry1_id}/resolve", headers=self.h1)
        self.assertEqual(resp_res.status_code, 200)

        # 5. User 2 isolation: cannot modify User 1's udhar
        u2_del = self.client.delete(f"/api/udhar/{entry1_id}", headers=self.h2)
        self.assertEqual(u2_del.status_code, 404)

        # Clean up entries
        self.client.delete(f"/api/udhar/{entry1_id}", headers=self.h1)
        self.client.delete(f"/api/udhar/{entry2_id}", headers=self.h1)

    def test_04_savings_goals_crud_and_calculation(self):
        # 1. Add savings goal
        resp = self.client.post("/api/goals", headers=self.h1, json={
            "name": "Japan Trip",
            "target_amount": 120000.0,
            "target_date": "2027-10-01"
        })
        self.assertEqual(resp.status_code, 200)
        goal = resp.json()
        goal_id = goal["id"]
        self.assertEqual(goal["target_amount"], 120000.0)
        self.assertIsNotNone(goal["required_monthly"])

        # 2. Add contribution
        resp_contrib = self.client.post("/api/goals/contribute", headers=self.h1, json={
            "goal_id": goal_id,
            "amount": 24000.0
        })
        self.assertEqual(resp_contrib.status_code, 200)
        c_goal = resp_contrib.json()
        self.assertEqual(c_goal["saved_amount"], 24000.0)
        self.assertEqual(c_goal["remaining"], 96000.0)

        # 3. Edit goal
        resp_edit = self.client.put(f"/api/goals/{goal_id}", headers=self.h1, json={
            "name": "Japan & Korea Trip",
            "target_amount": 150000.0
        })
        self.assertEqual(resp_edit.status_code, 200)
        self.assertEqual(resp_edit.json()["name"], "Japan & Korea Trip")
        self.assertEqual(resp_edit.json()["target_amount"], 150000.0)

        # 4. User 2 isolation: cannot delete User 1's goal
        u2_del = self.client.delete(f"/api/goals/{goal_id}", headers=self.h2)
        self.assertEqual(u2_del.status_code, 404)

        # 5. Delete goal
        resp_del = self.client.delete(f"/api/goals/{goal_id}", headers=self.h1)
        self.assertEqual(resp_del.status_code, 200)

    def test_05_recurring_expenses_crud(self):
        # 1. Add recurring expense
        resp = self.client.post("/api/recurring", headers=self.h1, json={
            "name": "Gym Membership",
            "amount": 2500.0,
            "category": "Health",
            "frequency": "monthly",
            "start_date": "2026-10-05"
        })
        self.assertEqual(resp.status_code, 200)
        r_id = resp.json()["id"]

        # 2. Edit recurring expense
        resp_edit = self.client.put(f"/api/recurring/{r_id}", headers=self.h1, json={
            "amount": 3000.0,
            "name": "Gym Pro Membership"
        })
        self.assertEqual(resp_edit.status_code, 200)
        self.assertEqual(resp_edit.json()["amount"], 3000.0)
        self.assertEqual(resp_edit.json()["name"], "Gym Pro Membership")

        # 3. Toggle active
        resp_toggle = self.client.post(f"/api/recurring/{r_id}/toggle", headers=self.h1)
        self.assertEqual(resp_toggle.status_code, 200)
        self.assertFalse(resp_toggle.json()["active"])

        resp_toggle2 = self.client.post(f"/api/recurring/{r_id}/toggle", headers=self.h1)
        self.assertEqual(resp_toggle2.status_code, 200)
        self.assertTrue(resp_toggle2.json()["active"])

        # 4. User 2 isolation: cannot delete User 1's recurring
        u2_del = self.client.delete(f"/api/recurring/{r_id}", headers=self.h2)
        self.assertEqual(u2_del.status_code, 404)

        # 5. Delete recurring
        resp_del = self.client.delete(f"/api/recurring/{r_id}", headers=self.h1)
        self.assertEqual(resp_del.status_code, 200)

if __name__ == "__main__":
    unittest.main()
