"""
Unit and integration tests for SAARTH automatic push notifications and APScheduler:
1. APScheduler job registration (daily morning & bill due checks)
2. Notification 1: Daily Morning Reminder
3. Notification 2: Budget 80% Warning & Exceeded
4. Notification 3: Bill Due Tomorrow
5. Notification 4: Goal Milestones (25%, 50%, 75%, 100%)
6. Notification 5: Large Expense Alert
7. Helper: send_push_to_user and expired subscription handling
8. Endpoint integration: /api/transactions and /api/goals/contribute
"""
import json
import secrets
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import (
    get_db_cursor,
    create_user,
    set_budget,
    set_savings_goal,
    save_push_subscription,
    get_user_push_subscriptions,
)
from app.auth import create_access_token
from app.scheduler import (
    scheduler,
    start_scheduler,
    stop_scheduler,
    log_notification,
    send_daily_morning_notifications,
    check_budget_alerts,
    send_bill_due_notifications,
    check_goal_milestones,
    check_large_expense,
)
from app.push import send_push_to_user


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture
def test_user():
    """Create or ensure a test user with verified email and push subscription."""
    unique_email = f"notif_test_{secrets.token_hex(6)}@example.com"
    user = create_user(unique_email, "hashed_pw")

    # Mark user email verified and not banned
    with get_db_cursor() as cur:
        cur.execute(
            """
            UPDATE users 
            SET email_verified = true, is_banned = false, username = 'TestUser' 
            WHERE id = %s
            """,
            (user["id"],),
        )

    # Add a mock push subscription
    fake_endpoint = f"https://push.example.com/sub/{secrets.token_hex(8)}"
    save_push_subscription(
        user_id=user["id"],
        endpoint=fake_endpoint,
        p256dh="mock_p256dh_key",
        auth="mock_auth_key",
    )
    user["endpoint"] = fake_endpoint
    return user


class TestSchedulerSetup:
    """Test APScheduler initialization and cron job definitions."""

    def test_scheduler_jobs_configured(self):
        start_scheduler()
        job_ids = [job.id for job in scheduler.get_jobs()]
        assert "daily_morning" in job_ids, "daily_morning job must be registered"
        assert "bill_due_check" in job_ids, "bill_due_check job must be registered"

        morning_job = scheduler.get_job("daily_morning")
        # Daily morning at 9:00 AM IST = 3:30 AM UTC
        assert str(morning_job.trigger.fields[5]) == "3", "Hour should be 3 UTC"
        assert str(morning_job.trigger.fields[6]) == "30", "Minute should be 30 UTC"

        bill_job = scheduler.get_job("bill_due_check")
        # Bill due check daily at 8:00 AM IST = 2:30 AM UTC
        assert str(bill_job.trigger.fields[5]) == "2", "Hour should be 2 UTC"
        assert str(bill_job.trigger.fields[6]) == "30", "Minute should be 30 UTC"

        stop_scheduler()


class TestPushHelpers:
    """Test send_push_to_user helper and 410 expired subscription pruning."""

    def test_send_push_to_user_delivers(self, test_user):
        with patch("app.push.send_web_push") as mock_web_push:
            mock_web_push.return_value = (True, 201, "")
            sent = send_push_to_user(
                user_id=test_user["id"],
                title="Hello Title",
                body="Hello Body",
                url="/test",
            )
            assert sent >= 1
            mock_web_push.assert_called()

    def test_send_push_prunes_expired_subscription(self, test_user):
        temp_endpoint = f"https://push.example.com/expired/{secrets.token_hex(6)}"
        save_push_subscription(
            user_id=test_user["id"],
            endpoint=temp_endpoint,
            p256dh="p256dh_val",
            auth="auth_val",
        )

        with patch("app.push.send_web_push") as mock_web_push:
            def fake_send(endpoint=None, **kwargs):
                if endpoint == temp_endpoint:
                    return False, 410, "Subscription expired"
                return True, 201, ""

            mock_web_push.side_effect = fake_send
            send_push_to_user(
                user_id=test_user["id"],
                title="Test Expired",
                body="Test Body",
            )

            subs = get_user_push_subscriptions(test_user["id"])
            endpoints = [s["endpoint"] for s in subs]
            assert temp_endpoint not in endpoints


