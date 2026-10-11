"""
Automatic notification scheduler and trigger checks for SAARTH.
Uses APScheduler BackgroundScheduler with CronTrigger in UTC timezone.
Triggers:
1. Daily Morning Reminder (9:00 AM IST / 03:30 UTC)
2. Budget 80% & Exceeded Warning (on transaction)
3. Bill Due Tomorrow Reminder (8:00 AM IST / 02:30 UTC)
4. Goal Milestones (25%, 50%, 75%, 100%) (on contribution/update)
5. Large Expense Alert (on transaction)
"""
import json
import logging
from typing import Optional, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.db import get_db_cursor
from app.push import send_push_to_user, _safe_print

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=pytz.utc)


def log_notification(
    user_id: int,
    type: str,
    category: Optional[str] = None,
    reference_id: Optional[int] = None,
    metadata: Optional[dict] = None,
):
    """Log a notification to prevent spamming duplicate alerts."""
    try:
        with get_db_cursor() as cur:
            meta_json = json.dumps(metadata) if metadata is not None else None
            cur.execute(
                """
                INSERT INTO notification_log (user_id, type, category, reference_id, metadata)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, type, category, reference_id, meta_json),
            )
    except Exception as e:
        logger.error(f"[NOTIFICATION_LOG] Failed to log notification for user {user_id}: {e}")


def send_daily_morning_notifications():
    """Daily morning reminder with safe-to-spend today (9:00 AM IST = 3:30 AM UTC)."""
    _safe_print("🌅 Running daily morning notifications...")

    try:
        with get_db_cursor() as cur:
            # Get all users with push subscriptions
            cur.execute("""
                SELECT DISTINCT u.id, u.email, u.username,
                       s.safe_to_spend
                FROM users u
                JOIN push_subscriptions ps ON ps.user_id = u.id
                LEFT JOIN (
                    SELECT user_id, 
                           (monthly_income - total_budgeted) / 
                           NULLIF(days_in_month, 0) as safe_to_spend
                    FROM user_snapshots
                    WHERE date = CURRENT_DATE
                ) s ON s.user_id = u.id
                WHERE u.email_verified = true
                AND u.is_banned = false
            """)
            users = cur.fetchall()
    except Exception as e:
        logger.error(f"[MORNING_PUSH] Error fetching eligible users: {e}")
        return

    sent = 0
    for user in users:
        try:
            name = user.get("username") or "there"
            amount = user.get("safe_to_spend")

            # Fallback if user_snapshots row does not exist for today
            if amount is None:
                try:
                    from app.db import get_financial_snapshot
                    snap = get_financial_snapshot(user["id"])
                    if snap and snap.get("safe_to_spend_today") is not None:
                        amount = snap.get("safe_to_spend_today")
                except Exception:
                    pass

            if amount is not None and amount > 0:
                body = f"You can safely spend ₹{int(amount):,} today 💰"
            else:
                body = "Check your spending plan for today 📊"

            send_push_to_user(
                user_id=user["id"],
                title=f"Good morning, {name}! ☀️",
                body=body,
                url="/",
            )
            sent += 1
        except Exception as e:
            logger.error(f"[MORNING_PUSH] Error sending to user {user.get('id')}: {e}")

    _safe_print(f"✅ Morning notifications sent to {sent} users")


def check_budget_alerts(user_id: int, category: str, amount: float):
    """
    Called after EVERY transaction is added.
    Sends 80% warning or 100% exceeded alert at most once per month per category.
    """
    if not category:
        return

    try:
        with get_db_cursor() as cur:
            # Get budget limit and current month spent for this category
            cur.execute("""
                SELECT b.monthly_limit,
                       COALESCE(SUM(t.amount), 0) as spent
                FROM budgets b
                LEFT JOIN transactions t ON 
                    t.user_id = b.user_id AND
                    LOWER(t.category) = LOWER(b.category) AND
                    DATE_TRUNC('month', t.date) = DATE_TRUNC('month', CURRENT_DATE)
                WHERE b.user_id = %s AND LOWER(b.category) = LOWER(%s)
                GROUP BY b.monthly_limit
            """, (user_id, category.strip()))

            budget = cur.fetchone()
            if not budget:
                return

            limit = float(budget["monthly_limit"] or 0)
            spent = float(budget["spent"] or 0)
            percentage = (spent / limit * 100) if limit > 0 else 0
            remaining = limit - spent

            # 80% warning - send once per month
            if 80 <= percentage < 100:
                # Check if already notified this month
                cur.execute("""
                    SELECT id FROM notification_log
                    WHERE user_id = %s 
                    AND type = 'budget_80'
                    AND LOWER(category) = LOWER(%s)
                    AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
                """, (user_id, category.strip()))

                if not cur.fetchone():
                    send_push_to_user(
                        user_id=user_id,
                        title=f"⚠️ {category} budget at {int(percentage)}%",
                        body=f"Only ₹{int(remaining):,} left in {category} this month",
                        url="/budgets",
                    )
                    log_notification(user_id, "budget_80", category.strip())

            # Budget exceeded
            elif percentage >= 100:
                cur.execute("""
                    SELECT id FROM notification_log
                    WHERE user_id = %s 
                    AND type = 'budget_exceeded'
                    AND LOWER(category) = LOWER(%s)
                    AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
                """, (user_id, category.strip()))

                if not cur.fetchone():
                    send_push_to_user(
                        user_id=user_id,
                        title=f"🚨 {category} budget exceeded!",
                        body=f"You've spent ₹{int(spent):,} of your ₹{int(limit):,} budget",
                        url="/budgets",
                    )
                    log_notification(user_id, "budget_exceeded", category.strip())
    except Exception as e:
        logger.error(f"[BUDGET_ALERT] Error checking budget alerts for user {user_id}: {e}")


def send_bill_due_notifications():
    """Bill due check daily at 8:00 AM IST = 2:30 AM UTC."""
    _safe_print("📅 Checking bills due tomorrow...")

    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT DISTINCT b.id, b.user_id, b.name, b.amount, b.due_date,
                       u.username
                FROM bills b
                JOIN users u ON u.id = b.user_id
                JOIN push_subscriptions ps ON ps.user_id = b.user_id
                WHERE b.due_date = CURRENT_DATE + INTERVAL '1 day'
                AND b.is_paid = false
            """)
            bills = cur.fetchall()
    except Exception as e:
        logger.error(f"[BILL_ALERT] Error fetching bills due tomorrow: {e}")
        return

    for bill in bills:
        try:
            send_push_to_user(
                user_id=bill["user_id"],
                title=f"📅 {bill['name']} due tomorrow",
                body=f"₹{int(bill['amount']):,} payment due tomorrow. Don't forget!",
                url="/bills",
            )
        except Exception as e:
            logger.error(f"[BILL_ALERT] Failed to send bill reminder for bill {bill.get('id')}: {e}")

    _safe_print(f"✅ Bill reminders sent for {len(bills)} bills")


