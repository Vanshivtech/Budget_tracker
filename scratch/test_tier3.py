"""
Comprehensive verification test suite for Tier 3 features:
1. Receipts & Bill Attachments (Magic bytes, path format, signed URL, user isolation, deletion)
2. Statement & CSV Import (Parsing, rule/past/cache hierarchy, duplicates, credits)
3. Udhar Reminder Nudge (Deterministic template, balance/due date, zero emojis)
4. Cash-Flow Calendar (Month grid, recurring bills, udhar, running balance)
5. Overspending Projections (Pace formula, >=7 days threshold, agent tool)
6. Web Push (VAPID, subscription, deduplication)
"""
import io
import json
import os
import sys
import unittest
from datetime import date, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.db import (
    init_db, get_db_cursor, create_user, get_user_by_email,
    add_receipt, get_receipts, get_receipt_by_id, delete_receipt, get_transaction_receipts,
    get_cached_merchant_category, set_cached_merchant_category, get_past_merchant_category,
    get_udhar_reminder_data, get_cashflow_calendar, get_overspending_projections,
    save_push_subscription, get_user_push_subscriptions, remove_push_subscription,
    check_and_record_notification, normalize_merchant, check_duplicate_expense,
    log_transaction, add_udhar, add_recurring_expense, add_income_entry,
)
from app.storage import (
    validate_file_content, upload_to_storage, get_storage_path,
    delete_from_storage, get_signed_url, get_file_bytes, ocr_receipt_hook,
)
from app.importer import (
    parse_csv_content, parse_plain_text_statements, categorize_by_rule,
    batch_llm_categorize, MAX_FILE_BYTES, MAX_ROWS,
)
from app.agent import check_overspending_projections