class TestNotification1MorningReminder:
    """Test daily morning reminder push."""

    def test_send_daily_morning_notifications(self, test_user):
        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_snapshots (user_id, date, monthly_income, total_budgeted, days_in_month, safe_to_spend)
                VALUES (%s, CURRENT_DATE, 60000, 30000, 30, 1000)
                ON CONFLICT (user_id, date) DO UPDATE 
                SET safe_to_spend = 1000;
                """,
                (test_user["id"],),
            )

        with patch("app.scheduler.send_push_to_user") as mock_push:
            send_daily_morning_notifications()
            called_user_ids = [call.kwargs.get("user_id") for call in mock_push.call_args_list]
            assert test_user["id"] in called_user_ids

            user_call = [call for call in mock_push.call_args_list if call.kwargs.get("user_id") == test_user["id"]][0]
            assert "1,000" in user_call.kwargs.get("body")


class TestNotification2BudgetAlerts:
    """Test 80% warning and 100% exceeded notification."""

    def test_budget_80_percent_alert(self, test_user):
        category = f"food_{secrets.token_hex(4)}"
        set_budget(test_user["id"], category, 1000.0)

        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (user_id, amount, category, date)
                VALUES (%s, 850, %s, CURRENT_TIMESTAMP)
                """,
                (test_user["id"], category),
            )

        with patch("app.scheduler.send_push_to_user") as mock_push:
            check_budget_alerts(test_user["id"], category, 850.0)
            assert mock_push.called
            call_kwargs = mock_push.call_args.kwargs
            assert "85%" in call_kwargs["title"]
            assert "150" in call_kwargs["body"]

        # Deduplication
        with patch("app.scheduler.send_push_to_user") as mock_push:
            check_budget_alerts(test_user["id"], category, 850.0)
            mock_push.assert_not_called()

    def test_budget_exceeded_alert(self, test_user):
        category = f"shopping_{secrets.token_hex(4)}"
        set_budget(test_user["id"], category, 1000.0)

        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (user_id, amount, category, date)
                VALUES (%s, 1200, %s, CURRENT_TIMESTAMP)
                """,
                (test_user["id"], category),
            )

        with patch("app.scheduler.send_push_to_user") as mock_push:
            check_budget_alerts(test_user["id"], category, 1200.0)
            assert mock_push.called
            call_kwargs = mock_push.call_args.kwargs
            assert "exceeded" in call_kwargs["title"].lower()

        # Deduplication
        with patch("app.scheduler.send_push_to_user") as mock_push:
            check_budget_alerts(test_user["id"], category, 1200.0)
            mock_push.assert_not_called()


class TestNotification3BillDueTomorrow:
    """Test bill due check notification."""

    def test_send_bill_due_notifications(self, test_user):
        with get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO recurring_expenses (user_id, name, amount, category, frequency, next_due_date, active)
                VALUES (%s, 'Wifi Bill', 999, 'Utilities', 'monthly', CURRENT_DATE + INTERVAL '1 day', true)
                RETURNING id;
                """,
                (test_user["id"],),
            )
            bill_id = cur.fetchone()["id"]

        with patch("app.scheduler.send_push_to_user") as mock_push:
            send_bill_due_notifications()
            called_user_ids = [call.kwargs.get("user_id") for call in mock_push.call_args_list]
            assert test_user["id"] in called_user_ids
            matching_calls = [c for c in mock_push.call_args_list if c.kwargs.get("user_id") == test_user["id"]]
            assert any("Wifi Bill" in c.kwargs.get("title") for c in matching_calls)


class TestNotification4GoalMilestones:
    """Test goal milestone alerts (25, 50, 75, 100%)."""

    def test_goal_milestones(self, test_user):
        goal = set_savings_goal(
            user_id=test_user["id"],
            name="New Laptop",
            target_amount=10000.0,
        )
        goal_id = goal["id"]

        with get_db_cursor() as cur:
            cur.execute(
                "UPDATE savings_goals SET saved_amount = 5000 WHERE id = %s",
                (goal_id,),
            )

        with patch("app.scheduler.send_push_to_user") as mock_push:
            check_goal_milestones(test_user["id"], goal_id)
            assert mock_push.called
            assert mock_push.call_count >= 1
            titles = [c.kwargs.get("title") for c in mock_push.call_args_list]
            assert any("New Laptop" in t for t in titles)

        # Deduplication
        with patch("app.scheduler.send_push_to_user") as mock_push:
            check_goal_milestones(test_user["id"], goal_id)
            mock_push.assert_not_called()


class TestNotification5LargeExpense:
    """Test large expense notification (> 3x avg or > 5000)."""

    def test_large_expense_alert(self, test_user):
        with patch("app.scheduler.send_push_to_user") as mock_push:
            check_large_expense(test_user["id"], 6500.0, "Electronics", merchant="Apple Store")
            assert mock_push.called
            call_kwargs = mock_push.call_args.kwargs
            assert "Large expense recorded" in call_kwargs["title"]
            assert "6,500" in call_kwargs["body"]
            assert "Apple Store" in call_kwargs["body"]


class TestAPIEndpointsTriggerNotifications:
    """Test endpoints wire triggers correctly."""

    def test_transaction_api_triggers_alerts(self, client, test_user):
        token = create_access_token(test_user["id"], test_user["email"])
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.main.check_budget_alerts") as mock_budget_check, \
             patch("app.main.check_large_expense") as mock_large_check:
            res = client.post(
                "/api/transactions",
                headers=headers,
                json={
                    "amount": 7500.0,
                    "category": "Travel",
                    "note": "Flight ticket",
                    "merchant": "IndiGo",
                },
            )
            assert res.status_code == 200
            mock_budget_check.assert_called_once_with(test_user["id"], "travel", 7500.0)
            mock_large_check.assert_called_once_with(test_user["id"], 7500.0, "travel", "IndiGo")

    def test_goal_contribute_api_triggers_milestone(self, client, test_user):
        token = create_access_token(test_user["id"], test_user["email"])
        headers = {"Authorization": f"Bearer {token}"}

        goal = set_savings_goal(
            user_id=test_user["id"],
            name="Emergency Fund",
            target_amount=20000.0,
        )

        with patch("app.main.check_goal_milestones") as mock_milestone:
            res = client.post(
                "/api/goals/contribute",
                headers=headers,
                json={
                    "goal_id": goal["id"],
                    "amount": 5000.0,
                },
            )
            assert res.status_code == 200
            mock_milestone.assert_called_once_with(test_user["id"], goal["id"])