def check_goal_milestones(user_id: int, goal_id: int):
    """
    Called after EVERY goal contribution or goal update.
    Triggers milestones at 25%, 50%, 75%, 100%.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT name, target_amount, current_amount
                FROM goals
                WHERE id = %s AND user_id = %s
            """, (goal_id, user_id))

            goal = cur.fetchone()
            if not goal:
                return

            target = float(goal["target_amount"] or 0)
            current = float(goal["current_amount"] or 0)
            if target <= 0:
                return

            percentage = (current / target * 100)
            milestones = [25, 50, 75, 100]

            for milestone in milestones:
                if percentage >= milestone:
                    cur.execute("""
                        SELECT id FROM notification_log
                        WHERE user_id = %s
                        AND type = 'goal_milestone'
                        AND reference_id = %s
                        AND metadata->>'milestone' = %s
                    """, (user_id, goal_id, str(milestone)))

                    if not cur.fetchone():
                        emoji = "🎉" if milestone == 100 else "🎯"
                        msg = (
                            "Goal reached! Amazing work!"
                            if milestone == 100
                            else f"{milestone}% of the way there!"
                        )

                        send_push_to_user(
                            user_id=user_id,
                            title=f"{emoji} {goal['name']}",
                            body=f"₹{int(current):,} saved — {msg}",
                            url="/goals",
                        )
                        log_notification(
                            user_id=user_id,
                            type="goal_milestone",
                            reference_id=goal_id,
                            metadata={"milestone": milestone},
                        )
    except Exception as e:
        logger.error(f"[GOAL_MILESTONE] Error checking goal milestones for user {user_id}, goal {goal_id}: {e}")


def check_large_expense(
    user_id: int,
    amount: float,
    category: str,
    merchant: Optional[str] = None,
):
    """
    Called after adding a transaction.
    Alerts if single expense > 3x daily average OR if expense > ₹5,000.
    """
    try:
        with get_db_cursor() as cur:
            # Get user's average daily spend over last 30 days
            cur.execute("""
                SELECT AVG(daily_total) as avg_daily
                FROM (
                    SELECT DATE(date) as d, SUM(amount) as daily_total
                    FROM transactions
                    WHERE user_id = %s
                    AND date >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY DATE(date)
                ) daily
            """, (user_id,))

            result = cur.fetchone()
            avg = float(result["avg_daily"] or 0) if result and result["avg_daily"] is not None else 0

            # Alert if single expense > 3x daily average OR if expense > ₹5000
            if amount > max(avg * 3, 5000):
                name = merchant or category
                send_push_to_user(
                    user_id=user_id,
                    title="💸 Large expense recorded",
                    body=f"₹{int(amount):,} spent on {name}",
                    url="/transactions",
                )
    except Exception as e:
        logger.error(f"[LARGE_EXPENSE] Error checking large expense for user {user_id}: {e}")


def start_scheduler():
    """Initialize and start the background scheduler with configured cron jobs."""
    # Daily morning at 9:00 AM IST = 3:30 AM UTC
    scheduler.add_job(
        send_daily_morning_notifications,
        CronTrigger(hour=3, minute=30, timezone="UTC"),
        id="daily_morning",
        replace_existing=True,
    )

    # Bill due check daily at 8:00 AM IST = 2:30 AM UTC
    scheduler.add_job(
        send_bill_due_notifications,
        CronTrigger(hour=2, minute=30, timezone="UTC"),
        id="bill_due_check",
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()
        _safe_print("✅ Scheduler started")


def stop_scheduler():
    """Safely stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        _safe_print("⏹️ Scheduler stopped")