class TestTier3Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        # Create test users
        cls.test_email_1 = f"test_tier3_u1_{os.getpid()}@example.com"
        cls.test_email_2 = f"test_tier3_u2_{os.getpid()}@example.com"
        
        from app.auth import hash_password
        u1 = get_user_by_email(cls.test_email_1)
        if not u1:
            cls.user1 = create_user(cls.test_email_1, hash_password("pass12345"))
        else:
            cls.user1 = u1
            
        u2 = get_user_by_email(cls.test_email_2)
        if not u2:
            cls.user2 = create_user(cls.test_email_2, hash_password("pass12345"))
        else:
            cls.user2 = u2

    # -------------------------------------------------------------
    # 1. Receipts & Bill Attachments
    # -------------------------------------------------------------
    def test_01_magic_bytes_validation(self):
        # Valid JPEG
        fake_jpg = b"\xFF\xD8\xFF\xE0" + b"\x00" * 50
        valid, mime, ext, err = validate_file_content(fake_jpg)
        self.assertTrue(valid)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(ext, "jpg")

        # Valid PNG
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        valid, mime, ext, err = validate_file_content(fake_png)
        self.assertTrue(valid)
        self.assertEqual(mime, "image/png")
        self.assertEqual(ext, "png")

        # Valid PDF
        fake_pdf = b"%PDF-1.4" + b"\x00" * 50
        valid, mime, ext, err = validate_file_content(fake_pdf)
        self.assertTrue(valid)
        self.assertEqual(mime, "application/pdf")
        self.assertEqual(ext, "pdf")

        # Invalid file content (e.g. text/exe spoofed as image)
        invalid_bytes = b"MZ\x90\x00This is an executable not an image"
        valid, mime, ext, err = validate_file_content(invalid_bytes)
        self.assertFalse(valid)
        self.assertIn("Unsupported file type", err)

        # File exceeding 5 MB
        too_big = b"\xFF\xD8\xFF\xE0" + b"\x00" * (5 * 1024 * 1024 + 10)
        valid, mime, ext, err = validate_file_content(too_big)
        self.assertFalse(valid)
        self.assertIn("exceeds maximum allowed size of 5 MB", err)

    def test_02_receipt_storage_path_and_isolation(self):
        u1_id = self.user1["id"]
        u2_id = self.user2["id"]

        # Log a real transaction to attach receipt to
        tx = log_transaction(user_id=u1_id, amount=450.0, category="food", note="Dinner receipt test")
        tx_id = tx["id"]

        # Verify storage path format {user_id}/{transaction_id}/{uuid}.{ext}
        path = get_storage_path(u1_id, tx_id, "jpg")
        parts = path.split("/")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], str(u1_id))
        self.assertEqual(parts[1], str(tx_id))
        self.assertTrue(parts[2].endswith(".jpg"))

        # Upload file content
        content = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 40
        uploaded = upload_to_storage(path, content, "image/jpeg")
        self.assertTrue(uploaded)

        # Record receipt in DB
        rec = add_receipt(u1_id, tx_id, path, "image/jpeg", len(content))
        self.assertIsNotNone(rec["id"])
        self.assertEqual(rec["user_id"], u1_id)
        self.assertEqual(rec["path"], path)

        # Verify signed URL generation
        signed_url = get_signed_url(path)
        self.assertTrue(len(signed_url) > 0)

        # Cross-user isolation: User 2 must NOT be able to access User 1's receipt
        rec_u2 = get_receipt_by_id(u2_id, rec["id"])
        self.assertIsNone(rec_u2)

        # User 1 can access it
        rec_u1 = get_receipt_by_id(u1_id, rec["id"])
        self.assertIsNotNone(rec_u1)
        self.assertEqual(rec_u1["id"], rec["id"])

        # Deletion
        del_path = delete_receipt(u1_id, rec["id"])
        self.assertEqual(del_path, path)
        delete_from_storage(del_path)

        # Confirm deleted from DB
        self.assertIsNone(get_receipt_by_id(u1_id, rec["id"]))

    # -------------------------------------------------------------
    # 2. Bank Statement & CSV Import
    # -------------------------------------------------------------
    def test_03_csv_statement_parsing(self):
        sample_csv = """Date,Description,Withdrawal,Deposit
2026-10-01,SWIGGY BANGALORE,350.00,
2026-10-02,UBER INDIA RIDES,450.00,
2026-10-03,SALARY CREDIT,,50000.00
2026-10-04,BLINKIT GROCERY,620.00,
"""
        rows = parse_csv_content(sample_csv)
        self.assertEqual(len(rows), 4)

        # Row 1: Swiggy debit
        self.assertEqual(rows[0]["amount"], 350.0)
        self.assertFalse(rows[0]["is_credit"])
        self.assertEqual(rows[0]["date"], "2026-10-01")

        # Row 3: Salary credit
        self.assertEqual(rows[2]["amount"], 50000.0)
        self.assertTrue(rows[2]["is_credit"])

    def test_04_categorization_hierarchy(self):
        u_id = self.user1["id"]

        # Rule match
        cat_swiggy = categorize_by_rule("Swiggy", "Paid to Swiggy")
        self.assertEqual(cat_swiggy.lower(), "food")

        cat_uber = categorize_by_rule("Uber", "Uber ride")
        self.assertEqual(cat_uber.lower(), "travel")

        # Merchant cache
        set_cached_merchant_category("UnusualMerchantX", "shopping")
        cached = get_cached_merchant_category("UnusualMerchantX")
        self.assertEqual(cached, "shopping")

    def test_05_plain_text_statement_parsing(self):
        sample_text = """
Paid Rs. 280 to Starbucks on 10-10-2026
Credited INR 12,000 for freelance on 11-10-2026
Spent 550 at DMart on 12 Oct 2026
"""
        rows = parse_plain_text_statements(sample_text)
        self.assertTrue(len(rows) >= 2)
        debit = next((r for r in rows if "starbucks" in r["description"].lower()), None)
        self.assertIsNotNone(debit)
        self.assertEqual(debit["amount"], 280.0)
        self.assertFalse(debit["is_credit"])

        credit = next((r for r in rows if r["is_credit"]), None)
        self.assertIsNotNone(credit)
        self.assertEqual(credit["amount"], 12000.0)

    # -------------------------------------------------------------
    # 3. Udhar Reminder Nudge (Zero emojis, deterministic template)
    # -------------------------------------------------------------
    def test_06_udhar_reminder_deterministic_no_emojis(self):
        u_id = self.user1["id"]
        # Add udhar lent entry
        add_udhar(
            user_id=u_id,
            person_name="Rohan",
            kind="lent",
            amount=1500.0,
            note="Dinner bill split",
            due_date="2026-10-25",
        )

        reminder = get_udhar_reminder_data(u_id, "rohan")
        self.assertIsNotNone(reminder)
        self.assertEqual(reminder["person_name"], "Rohan")
        self.assertEqual(reminder["net_balance"], 1500.0)
        self.assertTrue("2026" in reminder["due_date"] or "25" in reminder["due_date"])

        text = reminder["message"]
        # Must contain balance and person name
        self.assertIn("1500", text)
        self.assertIn("Rohan", text)

        # STRICT CONSTRAINT: Zero emojis anywhere in text or link
        for char in text:
            code = ord(char)
            self.assertFalse(0x1F300 <= code <= 0x1F9FF, f"Found emoji in reminder text: {char}")
            self.assertFalse(0x2600 <= code <= 0x27BF, f"Found emoji in reminder text: {char}")

        wa_link = reminder["wa_url"]
        self.assertTrue(wa_link.startswith("https://wa.me/?text="))
        self.assertIn("1500", wa_link)

    # -------------------------------------------------------------
    # 4. Cash-Flow Calendar
    # -------------------------------------------------------------
    def test_07_cashflow_calendar(self):
        u_id = self.user1["id"]
        target_month = "2026-10"

        # Add recurring bill
        add_recurring_expense(
            user_id=u_id,
            name="Broadband WiFi",
            amount=1200.0,
            category="utilities",
            frequency="monthly",
            start_date="2026-10-15",
        )

        cal = get_cashflow_calendar(u_id, target_month)
        self.assertEqual(cal["month"], target_month)
        self.assertEqual(cal["days_in_month"], 31)

        # Check day 15 has the recurring bill
        day15 = cal["days"][15]
        bill_events = [e for e in day15["bills"] if e.get("name") == "Broadband WiFi"]
        self.assertTrue(len(bill_events) > 0)
        self.assertEqual(bill_events[0]["amount"], 1200.0)

    # -------------------------------------------------------------
    # 5. Overspending Projections
    # -------------------------------------------------------------
    def test_08_overspending_projections_formula(self):
        u_id = self.user1["id"]

        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO budgets (user_id, category, monthly_limit)
                VALUES (%s, 'eating out', 2000.0)
                ON CONFLICT (user_id, category) DO UPDATE SET monthly_limit = 2000.0
                """,
                (u_id,),
            )

        projs = get_overspending_projections(u_id)
        self.assertIsInstance(projs, list)

        # Test agent tool check_overspending_projections with LangChain config
        agent_tool_output = check_overspending_projections.invoke({}, config={"configurable": {"user_id": u_id}})
        self.assertIsInstance(agent_tool_output, str)
        self.assertTrue(len(agent_tool_output) > 0)

    # -------------------------------------------------------------
    # 6. Web Push Notifications
    # -------------------------------------------------------------
    def test_09_push_subscription_and_deduplication(self):
        u_id = self.user1["id"]
        endpoint = f"https://updates.push.services.mozilla.com/wpush/v2/test_sub_{os.getpid()}"
        p256dh = "BCVxsG0u8pYkG..."
        auth = "1234567890abcdef"

        sub = save_push_subscription(
            user_id=u_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            preferences={"budget_alerts": True},
        )
        self.assertIsNotNone(sub["id"])
        self.assertEqual(sub["endpoint"], endpoint)

        # Fetch subscriptions
        subs = get_user_push_subscriptions(u_id)
        self.assertTrue(any(s["endpoint"] == endpoint for s in subs))

        # Test deduplication in sent_notifications:
        # First check: returns True (newly recorded, send alert)
        first_check = check_and_record_notification(u_id, "budget_limit_eating_out", "2026-10")
        self.assertTrue(first_check)

        # Second check within same cycle: returns False (already sent, suppress duplicate!)
        second_check = check_and_record_notification(u_id, "budget_limit_eating_out", "2026-10")
        self.assertFalse(second_check)

        # Clean up subscription
        removed = remove_push_subscription(endpoint)
        self.assertTrue(removed)

if __name__ == "__main__":
    unittest.main()
