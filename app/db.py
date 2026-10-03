"""
Database storage layer powered by Supabase Postgres.

Tables:
    users           — id (SERIAL PK), email (unique), password_hash, created_at
    transactions    — id (SERIAL PK), user_id (FK), date, amount, category, note, raw_message
    budgets         — user_id (FK), category, monthly_limit (PK: user_id, category)
    udhar_entries   — id (SERIAL PK), user_id (FK), person_name, person_key, kind,
                      amount, note, entry_date, due_date, created_at
    chat_messages   — id (SERIAL PK), user_id (FK), role, content, created_at
    income_entries  — id (SERIAL PK), user_id (FK), amount, source, date, created_at
    savings_goals   — id (SERIAL PK), user_id (FK), name, target_amount, saved_amount,
                      target_date, created_at
    user_profile    — user_id (PK/FK), current_savings, risk_comfort, updated_at

All queries are strictly scoped by user_id. Connection pooling via psycopg2.
"""
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
import calendar
import io
import time
from contextlib import contextmanager

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor, execute_values

from app.config import settings

_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    """Initialize or return the threaded connection pool for Postgres."""
    global _pool
    if _pool is None:
        if not settings.DATABASE_URL:
            raise RuntimeError(
                "[DATABASE ERROR] DATABASE_URL is not configured. "
                "Please set your Supabase Postgres connection string in .env."
            )
        # minconn=1, maxconn=10 is optimal for Supabase pooler connection limits
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=settings.DATABASE_URL,
        )
    return _pool


@contextmanager
def get_db_cursor():
    """Context manager for acquiring a connection & cursor from the pool."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def init_db() -> None:
    """Create tables and indexes if they don't already exist in Supabase Postgres."""
    with get_db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                email         VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                date        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                amount      NUMERIC(12, 2) NOT NULL,
                category    VARCHAR(100) NOT NULL,
                note        TEXT DEFAULT '',
                raw_message TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS budgets (
                user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category      VARCHAR(100) NOT NULL,
                monthly_limit NUMERIC(12, 2) NOT NULL,
                PRIMARY KEY (user_id, category)
            );

            CREATE TABLE IF NOT EXISTS udhar_entries (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                person_name VARCHAR(255) NOT NULL,
                person_key  VARCHAR(255) NOT NULL,
                kind        VARCHAR(10) NOT NULL CHECK (kind IN ('lent', 'borrowed')),
                amount      NUMERIC(12, 2) NOT NULL,
                note        TEXT DEFAULT '',
                entry_date  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                due_date    TIMESTAMPTZ,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role       VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
                content    TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date DESC);
            CREATE INDEX IF NOT EXISTS idx_budgets_user ON budgets(user_id);
            CREATE INDEX IF NOT EXISTS idx_udhar_user ON udhar_entries(user_id, entry_date DESC);
            CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS income_entries (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                amount     NUMERIC(12, 2) NOT NULL,
                source     VARCHAR(255) NOT NULL DEFAULT 'salary',
                date       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS savings_goals (
                id            SERIAL PRIMARY KEY,
                user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name          VARCHAR(255) NOT NULL,
                target_amount NUMERIC(12, 2) NOT NULL,
                saved_amount  NUMERIC(12, 2) NOT NULL DEFAULT 0,
                target_date   DATE,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS user_profile (
                user_id          INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                current_savings  NUMERIC(14, 2),
                risk_comfort     VARCHAR(10) CHECK (risk_comfort IN ('low', 'medium', 'high')),
                updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_income_user_date ON income_entries(user_id, date DESC);
            CREATE INDEX IF NOT EXISTS idx_goals_user ON savings_goals(user_id);

            -- Tier 1 Features: Recurring expenses, budget rollover, and split udhar
            CREATE TABLE IF NOT EXISTS recurring_expenses (
                id                 SERIAL PRIMARY KEY,
                user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name               VARCHAR(255) NOT NULL,
                amount             NUMERIC(12, 2) NOT NULL,
                category           VARCHAR(100) NOT NULL,
                frequency          VARCHAR(20) NOT NULL CHECK (frequency IN ('monthly', 'weekly', 'yearly')),
                next_due_date      DATE NOT NULL,
                active             BOOLEAN NOT NULL DEFAULT TRUE,
                last_reminded_date DATE,
                created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_recurring_user_due ON recurring_expenses(user_id, active, next_due_date);

            ALTER TABLE budgets ADD COLUMN IF NOT EXISTS rollover_enabled BOOLEAN NOT NULL DEFAULT FALSE;

            CREATE TABLE IF NOT EXISTS budget_rollovers (
                id             SERIAL PRIMARY KEY,
                user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category       VARCHAR(100) NOT NULL,
                month          VARCHAR(7) NOT NULL,
                carried_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_user_category_month UNIQUE (user_id, category, month)
            );
            CREATE INDEX IF NOT EXISTS idx_budget_rollovers_user_month ON budget_rollovers(user_id, month);

            ALTER TABLE udhar_entries ADD COLUMN IF NOT EXISTS is_split BOOLEAN NOT NULL DEFAULT FALSE;
            ALTER TABLE udhar_entries ADD COLUMN IF NOT EXISTS transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL;

            -- Tier 2: Username, avatar, merchant, categories, tags, undo
            ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(50);
            ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_id INTEGER NOT NULL DEFAULT 1;

            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant VARCHAR(255);

            CREATE TABLE IF NOT EXISTS user_categories (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name       VARCHAR(100) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_user_categories_unique
                ON user_categories(user_id, LOWER(name));

            CREATE TABLE IF NOT EXISTS transaction_tags (
                id             SERIAL PRIMARY KEY,
                transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
                user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                tag            VARCHAR(100) NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_tags_unique
                ON transaction_tags(transaction_id, LOWER(tag));
            CREATE INDEX IF NOT EXISTS idx_tx_tags_user ON transaction_tags(user_id, tag);

            CREATE TABLE IF NOT EXISTS merchant_aliases (
                id              SERIAL PRIMARY KEY,
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                raw_input       VARCHAR(500) NOT NULL,
                normalized_name VARCHAR(255) NOT NULL,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_merchant_alias_unique
                ON merchant_aliases(user_id, LOWER(raw_input));

            CREATE TABLE IF NOT EXISTS undo_log (
                id             SERIAL PRIMARY KEY,
                user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                action_type    VARCHAR(20) NOT NULL,
                entity_type    VARCHAR(50) NOT NULL,
                entity_id      INTEGER,
                previous_state JSONB,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_undo_user ON undo_log(user_id, created_at DESC);

            -- Tier 3: Receipts, Merchant Category Cache, Web Push Subscriptions, Notification Logs
            CREATE TABLE IF NOT EXISTS receipts (
                id             SERIAL PRIMARY KEY,
                user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                transaction_id INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
                path           VARCHAR(500) NOT NULL,
                mime           VARCHAR(50) NOT NULL,
                size           INTEGER NOT NULL,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_receipts_user ON receipts(user_id);
            CREATE INDEX IF NOT EXISTS idx_receipts_tx ON receipts(transaction_id);

            CREATE TABLE IF NOT EXISTS merchant_category_cache (
                normalized_merchant VARCHAR(255) PRIMARY KEY,
                category            VARCHAR(100) NOT NULL,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                endpoint    TEXT NOT NULL UNIQUE,
                p256dh      TEXT NOT NULL,
                auth        TEXT NOT NULL,
                preferences JSONB NOT NULL DEFAULT '{"budget_alerts": true, "bill_reminders": true, "weekly_recap": true}',
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_push_sub_user ON push_subscriptions(user_id);

            CREATE TABLE IF NOT EXISTS sent_notifications (
                id                SERIAL PRIMARY KEY,
                user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                notification_type VARCHAR(100) NOT NULL,
                cycle             VARCHAR(50) NOT NULL,
                sent_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_sent_notification UNIQUE (user_id, notification_type, cycle)
            );
            CREATE INDEX IF NOT EXISTS idx_sent_notif_user ON sent_notifications(user_id, cycle);

            -- Admin & Account Management
            ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS force_password_reset BOOLEAN NOT NULL DEFAULT FALSE;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;

            CREATE TABLE IF NOT EXISTS errors (
                id         SERIAL PRIMARY KEY,
                route      VARCHAR(500) NOT NULL,
                message    TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_errors_created ON errors(created_at DESC);

            CREATE TABLE IF NOT EXISTS app_settings (
                key        VARCHAR(100) PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            INSERT INTO app_settings (key, value)
            VALUES
                ('daily_message_cap', '100'),
                ('maintenance_mode', 'false'),
                ('push_notifications_enabled', 'true'),
                ('csv_import_enabled', 'true'),
                ('receipt_upload_enabled', 'true')
            ON CONFLICT (key) DO NOTHING;
        """)


# ---------- Users ----------

def create_user(email: str, password_hash: str) -> dict:
    """Create a new user record in Postgres."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id, email, created_at
            """,
            (email.lower().strip(), password_hash),
        )
        row = cur.fetchone()
        created_at_str = (
            row["created_at"].isoformat()
            if hasattr(row["created_at"], "isoformat")
            else str(row["created_at"])
        )
        return {
            "id": row["id"],
            "email": row["email"],
            "created_at": created_at_str,
        }


def get_user_by_email(email: str) -> dict | None:
    """Lookup a user by email address."""
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email.lower().strip(),))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    """Lookup a user by their primary key id."""
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


# ---------- Transactions ----------

def log_transaction(
    user_id: int,
    amount: float,
    category: str,
    note: str = "",
    raw_message: str = "",
    merchant: str | None = None,
    entry_date: str | None = None,
) -> dict:
    """Insert a new transaction scoped to user_id."""
    cat = category.lower().strip()
    with get_db_cursor() as cur:
        if entry_date:
            cur.execute(
                """
                INSERT INTO transactions (user_id, amount, category, note, raw_message, merchant, date)
                VALUES (%s, %s, %s, %s, %s, %s, %s::timestamptz)
                RETURNING id, user_id, date, amount, category, note, merchant
                """,
                (user_id, amount, cat, note.strip(), raw_message, merchant, entry_date),
            )
        else:
            cur.execute(
                """
                INSERT INTO transactions (user_id, amount, category, note, raw_message, merchant)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, user_id, date, amount, category, note, merchant
                """,
                (user_id, amount, cat, note.strip(), raw_message, merchant),
            )
        row = cur.fetchone()
        date_str = (
            row["date"].isoformat()
            if hasattr(row["date"], "isoformat")
            else str(row["date"])
        )
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "date": date_str,
            "amount": float(row["amount"]),
            "category": row["category"],
            "note": row["note"],
            "merchant": row.get("merchant"),
        }


def get_transactions(
    user_id: int,
    month: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return transactions for a specific user, optionally filtered by month."""
    query = "SELECT * FROM transactions WHERE user_id = %s"
    params: list = [user_id]

    if month:
        query += " AND TO_CHAR(date, 'YYYY-MM') = %s"
        params.append(month)

    query += " ORDER BY date DESC, id DESC"

    if limit:
        query += " LIMIT %s"
        params.append(limit)

    with get_db_cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if hasattr(d.get("date"), "isoformat"):
                d["date"] = d["date"].isoformat()
            if "amount" in d and d["amount"] is not None:
                d["amount"] = float(d["amount"])
            results.append(d)
        return results


def get_recent_expenses(user_id: int, limit: int = 10) -> list[dict]:
    """Get the user's most recent transactions."""
    return get_transactions(user_id=user_id, limit=limit)


def update_expense(
    user_id: int,
    transaction_id: int,
    amount: float | None = None,
    category: str | None = None,
    note: str | None = None,
    entry_date: str | None = None,
    merchant: str | None = None,
    tags: list[str] | None = None,
) -> dict | None:
    """Update specific fields of an existing transaction owned by user_id."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT * FROM transactions WHERE id = %s AND user_id = %s",
            (transaction_id, user_id),
        )
        existing = cur.fetchone()
        if not existing:
            return None

        new_amount = amount if amount is not None else float(existing["amount"])
        new_category = (
            category.lower().strip() if category is not None else existing["category"]
        )
        new_note = note.strip() if note is not None else existing["note"]
        new_date = entry_date if entry_date is not None else existing["date"]
        new_merchant = merchant.strip() if merchant is not None else existing.get("merchant")

        cur.execute(
            """
            UPDATE transactions
            SET amount = %s, category = %s, note = %s, date = %s::timestamptz, merchant = %s
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (new_amount, new_category, new_note, new_date, new_merchant, transaction_id, user_id),
        )
        updated = cur.fetchone()
        if not updated:
            return None

        if tags is not None:
            cur.execute("DELETE FROM transaction_tags WHERE transaction_id = %s", (transaction_id,))
            for t in tags:
                clean_tag = t.strip().lstrip("#").lower()
                if clean_tag:
                    cur.execute(
                        "INSERT INTO transaction_tags (transaction_id, user_id, tag) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (transaction_id, user_id, clean_tag),
                    )

        d = dict(updated)
        if hasattr(d.get("date"), "isoformat"):
            d["date"] = d["date"].isoformat()
        if "amount" in d and d["amount"] is not None:
            d["amount"] = float(d["amount"])
        cur.execute(
            "SELECT tag FROM transaction_tags WHERE user_id = %s AND transaction_id = %s ORDER BY tag",
            (user_id, transaction_id),
        )
        d["tags"] = [r["tag"] for r in cur.fetchall()]
        return d


def delete_expense(user_id: int, transaction_id: int) -> bool:
    """Delete a transaction owned by user_id and its attached receipt files. Returns True if deleted."""
    from app.storage import delete_from_storage
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT path FROM receipts WHERE transaction_id = %s AND user_id = %s",
            (transaction_id, user_id),
        )
        receipt_paths = [r["path"] for r in cur.fetchall()]
        cur.execute(
            "DELETE FROM transactions WHERE id = %s AND user_id = %s",
            (transaction_id, user_id),
        )
        deleted = cur.rowcount > 0

    if deleted and receipt_paths:
        for p in receipt_paths:
            try:
                delete_from_storage(p)
            except Exception:
                pass

    return deleted


def bulk_delete_expenses(user_id: int, transaction_ids: list[int]) -> int:
    """Bulk delete transactions owned by user_id and attached receipt files."""
    if not transaction_ids:
        return 0
    from app.storage import delete_from_storage
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT path FROM receipts WHERE user_id = %s AND transaction_id = ANY(%s)",
            (user_id, transaction_ids),
        )
        receipt_paths = [r["path"] for r in cur.fetchall()]
        cur.execute(
            "DELETE FROM transactions WHERE user_id = %s AND id = ANY(%s)",
            (user_id, transaction_ids),
        )
        deleted_count = cur.rowcount

    if deleted_count > 0 and receipt_paths:
        for p in receipt_paths:
            try:
                delete_from_storage(p)
            except Exception:
                pass

    return deleted_count


def spend_by_category(user_id: int, month: str) -> dict[str, float]:
    """Aggregate spending by category for a given month and user."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE user_id = %s AND TO_CHAR(date, 'YYYY-MM') = %s
            GROUP BY category
            """,
            (user_id, month),
        )
        rows = cur.fetchall()
        return {row["category"]: float(row["total"]) for row in rows}


def get_daily_spend(user_id: int, month: str) -> list[dict]:
    """Return daily spending totals for a given month."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT DATE(date AT TIME ZONE 'UTC') as day, SUM(amount) as total
            FROM transactions
            WHERE user_id = %s AND TO_CHAR(date, 'YYYY-MM') = %s
            GROUP BY day
            ORDER BY day ASC
            """,
            (user_id, month),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "day": r["day"].isoformat() if hasattr(r["day"], "isoformat") else str(r["day"]),
                "total": float(r["total"]),
            })
        return result


def get_monthly_totals(user_id: int, num_months: int = 6) -> list[dict]:
    """Return total spending per month for the last N months."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT TO_CHAR(date, 'YYYY-MM') as month, SUM(amount) as total
            FROM transactions
            WHERE user_id = %s
              AND date >= NOW() - INTERVAL '%s months'
            GROUP BY month
            ORDER BY month ASC
            """,
            (user_id, num_months),
        )
        rows = cur.fetchall()
        return [{"month": r["month"], "total": float(r["total"])} for r in rows]


# ---------- Budgets ----------

def get_budgets(user_id: int) -> dict[str, float]:
    """Fetch all budget limits configured for user_id."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT category, monthly_limit FROM budgets WHERE user_id = %s",
            (user_id,),
        )
        rows = cur.fetchall()
        return {row["category"]: float(row["monthly_limit"]) for row in rows}


def set_budget(user_id: int, category: str, monthly_limit: float, rollover_enabled: bool | None = None) -> None:
    """Upsert a budget row for user_id."""
    cat = category.lower().strip()
    with get_db_cursor() as cur:
        if rollover_enabled is not None:
            cur.execute(
                """
                INSERT INTO budgets (user_id, category, monthly_limit, rollover_enabled)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, category)
                DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit, rollover_enabled = EXCLUDED.rollover_enabled
                """,
                (user_id, cat, monthly_limit, rollover_enabled),
            )
        else:
            cur.execute(
                """
                INSERT INTO budgets (user_id, category, monthly_limit)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, category)
                DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit
                """,
                (user_id, cat, monthly_limit),
            )


def delete_budget(user_id: int, category: str) -> bool:
    """Delete a budget row entirely for user_id."""
    with get_db_cursor() as cur:
        cur.execute(
            "DELETE FROM budgets WHERE user_id = %s AND LOWER(category) = LOWER(%s)",
            (user_id, category.strip()),
        )
        return cur.rowcount > 0


def get_budgets_manager(user_id: int) -> list[dict]:
    """
    Table of all categories (preset + custom + any configured) with current monthly limit,
    this month's spend, and rollover status.
    """
    cur_m = current_month()
    spend_map = spend_by_category(user_id, cur_m)
    custom_cats = [c.lower() for c in get_user_categories(user_id)]

    with get_db_cursor() as cur:
        cur.execute(
            "SELECT category, monthly_limit, rollover_enabled FROM budgets WHERE user_id = %s",
            (user_id,),
        )
        budget_rows = {
            r["category"].lower(): {
                "limit": float(r["monthly_limit"]),
                "rollover": bool(r["rollover_enabled"]),
            }
            for r in cur.fetchall()
        }

    all_cat_names = set(c.lower() for c in SYSTEM_CATEGORIES)
    all_cat_names.update(custom_cats)
    all_cat_names.update(budget_rows.keys())

    result = []
    for cat in sorted(all_cat_names):
        b_info = budget_rows.get(cat, {"limit": 0.0, "rollover": False})
        has_budget = cat in budget_rows
        limit = b_info["limit"] if has_budget else 0.0
        spent = round(spend_map.get(cat, 0.0), 2)
        remaining = round(limit - spent, 2) if has_budget else None
        result.append({
            "category": cat,
            "monthly_limit": limit,
            "has_budget": has_budget,
            "current_spend": spent,
            "remaining": remaining,
            "rollover_enabled": b_info["rollover"],
            "is_custom": cat in custom_cats,
        })
    return result


def current_month() -> str:
    """Return current month in YYYY-MM format."""
    return date.today().strftime("%Y-%m")


def get_effective_budgets(user_id: int, month: str | None = None) -> dict[str, dict]:
    """
    Fetch all budgets for user_id with rollover logic applied.
    Returns:
        {
            "category": {
                "base_limit": float,
                "effective_budget": float,
                "rollover_enabled": bool,
                "carried_amount": float
            }
        }
    """
    target_month = month or current_month()
    try:
        y, m = map(int, target_month.split("-"))
        if m == 1:
            prev_month = f"{y - 1}-12"
        else:
            prev_month = f"{y}-{m - 1:02d}"
    except Exception:
        prev_month = None

    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT category, monthly_limit, rollover_enabled
            FROM budgets
            WHERE user_id = %s
            """,
            (user_id,),
        )
        budget_rows = cur.fetchall()

        if not budget_rows:
            return {}

        cur.execute(
            """
            SELECT category, carried_amount
            FROM budget_rollovers
            WHERE user_id = %s AND month = %s
            """,
            (user_id, target_month),
        )
        rollover_rows = cur.fetchall()
        existing_rollovers = {
            r["category"].lower().strip(): float(r["carried_amount"])
            for r in rollover_rows
        }

    prev_spend = spend_by_category(user_id, prev_month) if prev_month else {}

    results = {}
    to_record = []

    for r in budget_rows:
        cat = r["category"].lower().strip()
        base_limit = float(r["monthly_limit"])
        rollover_enabled = bool(r.get("rollover_enabled", False))

        carried = 0.0
        if rollover_enabled:
            if cat in existing_rollovers:
                carried = existing_rollovers[cat]
            elif prev_month:
                p_spent = prev_spend.get(cat, 0.0)
                unspent = max(0.0, base_limit - p_spent)
                carried = round(unspent, 2)
                to_record.append((user_id, cat, target_month, carried))

        effective = base_limit + carried
        results[cat] = {
            "base_limit": base_limit,
            "effective_budget": round(effective, 2),
            "rollover_enabled": rollover_enabled,
            "carried_amount": carried,
        }

    if to_record:
        with get_db_cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO budget_rollovers (user_id, category, month, carried_amount)
                VALUES %s
                ON CONFLICT (user_id, category, month)
                DO UPDATE SET carried_amount = EXCLUDED.carried_amount
                """,
                to_record,
            )

    return results


def set_category_rollover(user_id: int, category: str, enabled: bool) -> dict:
    """Enable or disable rollover for a category."""
    cat = category.strip().lower()
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO budgets (user_id, category, monthly_limit, rollover_enabled)
            VALUES (%s, %s, 0.0, %s)
            ON CONFLICT (user_id, category)
            DO UPDATE SET rollover_enabled = EXCLUDED.rollover_enabled
            RETURNING category, monthly_limit, rollover_enabled
            """,
            (user_id, cat, enabled),
        )
        row = cur.fetchone()
        if not row:
            return {}
        return {
            "category": row["category"],
            "monthly_limit": float(row["monthly_limit"]),
            "rollover_enabled": bool(row["rollover_enabled"]),
        }


def get_summary(user_id: int) -> dict:
    """
    Build the full summary payload for GET /api/summary.
    Returns categories sorted by spend, total spent/budget, and recent transactions.
    """
    month = current_month()
    spend = spend_by_category(user_id, month)
    effective_budgets = get_effective_budgets(user_id, month)
    recent = get_recent_expenses(user_id, limit=10)

    # Merge all categories from both spend and budgets
    all_categories = sorted(set(list(spend.keys()) + list(effective_budgets.keys())))

    categories = []
    total_spent = 0.0
    total_budget = 0.0

    for cat in all_categories:
        spent = spend.get(cat, 0.0)
        eff = effective_budgets.get(cat)
        limit = eff["effective_budget"] if eff else None
        base_limit = eff["base_limit"] if eff else None
        rollover_enabled = eff["rollover_enabled"] if eff else False
        carried = eff["carried_amount"] if eff else 0.0
        total_spent += spent

        entry = {
            "category": cat,
            "spent": round(spent, 2),
            "budget": round(limit, 2) if limit is not None else None,
            "base_budget": round(base_limit, 2) if base_limit is not None else None,
            "rollover_enabled": rollover_enabled,
            "carried_amount": round(carried, 2),
            "percentage": round((spent / limit) * 100, 1) if limit else None,
        }
        if limit is not None:
            total_budget += limit
        categories.append(entry)

    # Sort categories by spent descending (highest first)
    categories.sort(key=lambda x: x["spent"], reverse=True)

    return {
        "user_id": user_id,
        "month": month,
        "currency": settings.CURRENCY_SYMBOL,
        "categories": categories,
        "total_spent": round(total_spent, 2),
        "total_budget": round(total_budget, 2) if total_budget > 0 else None,
        "recent_transactions": recent,
    }


def get_dashboard(user_id: int) -> dict:
    """
    Build the full dashboard payload for GET /api/dashboard.
    Includes 6-month trends, daily spend for current month, category breakdown,
    budget vs actual, and udhar totals.
    """
    month = current_month()
    spend = spend_by_category(user_id, month)
    effective_budgets = get_effective_budgets(user_id, month)
    daily = get_daily_spend(user_id, month)
    monthly_trends = get_monthly_totals(user_id, num_months=6)
    udhar = get_udhar_summary(user_id)

    # Category breakdown with budget comparison
    all_categories = sorted(set(list(spend.keys()) + list(effective_budgets.keys())))
    categories = []
    total_spent = 0.0
    total_budget = 0.0

    for cat in all_categories:
        spent = spend.get(cat, 0.0)
        eff = effective_budgets.get(cat)
        limit = eff["effective_budget"] if eff else None
        base_limit = eff["base_limit"] if eff else None
        rollover_enabled = eff["rollover_enabled"] if eff else False
        carried = eff["carried_amount"] if eff else 0.0
        total_spent += spent

        entry = {
            "category": cat,
            "spent": round(spent, 2),
            "budget": round(limit, 2) if limit is not None else None,
            "base_budget": round(base_limit, 2) if base_limit is not None else None,
            "rollover_enabled": rollover_enabled,
            "carried_amount": round(carried, 2),
            "percentage": round((spent / limit) * 100, 1) if limit else None,
        }
        if limit is not None:
            total_budget += limit
        categories.append(entry)

    categories.sort(key=lambda x: x["spent"], reverse=True)

    return {
        "month": month,
        "total_spent": round(total_spent, 2),
        "total_budget": round(total_budget, 2) if total_budget > 0 else None,
        "categories": categories,
        "daily_spend": daily,
        "monthly_trends": monthly_trends,
        "udhar_net": udhar["net"],
        "udhar_lent": udhar["total_lent"],
        "udhar_borrowed": udhar["total_borrowed"],
    }


# ---------- Udhar (Lending/Borrowing) ----------

def add_udhar(
    user_id: int,
    person_name: str,
    kind: str,
    amount: float,
    note: str = "",
    due_date: str | None = None,
    is_split: bool = False,
    transaction_id: int | None = None,
    entry_date: str | None = None,
) -> dict:
    """Add a new udhar entry. Never counted in expenses."""
    person_key = person_name.strip().lower()
    norm_kind = kind.strip().lower()
    entry_note = note.strip()

    if norm_kind in ("received_back", "received back", "received"):
        db_kind = "borrowed"
        if not entry_note:
            entry_note = "Received back"
    elif norm_kind in ("paid_back", "paid back", "paid"):
        db_kind = "lent"
        if not entry_note:
            entry_note = "Paid back"
    else:
        db_kind = norm_kind

    due_dt = None
    if due_date:
        try:
            due_dt = datetime.fromisoformat(due_date)
        except ValueError:
            due_dt = None

    entry_dt = None
    if entry_date:
        try:
            entry_dt = datetime.fromisoformat(entry_date)
        except ValueError:
            entry_dt = None

    with get_db_cursor() as cur:
        if entry_dt:
            cur.execute(
                """
                INSERT INTO udhar_entries (user_id, person_name, person_key, kind, amount, note, due_date, is_split, transaction_id, entry_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, person_name, kind, amount, note, entry_date, due_date, is_split, transaction_id
                """,
                (user_id, person_name.strip(), person_key, db_kind, amount, entry_note, due_dt, is_split, transaction_id, entry_dt),
            )
        else:
            cur.execute(
                """
                INSERT INTO udhar_entries (user_id, person_name, person_key, kind, amount, note, due_date, is_split, transaction_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, person_name, kind, amount, note, entry_date, due_date, is_split, transaction_id
                """,
                (user_id, person_name.strip(), person_key, db_kind, amount, entry_note, due_dt, is_split, transaction_id),
            )
        row = cur.fetchone()
        d = dict(row)
        for f in ("entry_date", "due_date"):
            if d.get(f) and hasattr(d[f], "isoformat"):
                d[f] = d[f].isoformat()
        d["amount"] = float(d["amount"])
        d["is_split"] = bool(d.get("is_split", False))
        return d


def update_udhar_entry(
    user_id: int,
    entry_id: int,
    amount: float | None = None,
    note: str | None = None,
    entry_date: str | None = None,
    due_date: str | None = None,
) -> dict | None:
    """Update an existing udhar entry owned by user_id."""
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM udhar_entries WHERE id = %s AND user_id = %s", (entry_id, user_id))
        existing = cur.fetchone()
        if not existing:
            return None

        new_amount = amount if amount is not None else float(existing["amount"])
        new_note = note.strip() if note is not None else existing["note"]
        new_entry_date = entry_date if entry_date is not None else existing["entry_date"]

        if due_date == "":
            new_due_date = None
        elif due_date is not None:
            new_due_date = due_date
        else:
            new_due_date = existing["due_date"]

        cur.execute(
            """
            UPDATE udhar_entries
            SET amount = %s, note = %s, entry_date = %s::timestamptz, due_date = %s::timestamptz
            WHERE id = %s AND user_id = %s
            RETURNING id, person_name, person_key, kind, amount, note, entry_date, due_date, is_split, transaction_id
            """,
            (new_amount, new_note, new_entry_date, new_due_date, entry_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        for f in ("entry_date", "due_date"):
            if d.get(f) and hasattr(d[f], "isoformat"):
                d[f] = d[f].isoformat()
        d["amount"] = float(d["amount"])
        return d


def delete_udhar_entry(user_id: int, entry_id: int) -> bool:
    """Delete an udhar entry owned by user_id."""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM udhar_entries WHERE id = %s AND user_id = %s", (entry_id, user_id))
        return cur.rowcount > 0


def resolve_udhar_due_date(user_id: int, entry_id: int) -> bool:
    """Clear due_date on an udhar entry so overdue highlight is removed."""
    with get_db_cursor() as cur:
        cur.execute("UPDATE udhar_entries SET due_date = NULL WHERE id = %s AND user_id = %s", (entry_id, user_id))
        return cur.rowcount > 0


def record_udhar_repayment(
    user_id: int,
    person_name: str,
    amount: float,
    note: str = "",
) -> dict:
    """
    Record a repayment. Repayments are stored as opposite-kind entries.
    E.g., if you lent 500 and received 500 back, add a 'borrowed' entry for same person.
    The net balance automatically reflects correctly.
    """
    person_key = person_name.strip().lower()

    # Find the dominant direction (lent or borrowed) for this person to determine repayment kind
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT kind, SUM(amount) as total FROM udhar_entries
            WHERE user_id = %s AND person_key = %s
            GROUP BY kind
            """,
            (user_id, person_key),
        )
        rows = cur.fetchall()

    lent = sum(float(r["total"]) for r in rows if r["kind"] == "lent")
    borrowed = sum(float(r["total"]) for r in rows if r["kind"] == "borrowed")
    net = lent - borrowed

    # Repayment reverses net direction
    repayment_kind = "borrowed" if net > 0 else "lent"
    repayment_note = f"Repayment: {note}" if note else "Repayment"

    return add_udhar(
        user_id=user_id,
        person_name=person_name,
        kind=repayment_kind,
        amount=amount,
        note=repayment_note,
    )


def get_udhar_entries(user_id: int) -> list[dict]:
    """Get all udhar entries for a user."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, person_name, person_key, kind, amount, note, entry_date, due_date, is_split, transaction_id
            FROM udhar_entries
            WHERE user_id = %s
            ORDER BY entry_date DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for f in ("entry_date", "due_date"):
                if d.get(f) and hasattr(d[f], "isoformat"):
                    d[f] = d[f].isoformat()
            d["amount"] = float(d["amount"])
            d["is_split"] = bool(d.get("is_split", False))
            result.append(d)
        return result


def get_udhar_summary(user_id: int) -> dict:
    """
    Compute udhar balances per person and overall totals.
    net > 0 means overall the user is owed money; net < 0 means user owes money.
    NEVER included in expense or budget totals.
    """
    entries = get_udhar_entries(user_id)

    # Compute per-person balances
    persons: dict[str, dict] = {}
    for e in entries:
        key = e["person_key"]
        name = e["person_name"]
        if key not in persons:
            persons[key] = {"name": name, "lent": 0.0, "borrowed": 0.0, "history": []}
        if e["kind"] == "lent":
            persons[key]["lent"] += e["amount"]
        else:
            persons[key]["borrowed"] += e["amount"]
        persons[key]["history"].append(e)

    person_list = []
    total_lent = 0.0
    total_borrowed = 0.0

    for key, p in persons.items():
        net = p["lent"] - p["borrowed"]
        total_lent += p["lent"]
        total_borrowed += p["borrowed"]
        person_list.append({
            "name": p["name"],
            "key": key,
            "lent": round(p["lent"], 2),
            "borrowed": round(p["borrowed"], 2),
            "net": round(net, 2),
            "history": p["history"],
        })

    # Sort: largest abs balance first
    person_list.sort(key=lambda x: abs(x["net"]), reverse=True)

    return {
        "persons": person_list,
        "total_lent": round(total_lent, 2),
        "total_borrowed": round(total_borrowed, 2),
        "net": round(total_lent - total_borrowed, 2),
    }


# ---------- Chat Messages ----------

def save_chat_message(user_id: int, role: str, content: str) -> None:
    """Persist a chat message for a user."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_messages (user_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (user_id, role, content),
        )


def get_chat_history(user_id: int, limit: int = 50) -> list[dict]:
    """Retrieve the last N chat messages for a user, oldest first."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT role, content, created_at
            FROM (
                SELECT role, content, created_at
                FROM chat_messages
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            ) sub
            ORDER BY created_at ASC
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            result.append(d)
        return result


# ---------- Income ----------

def add_income_entry(
    user_id: int,
    amount: float,
    source: str = "salary",
    entry_date: str | None = None,
) -> dict:
    """Insert an income entry for a user."""
    date_val = None
    if entry_date:
        try:
            date_val = datetime.fromisoformat(entry_date)
        except ValueError:
            date_val = None

    with get_db_cursor() as cur:
        if date_val:
            cur.execute(
                """
                INSERT INTO income_entries (user_id, amount, source, date)
                VALUES (%s, %s, %s, %s)
                RETURNING id, amount, source, date
                """,
                (user_id, amount, source.strip(), date_val),
            )
        else:
            cur.execute(
                """
                INSERT INTO income_entries (user_id, amount, source)
                VALUES (%s, %s, %s)
                RETURNING id, amount, source, date
                """,
                (user_id, amount, source.strip()),
            )
        row = cur.fetchone()
        d = dict(row)
        d["amount"] = float(d["amount"])
        if hasattr(d.get("date"), "isoformat"):
            d["date"] = d["date"].isoformat()
        return d


def get_income_entries(user_id: int, month: str | None = None) -> list[dict]:
    """Return income entries for a user, optionally filtered by month."""
    query = "SELECT id, amount, source, date FROM income_entries WHERE user_id = %s"
    params: list = [user_id]
    if month:
        query += " AND TO_CHAR(date, 'YYYY-MM') = %s"
        params.append(month)
    query += " ORDER BY date DESC"

    with get_db_cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["amount"] = float(d["amount"])
            if hasattr(d.get("date"), "isoformat"):
                d["date"] = d["date"].isoformat()
            result.append(d)
        return result


def get_income_summary(user_id: int, month: str) -> dict:
    """Aggregate income by source for a given month."""
    entries = get_income_entries(user_id, month)
    total = sum(e["amount"] for e in entries)
    by_source: dict[str, float] = {}
    for e in entries:
        by_source[e["source"]] = by_source.get(e["source"], 0.0) + e["amount"]
    return {
        "month": month,
        "total": round(total, 2),
        "by_source": {k: round(v, 2) for k, v in by_source.items()},
        "entries": entries,
    }


# ---------- Savings Goals ----------

def _format_goal(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    d["target_amount"] = float(d["target_amount"])
    d["saved_amount"] = float(d["saved_amount"])
    remaining = max(d["target_amount"] - d["saved_amount"], 0.0)
    d["remaining"] = round(remaining, 2)
    d["pct_complete"] = round(
        (d["saved_amount"] / d["target_amount"] * 100), 1
    ) if d["target_amount"] else 0.0

    d["months_left"] = None
    d["required_monthly"] = None
    td = d.get("target_date")
    if td:
        if hasattr(td, "isoformat"):
            d["target_date"] = td.isoformat()
        today = date.today()
        if hasattr(td, "year"):
            months_left = (td.year - today.year) * 12 + (td.month - today.month)
        else:
            months_left = 0
        d["months_left"] = max(months_left, 0)
        if months_left > 0 and remaining > 0:
            d["required_monthly"] = round(remaining / months_left, 2)
    return d


def set_savings_goal(
    user_id: int,
    name: str,
    target_amount: float,
    saved_amount: float = 0.0,
    target_date: str | None = None,
) -> dict:
    """Upsert a savings goal by name for user_id."""
    date_val = None
    if target_date:
        try:
            date_val = datetime.fromisoformat(target_date).date()
        except ValueError:
            date_val = None

    with get_db_cursor() as cur:
        cur.execute(
            "SELECT id FROM savings_goals WHERE user_id = %s AND LOWER(name) = LOWER(%s)",
            (user_id, name.strip()),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE savings_goals
                SET target_amount = %s, target_date = %s
                WHERE id = %s
                RETURNING id, name, target_amount, saved_amount, target_date
                """,
                (target_amount, date_val, existing["id"]),
            )
        else:
            cur.execute(
                """
                INSERT INTO savings_goals (user_id, name, target_amount, saved_amount, target_date)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, target_amount, saved_amount, target_date
                """,
                (user_id, name.strip(), target_amount, saved_amount, date_val),
            )
        row = cur.fetchone()
        return _format_goal(row)


def contribute_to_goal(user_id: int, goal_id: int, amount: float) -> dict | None:
    """Add amount to saved_amount for a goal owned by user_id."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            UPDATE savings_goals
            SET saved_amount = saved_amount + %s
            WHERE id = %s AND user_id = %s
            RETURNING id, name, target_amount, saved_amount, target_date
            """,
            (amount, goal_id, user_id),
        )
        row = cur.fetchone()
        return _format_goal(row) if row else None


def get_goals(user_id: int) -> list[dict]:
    """Return all savings goals for user_id with computed progress info."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, target_amount, saved_amount, target_date
            FROM savings_goals WHERE user_id = %s
            ORDER BY created_at ASC
            """,
            (user_id,),
        )
        return [_format_goal(r) for r in cur.fetchall()]


def update_savings_goal(
    user_id: int,
    goal_id: int,
    name: str | None = None,
    target_amount: float | None = None,
    target_date: str | None = None,
) -> dict | None:
    """Update an existing savings goal owned by user_id."""
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM savings_goals WHERE id = %s AND user_id = %s", (goal_id, user_id))
        existing = cur.fetchone()
        if not existing:
            return None

        new_name = name.strip() if name is not None else existing["name"]
        new_target = target_amount if target_amount is not None else float(existing["target_amount"])

        if target_date == "":
            new_date = None
        elif target_date is not None:
            try:
                new_date = datetime.fromisoformat(target_date).date()
            except Exception:
                new_date = None
        else:
            new_date = existing["target_date"]

        cur.execute(
            """
            UPDATE savings_goals
            SET name = %s, target_amount = %s, target_date = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, name, target_amount, saved_amount, target_date
            """,
            (new_name, new_target, new_date, goal_id, user_id),
        )
        row = cur.fetchone()
        return _format_goal(row) if row else None


def delete_savings_goal(user_id: int, goal_id: int) -> bool:
    """Delete a savings goal owned by user_id."""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM savings_goals WHERE id = %s AND user_id = %s", (goal_id, user_id))
        return cur.rowcount > 0


# ---------- User Profile ----------

def get_user_profile(user_id: int) -> dict:
    """Return the user profile row, or defaults if not set."""
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM user_profile WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return {"user_id": user_id, "current_savings": None, "risk_comfort": None}
        d = dict(row)
        if d.get("current_savings") is not None:
            d["current_savings"] = float(d["current_savings"])
        if d.get("updated_at") and hasattr(d["updated_at"], "isoformat"):
            d["updated_at"] = d["updated_at"].isoformat()
        return d


def update_user_profile(
    user_id: int,
    current_savings: float | None = None,
    risk_comfort: str | None = None,
    living_situation: str | None = None,
) -> dict:
    """Upsert user profile fields."""
    with get_db_cursor() as cur:
        cur.execute("SELECT user_id FROM user_profile WHERE user_id = %s", (user_id,))
        exists = cur.fetchone()
        if exists:
            updates = []
            params: list = []
            if current_savings is not None:
                updates.append("current_savings = %s")
                params.append(current_savings)
            if risk_comfort is not None:
                updates.append("risk_comfort = %s")
                params.append(risk_comfort)
            if living_situation is not None:
                updates.append("living_situation = %s")
                params.append(living_situation)
            updates.append("updated_at = NOW()")
            params.append(user_id)
            cur.execute(
                f"UPDATE user_profile SET {', '.join(updates)} WHERE user_id = %s",
                tuple(params),
            )
        else:
            cur.execute(
                """
                INSERT INTO user_profile (user_id, current_savings, risk_comfort, living_situation)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, current_savings, risk_comfort, living_situation),
            )
    return get_user_profile(user_id)


# ---------- Logging Streak ----------

def get_logging_streak(user_id: int) -> dict:
    """Consecutive days the user has logged any transaction or income entry."""
    import datetime as dt
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT DATE(date AT TIME ZONE 'UTC') as day
            FROM (
                SELECT date FROM transactions WHERE user_id = %s
                UNION ALL
                SELECT date FROM income_entries WHERE user_id = %s
            ) combined
            ORDER BY day DESC
            """,
            (user_id, user_id),
        )
        days = [r["day"] for r in cur.fetchall()]

    if not days:
        return {"streak": 0, "last_entry_date": None}

    today = date.today()
    streak = 0
    expected = today

    for d in days:
        if d == expected or (streak == 0 and d == today - dt.timedelta(days=1)):
            expected = d - dt.timedelta(days=1)
            streak += 1
        else:
            break

    return {
        "streak": streak,
        "last_entry_date": days[0].isoformat() if days else None,
    }


# ---------- Financial Snapshot ----------

def get_financial_snapshot(user_id: int) -> dict:
    """
    Full financial snapshot for the current month.
    All arithmetic happens here in Python — agent uses this for guidance.
    """
    import calendar as cal

    month = current_month()
    today = date.today()

    income_data = get_income_summary(user_id, month)
    monthly_income = income_data["total"]

    spend = spend_by_category(user_id, month)
    monthly_expenses = sum(spend.values())

    budgets = get_budgets(user_id)
    if budgets:
        within = sum(1 for cat, limit in budgets.items() if spend.get(cat, 0) <= limit)
        budget_adherence_pct = round(within / len(budgets) * 100, 1)
    else:
        budget_adherence_pct = None

    net_surplus = monthly_income - monthly_expenses
    savings_rate = round(net_surplus / monthly_income * 100, 1) if monthly_income > 0 else None

    profile = get_user_profile(user_id)
    current_savings = profile.get("current_savings")
    emergency_months = None
    if current_savings is not None and monthly_expenses > 0:
        emergency_months = round(current_savings / monthly_expenses, 1)

    total_budget = sum(budgets.values()) if budgets else None
    safe_to_spend_today = None
    if total_budget is not None:
        remaining = total_budget - monthly_expenses
        days_in_month = cal.monthrange(today.year, today.month)[1]
        days_left = days_in_month - today.day + 1
        safe_to_spend_today = round(max(remaining, 0) / days_left, 2) if days_left > 0 else 0.0

    goals = get_goals(user_id)
    goals_summary = []
    for g in goals:
        pace = None
        if g.get("required_monthly") is not None:
            pace = "on_pace" if net_surplus >= g["required_monthly"] else "behind"
        goals_summary.append({
            "id": g["id"],
            "name": g["name"],
            "pct_complete": g["pct_complete"],
            "remaining": g["remaining"],
            "required_monthly": g.get("required_monthly"),
            "pace": pace,
        })

    streak = get_logging_streak(user_id)

    return {
        "month": month,
        "monthly_income": round(monthly_income, 2),
        "monthly_expenses": round(monthly_expenses, 2),
        "net_surplus": round(net_surplus, 2),
        "savings_rate_pct": savings_rate,
        "budget_adherence_pct": budget_adherence_pct,
        "emergency_months": emergency_months,
        "safe_to_spend_today": safe_to_spend_today,
        "current_savings": current_savings,
        "risk_comfort": profile.get("risk_comfort"),
        "goals": goals_summary,
        "logging_streak": streak["streak"],
    }


# ---------- Weekly Recap ----------

def get_weekly_recap(user_id: int) -> dict:
    """Deterministic weekly recap facts for the last 7 days."""
    import datetime as dt

    today = date.today()
    week_start = today - dt.timedelta(days=6)

    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM transactions
            WHERE user_id = %s AND DATE(date) >= %s AND DATE(date) <= %s
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id, week_start, today),
        )
        week_cats = [
            {"category": r["category"], "total": float(r["total"]), "count": int(r["count"])}
            for r in cur.fetchall()
        ]

        prior_start = week_start - dt.timedelta(days=7)
        prior_end = week_start - dt.timedelta(days=1)
        cur.execute(
            """
            SELECT SUM(amount) as total FROM transactions
            WHERE user_id = %s AND DATE(date) >= %s AND DATE(date) <= %s
            """,
            (user_id, prior_start, prior_end),
        )
        row = cur.fetchone()
        prior_week_total = float(row["total"] or 0)

        cur.execute(
            """
            SELECT SUM(amount) as total FROM income_entries
            WHERE user_id = %s AND DATE(date) >= %s AND DATE(date) <= %s
            """,
            (user_id, week_start, today),
        )
        row = cur.fetchone()
        week_income = float(row["total"] or 0)

    week_total = sum(c["total"] for c in week_cats)
    spend_change_pct = None
    if prior_week_total > 0:
        spend_change_pct = round((week_total - prior_week_total) / prior_week_total * 100, 1)

    streak = get_logging_streak(user_id)

    # Deterministic narration computed directly from facts
    if week_total == 0 and week_income == 0:
        narration = "No spending or income recorded in the past 7 days. Log expenses to unlock weekly insights."
    else:
        narration_parts = [f"You spent Rs {week_total:.0f} over the past 7 days"]
        if spend_change_pct is not None:
            if spend_change_pct > 0:
                narration_parts.append(f"up {spend_change_pct:.0f}% vs last week")
            elif spend_change_pct < 0:
                narration_parts.append(f"down {abs(spend_change_pct):.0f}% vs last week")
            else:
                narration_parts.append("matching last week")
        if week_cats:
            narration_parts.append(f"top expense was {week_cats[0]['category']} (Rs {week_cats[0]['total']:.0f})")
        if week_income > 0:
            narration_parts.append(f"earned Rs {week_income:.0f}")
        streak_val = streak.get("streak", 0)
        streak_note = f" {streak_val}-day logging streak active." if streak_val > 0 else ""
        narration = ", ".join(narration_parts) + "." + streak_note

    return {
        "period_start": week_start.isoformat(),
        "period_end": today.isoformat(),
        "total_spent": round(week_total, 2),
        "prior_week_total": round(prior_week_total, 2),
        "spend_change_pct": spend_change_pct,
        "top_category": week_cats[0] if week_cats else None,
        "week_income": round(week_income, 2),
        "week_surplus": round(week_income - week_total, 2),
        "categories": week_cats,
        "logging_streak": streak["streak"],
        "narration": narration,
    }


# ---------- Insights ----------

def get_insights(user_id: int) -> list[dict]:
    """
    3-5 deterministic insight cards. All math in Python.
    No LLM involvement — the agent narrates these.
    """
    import datetime as dt

    today = date.today()
    month = current_month()
    first_this = today.replace(day=1)
    last_month_end = first_this - dt.timedelta(days=1)
    prior_month = last_month_end.strftime("%Y-%m")

    insights: list[dict] = []

    spend_now = spend_by_category(user_id, month)
    spend_prior = spend_by_category(user_id, prior_month)

    # 1. Top category vs last month
    if spend_now:
        top_cat = max(spend_now, key=lambda c: spend_now[c])
        now_amt = spend_now[top_cat]
        prior_amt = spend_prior.get(top_cat, 0.0)
        change_pct = round((now_amt - prior_amt) / prior_amt * 100, 1) if prior_amt > 0 else None
        insights.append({
            "id": "top_category",
            "title": f"Top spend: {top_cat}",
            "value": round(now_amt, 2),
            "comparison": round(prior_amt, 2),
            "change_pct": change_pct,
            "direction": (
                "up" if (change_pct or 0) > 0
                else "down" if (change_pct or 0) < 0
                else "same"
            ),
        })

    # 2. Savings rate
    income_data = get_income_summary(user_id, month)
    total_income = income_data["total"]
    total_expenses = sum(spend_now.values())
    if total_income > 0:
        savings_rate = round((total_income - total_expenses) / total_income * 100, 1)
        insights.append({
            "id": "savings_rate",
            "title": "Savings rate this month",
            "value": savings_rate,
            "unit": "%",
            "healthy": savings_rate >= 20,
            "note": "Aim for 20%+ as a baseline" if savings_rate < 20 else "Good savings rate",
        })

    # 3. Overdue udhar
    udhar = get_udhar_summary(user_id)
    owed = [p for p in udhar["persons"] if p["net"] > 0]
    if owed:
        total_owed = sum(p["net"] for p in owed)
        insights.append({
            "id": "overdue_udhar",
            "title": "Money owed to you",
            "value": round(total_owed, 2),
            "persons": len(owed),
            "note": f"{len(owed)} person{'s' if len(owed) > 1 else ''} owe you money",
        })

    # 4. Goals behind pace
    goals = get_goals(user_id)
    net_surplus = total_income - total_expenses
    behind = [g["name"] for g in goals if g.get("required_monthly") and net_surplus < g["required_monthly"]]
    if behind:
        insights.append({
            "id": "goals_behind",
            "title": "Goals behind pace",
            "value": len(behind),
            "names": behind,
            "note": "Increase income or cut expenses to stay on track",
        })

    # 5. Emergency fund
    profile = get_user_profile(user_id)
    current_savings = profile.get("current_savings")
    if current_savings is not None and total_expenses > 0:
        months_covered = round(current_savings / total_expenses, 1)
        insights.append({
            "id": "emergency_fund",
            "title": "Emergency fund coverage",
            "value": months_covered,
            "unit": "months",
            "healthy": months_covered >= 3,
            "note": "Aim for 3-6 months of expenses" if months_covered < 3 else "Emergency fund is healthy",
        })

    return insights


# ---------- Onboarding ----------

# Default flat amounts (used when income is unknown/skipped).
# Tuned for a ~15k-25k/month earner in urban India.
_FLAT_DEFAULTS: dict[str, float] = {
    "rent": 8000,
    "groceries": 3000,
    "eating out": 1500,
    "travel": 1000,
    "utilities": 1500,
    "personal care": 500,
    "entertainment": 500,
    "shopping": 1000,
    "health": 500,
    "emergency fund": 1000,
    "sip / investments": 1000,
    "miscellaneous": 500,
}

# Percentage allocations by living situation (used when income IS known).
_PCT_WITH_RENT: dict[str, float] = {
    "rent": 0.30,
    "groceries": 0.10,
    "eating out": 0.06,
    "travel": 0.05,
    "utilities": 0.05,
    "personal care": 0.03,
    "entertainment": 0.03,
    "shopping": 0.05,
    "health": 0.03,
    "emergency fund": 0.10,
    "sip / investments": 0.10,
    "miscellaneous": 0.05,
}

_LIVING_RENT_MULT: dict[str, float] = {
    "family": 0.0,      # no rent
    "alone": 1.0,        # full rent (~30%)
    "pg": 0.50,          # PG/hostel (~15%)
    "roommates": 0.55,   # shared (~16.5%)
}


def suggest_budget_defaults(
    monthly_income: float | None,
    living_situation: str,
) -> dict[str, float]:
    """Pure deterministic budget suggestions. No LLM call.

    Args:
        monthly_income: user's monthly income, or None if skipped.
        living_situation: one of 'family', 'alone', 'pg', 'roommates'.

    Returns:
        dict mapping category name -> suggested monthly amount (rounded).
    """
    sit = living_situation.lower().strip() if living_situation else "alone"
    rent_mult = _LIVING_RENT_MULT.get(sit, 1.0)

    if monthly_income and monthly_income > 0:
        # Income-based percentages
        result: dict[str, float] = {}
        for cat, pct in _PCT_WITH_RENT.items():
            if cat == "rent":
                amount = monthly_income * pct * rent_mult
            else:
                # When rent is saved (family), redistribute ~5% extra to
                # savings and groceries proportionally.
                if rent_mult == 0.0 and cat in ("groceries", "sip / investments", "emergency fund"):
                    amount = monthly_income * (pct + 0.04)
                else:
                    amount = monthly_income * pct
            result[cat] = round(amount / 100) * 100  # round to nearest 100
        return result
    else:
        # Flat defaults
        result = dict(_FLAT_DEFAULTS)
        if rent_mult == 0.0:
            result["rent"] = 0
        elif sit == "pg":
            result["rent"] = 5000
        elif sit == "roommates":
            result["rent"] = 6000
        return result


def has_completed_onboarding(user_id: int) -> bool:
    """Check if user has any budgets set (proxy for onboarding completion)."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM budgets WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        return row["cnt"] > 0


def complete_onboarding(
    user_id: int,
    living_situation: str,
    monthly_income: float | None,
    categories: list[dict],
) -> dict:
    """Save onboarding results: upsert budgets for enabled categories,
    optionally store income entry and living_situation on user_profile.

    categories: list of {name: str, amount: float, enabled: bool}
    """
    saved_count = 0
    with get_db_cursor() as cur:
        # Upsert each enabled budget category
        for cat in categories:
            if not cat.get("enabled"):
                continue
            name = cat["name"].lower().strip()
            amount = float(cat["amount"])
            if amount <= 0:
                continue
            cur.execute(
                """
                INSERT INTO budgets (user_id, category, monthly_limit)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, category)
                DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit
                """,
                (user_id, name, amount),
            )
            saved_count += 1

        # Store living_situation on user_profile
        # Add columns if they don't exist (safe for ALTER IF NOT EXISTS)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'user_profile' AND column_name = 'living_situation'
                ) THEN
                    ALTER TABLE user_profile ADD COLUMN living_situation VARCHAR(50);
                END IF;
            END $$;
        """)

        cur.execute(
            """
            INSERT INTO user_profile (user_id, living_situation, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET living_situation = EXCLUDED.living_situation,
                updated_at = NOW()
            """,
            (user_id, living_situation),
        )

    # Store monthly income as an income entry if provided
    if monthly_income and monthly_income > 0:
        add_income_entry(
            user_id=user_id,
            amount=monthly_income,
            source="salary",
            entry_date=None,
        )

    return {"saved_categories": saved_count, "status": "ok"}


# ======================================================================
# TIER 1: Recurring Expenses & Bill Reminders
# ======================================================================

def advance_due_date(d: date, frequency: str) -> date:
    """Advance a date by one cycle: weekly (+7d), monthly (+1m), yearly (+1y)."""
    freq = (frequency or "monthly").lower().strip()
    if freq == "weekly":
        return d + timedelta(days=7)
    elif freq == "yearly":
        try:
            return d.replace(year=d.year + 1)
        except ValueError:
            return d.replace(year=d.year + 1, day=28)
    else:  # monthly
        year = d.year + (d.month // 12)
        month = (d.month % 12) + 1
        max_days = calendar.monthrange(year, month)[1]
        day = min(d.day, max_days)
        return date(year, month, day)


def auto_advance_due_date(d: date, frequency: str) -> date:
    """Repeatedly advance a due date until it is on or after today."""
    today = date.today()
    curr = d
    count = 0
    while curr < today and count < 1000:
        curr = advance_due_date(curr, frequency)
        count += 1
    return curr


def add_recurring_expense(
    user_id: int,
    name: str,
    amount: float,
    category: str,
    frequency: str = "monthly",
    start_date: str | None = None,
) -> dict:
    """
    Register a recurring bill or expense.
    frequency must be 'monthly', 'weekly', or 'yearly'.
    """
    freq = frequency.lower().strip()
    if freq not in ("monthly", "weekly", "yearly"):
        freq = "monthly"

    if start_date:
        try:
            due_d = date.fromisoformat(start_date.strip()[:10])
        except ValueError:
            due_d = date.today()
    else:
        due_d = date.today()

    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO recurring_expenses (user_id, name, amount, category, frequency, next_due_date, active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id, name, amount, category, frequency, next_due_date, active, created_at
            """,
            (user_id, name.strip(), amount, category.lower().strip(), freq, due_d),
        )
        row = cur.fetchone()
        d = dict(row)
        d["amount"] = float(d["amount"])
        if hasattr(d.get("next_due_date"), "isoformat"):
            d["next_due_date"] = d["next_due_date"].isoformat()
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        return d


def get_recurring_expenses(user_id: int, active_only: bool = False) -> list[dict]:
    """Fetch recurring expenses for a user."""
    query = """
        SELECT id, name, amount, category, frequency, next_due_date, active, last_reminded_date, created_at
        FROM recurring_expenses
        WHERE user_id = %s
    """
    params: list = [user_id]
    if active_only:
        query += " AND active = TRUE"
    query += " ORDER BY active DESC, next_due_date ASC"

    with get_db_cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["amount"] = float(d["amount"])
            if hasattr(d.get("next_due_date"), "isoformat"):
                d["next_due_date"] = d["next_due_date"].isoformat()
            if hasattr(d.get("last_reminded_date"), "isoformat") and d.get("last_reminded_date"):
                d["last_reminded_date"] = d["last_reminded_date"].isoformat()
            if hasattr(d.get("created_at"), "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            result.append(d)
        return result


def deactivate_recurring_expense(user_id: int, expense_id: int) -> bool:
    """Deactivate a recurring expense."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            UPDATE recurring_expenses
            SET active = FALSE
            WHERE id = %s AND user_id = %s
            """,
            (expense_id, user_id),
        )
        return cur.rowcount > 0


def toggle_recurring_expense(user_id: int, expense_id: int, active: bool | None = None) -> dict | None:
    """Toggle or set the active status of a recurring expense."""
    with get_db_cursor() as cur:
        cur.execute("SELECT active FROM recurring_expenses WHERE id = %s AND user_id = %s", (expense_id, user_id))
        row = cur.fetchone()
        if not row:
            return None
        new_active = not row["active"] if active is None else active
        cur.execute(
            """
            UPDATE recurring_expenses
            SET active = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, name, amount, category, frequency, next_due_date, active, last_reminded_date, created_at
            """,
            (new_active, expense_id, user_id),
        )
        updated = cur.fetchone()
        if not updated:
            return None
        d = dict(updated)
        d["amount"] = float(d["amount"])
        for f in ("next_due_date", "last_reminded_date", "created_at"):
            if d.get(f) and hasattr(d[f], "isoformat"):
                d[f] = d[f].isoformat()
        return d


def update_recurring_expense(
    user_id: int,
    expense_id: int,
    name: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    frequency: str | None = None,
    next_due_date: str | None = None,
    active: bool | None = None,
) -> dict | None:
    """Update fields of an existing recurring expense."""
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM recurring_expenses WHERE id = %s AND user_id = %s", (expense_id, user_id))
        existing = cur.fetchone()
        if not existing:
            return None

        new_name = name.strip() if name is not None else existing["name"]
        new_amount = amount if amount is not None else float(existing["amount"])
        new_category = category.strip() if category is not None else existing["category"]
        new_freq = frequency.strip() if frequency is not None else existing["frequency"]
        new_active = active if active is not None else existing["active"]

        if next_due_date is not None:
            try:
                new_date = datetime.fromisoformat(next_due_date).date()
            except Exception:
                new_date = existing["next_due_date"]
        else:
            new_date = existing["next_due_date"]

        cur.execute(
            """
            UPDATE recurring_expenses
            SET name = %s, amount = %s, category = %s, frequency = %s, next_due_date = %s, active = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, name, amount, category, frequency, next_due_date, active, last_reminded_date, created_at
            """,
            (new_name, new_amount, new_category, new_freq, new_date, new_active, expense_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["amount"] = float(d["amount"])
        for f in ("next_due_date", "last_reminded_date", "created_at"):
            if d.get(f) and hasattr(d[f], "isoformat"):
                d[f] = d[f].isoformat()
        return d


def delete_recurring_expense(user_id: int, expense_id: int) -> bool:
    """Delete a recurring expense owned by user_id."""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM recurring_expenses WHERE id = %s AND user_id = %s", (expense_id, user_id))
        return cur.rowcount > 0


def check_and_process_recurring_reminders(user_id: int | None = None) -> list[dict]:
    """
    Check for active recurring bills due within 2 days.
    Auto-advances past due dates by cycle.
    Updates last_reminded_date to prevent duplicate alerts.
    Returns list of bills due within 2 days.
    """
    today = date.today()
    query = """
        SELECT id, user_id, name, amount, category, frequency, next_due_date, last_reminded_date
        FROM recurring_expenses
        WHERE active = TRUE
    """
    params: list = []
    if user_id is not None:
        query += " AND user_id = %s"
        params.append(user_id)

    with get_db_cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

    reminders = []
    updates = []

    for r in rows:
        due_d = r["next_due_date"]
        freq = r["frequency"]
        exp_id = r["id"]
        last_reminded = r["last_reminded_date"]

        # 1. If past due, advance until on or after today
        if due_d < today:
            due_d = auto_advance_due_date(due_d, freq)
            updates.append((due_d, last_reminded, exp_id))

        # 2. Check if due within 2 days (today <= due_d <= today + 2 days)
        days_until = (due_d - today).days
        if 0 <= days_until <= 2:
            # Check if reminded today already
            is_reminded_today = (last_reminded == today)
            reminders.append({
                "id": exp_id,
                "user_id": r["user_id"],
                "name": r["name"],
                "amount": float(r["amount"]),
                "category": r["category"],
                "frequency": freq,
                "next_due_date": due_d.isoformat(),
                "days_until_due": days_until,
                "is_due_today": (days_until == 0),
            })
            if not is_reminded_today:
                # Mark reminded today
                updates.append((due_d, today, exp_id))

    if updates:
        with get_db_cursor() as cur:
            for new_due, new_reminded, eid in updates:
                cur.execute(
                    """
                    UPDATE recurring_expenses
                    SET next_due_date = %s, last_reminded_date = %s
                    WHERE id = %s
                    """,
                    (new_due, new_reminded, eid),
                )

    return reminders


# ======================================================================
# TIER 1: Group / Split Expenses via Udhar
# ======================================================================

def split_expense(
    user_id: int,
    total_amount: float,
    category: str,
    note: str,
    participants: list[dict],
) -> dict:
    """
    Split a group expense among user and participants.
    Logs 1 full transaction for the user, and creates 'lent' udhar entries
    for all other participants.
    """
    if total_amount <= 0:
        raise ValueError("total_amount must be greater than 0")
    if not participants:
        raise ValueError("participants list cannot be empty")

    cat = category.lower().strip() or "food"
    clean_note = note.strip()

    # Determine shares
    has_custom_shares = all(p.get("share") is not None and float(p.get("share", 0)) > 0 for p in participants)

    clean_participants = []
    if has_custom_shares:
        sum_shares = sum(float(p["share"]) for p in participants)
        if sum_shares > total_amount:
            raise ValueError(f"Sum of participant shares (Rs {sum_shares:.0f}) exceeds total amount (Rs {total_amount:.0f})")
        user_share = round(total_amount - sum_shares, 2)
        for p in participants:
            clean_participants.append({
                "name": p["name"].strip(),
                "share": round(float(p["share"]), 2),
            })
    else:
        # Equal split across (1 user + len(participants))
        total_heads = 1 + len(participants)
        each_share = round(total_amount / total_heads, 2)
        sum_others = round(each_share * len(participants), 2)
        user_share = round(total_amount - sum_others, 2)
        for p in participants:
            clean_participants.append({
                "name": p["name"].strip(),
                "share": each_share,
            })

    # 1. Log single transaction for full spend
    tx_note = f"{clean_note} (Split)" if clean_note else "Split expense"
    tx = log_transaction(
        user_id=user_id,
        amount=total_amount,
        category=cat,
        note=tx_note,
    )

    # 2. Create udhar entries for each participant
    created_udhars = []
    for p in clean_participants:
        udhar_note = f"Split: {clean_note}" if clean_note else f"Split ({cat})"
        u = add_udhar(
            user_id=user_id,
            person_name=p["name"],
            kind="lent",
            amount=p["share"],
            note=udhar_note,
            due_date=None,
            is_split=True,
            transaction_id=tx["id"],
        )
        created_udhars.append(u)

    names = ", ".join(p["name"] for p in clean_participants)
    lent_total = round(total_amount - user_share, 2)
    return {
        "transaction": tx,
        "total_amount": total_amount,
        "user_share": user_share,
        "participants": clean_participants,
        "created_udhars": created_udhars,
        "summary": f"Split Rs {total_amount:.0f} ({cat}) with {names}. Your share is Rs {user_share:.0f}, lent Rs {lent_total:.0f} total.",
    }


# ======================================================================
# TIER 1: Financial Health Score
# ======================================================================

def compute_health_score(user_id: int, month: str | None = None) -> dict:
    """
    Deterministic 0-100 financial health score.
    Weighted factors:
      - Savings rate (35%)
      - Budget adherence (30%)
      - Emergency fund coverage (20%)
      - Logging consistency (15%)
    Dynamically re-normalizes if optional data (income, savings profile, budgets) is missing.
    """
    target_month = month or current_month()

    # 1. Savings Rate (35%)
    inc_data = get_income_summary(user_id=user_id, month=target_month)
    income = inc_data["total"]
    spend_map = spend_by_category(user_id=user_id, month=target_month)
    total_spend = sum(spend_map.values())

    savings_factor = None
    if income > 0:
        net_saved = income - total_spend
        rate = (net_saved / income) * 100
        if rate >= 30:
            s_score, s_status, s_tip = 100, "Excellent", "Superb savings rate! Keep growing your surplus."
        elif rate >= 20:
            s_score, s_status, s_tip = 80, "Good", "Solid savings rate. Aim for 30%+ to boost long-term wealth."
        elif rate >= 10:
            s_score, s_status, s_tip = 60, "Fair", "Fair savings rate. Look for discretionary cuts to reach 20%."
        elif rate >= 0:
            s_score, s_status, s_tip = 40, "Needs Attention", "Tight savings buffer. Try to build a 10%+ monthly margin."
        else:
            s_score, s_status, s_tip = 10, "Critical", "Expenses exceed income this month. Review non-essential spending."

        savings_factor = {
            "id": "savings_rate",
            "name": "Savings Rate",
            "score": s_score,
            "base_weight": 35,
            "status": s_status,
            "raw_metric": f"{rate:.1f}%",
            "description": f"Saved {rate:.1f}% of income (Rs {net_saved:.0f})",
            "tip": s_tip,
        }

    # 2. Budget Adherence (30%)
    eff_budgets = get_effective_budgets(user_id=user_id, month=target_month)
    adherence_factor = None
    if eff_budgets:
        total_cats = len(eff_budgets)
        within_count = 0
        for cat, b in eff_budgets.items():
            if spend_map.get(cat, 0.0) <= b["effective_budget"]:
                within_count += 1
        adh_pct = (within_count / total_cats) * 100

        if adh_pct == 100:
            a_score, a_status, a_tip = 100, "Excellent", "All category budgets respected! Excellent discipline."
        elif adh_pct >= 80:
            a_score, a_status, a_tip = 75, "Good", "Most budgets maintained. Watch the 1-2 categories nearing their cap."
        elif adh_pct >= 60:
            a_score, a_status, a_tip = 50, "Fair", "Several categories exceeded. Consider adjusting limits."
        elif adh_pct >= 40:
            a_score, a_status, a_tip = 30, "Needs Attention", "Frequent budget overruns. Re-align limits with spending realities."
        else:
            a_score, a_status, a_tip = 10, "Critical", "Most budgets breached. Review overall category allocations."

        adherence_factor = {
            "id": "budget_adherence",
            "name": "Budget Adherence",
            "score": a_score,
            "base_weight": 30,
            "status": a_status,
            "raw_metric": f"{within_count}/{total_cats} ({adh_pct:.0f}%)",
            "description": f"{within_count} of {total_cats} categories within budget",
            "tip": a_tip,
        }

    # 3. Emergency Fund Coverage (20%)
    profile = get_user_profile(user_id=user_id)
    current_savings = profile.get("current_savings")
    emergency_factor = None
    if current_savings is not None and current_savings > 0:
        # Benchmark monthly expense: current month spend or budget or default 10k
        bench_spend = total_spend
        if bench_spend <= 0:
            bench_spend = sum(b["effective_budget"] for b in eff_budgets.values())
        if bench_spend <= 0:
            bench_spend = 10000.0

        months_cov = round(current_savings / bench_spend, 1)
        if months_cov >= 6.0:
            e_score, e_status, e_tip = 100, "Excellent", "Full emergency runway (6+ months) secured."
        elif months_cov >= 3.0:
            e_score, e_status, e_tip = 80, "Good", "Healthy safety net (3-6 months). Keep building towards 6 months."
        elif months_cov >= 1.0:
            e_score, e_status, e_tip = 50, "Fair", "Partial coverage (1-3 months). Prioritize reaching 3 months."
        else:
            e_score, e_status, e_tip = 20, "Needs Attention", "Less than 1 month coverage. Build an initial safety cushion."

        emergency_factor = {
            "id": "emergency_fund",
            "name": "Emergency Fund",
            "score": e_score,
            "base_weight": 20,
            "status": e_status,
            "raw_metric": f"{months_cov:.1f} mos",
            "description": f"Covers {months_cov:.1f} months of expenses (Rs {current_savings:.0f})",
            "tip": e_tip,
        }

    # 4. Logging Consistency (15%)
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(DISTINCT DATE(date AT TIME ZONE 'UTC')) as active_days
            FROM transactions
            WHERE user_id = %s AND TO_CHAR(date, 'YYYY-MM') = %s
            """,
            (user_id, target_month),
        )
        row = cur.fetchone()
        active_days = int(row["active_days"]) if row else 0

    try:
        y, m = map(int, target_month.split("-"))
        if target_month == current_month():
            days_elapsed = max(1, date.today().day)
        else:
            days_elapsed = calendar.monthrange(y, m)[1]
    except Exception:
        days_elapsed = 30

    consistency_pct = min(100.0, (active_days / days_elapsed) * 100)
    if consistency_pct >= 50:
        c_score, c_status, c_tip = 100, "Excellent", "Consistent tracking habits give you crystal-clear money clarity."
    elif consistency_pct >= 30:
        c_score, c_status, c_tip = 70, "Good", "Regular tracking. Log small daily spends to avoid leaks."
    else:
        c_score, c_status, c_tip = 30, "Needs Attention", "Infrequent logs. Try logging right after each transaction."

    consistency_factor = {
        "id": "logging_consistency",
        "name": "Logging Consistency",
        "score": c_score,
        "base_weight": 15,
        "status": c_status,
        "raw_metric": f"{active_days}/{days_elapsed} days ({consistency_pct:.0f}%)",
        "description": f"Logged spending on {active_days} of {days_elapsed} days",
        "tip": c_tip,
    }

    # Dynamic Re-normalization
    factors = [f for f in [savings_factor, adherence_factor, emergency_factor, consistency_factor] if f is not None]
    total_active_weight = sum(f["base_weight"] for f in factors)

    if total_active_weight == 0:
        final_score = 50
    else:
        weighted_sum = sum(f["score"] * f["base_weight"] for f in factors)
        final_score = int(round(weighted_sum / total_active_weight))

    final_score = max(0, min(100, final_score))

    if final_score >= 80:
        tier = "Excellent"
    elif final_score >= 65:
        tier = "Good"
    elif final_score >= 50:
        tier = "Fair"
    else:
        tier = "Needs Attention"

    for f in factors:
        f["normalized_weight"] = round((f["base_weight"] / total_active_weight) * 100) if total_active_weight > 0 else 0

    tips = [f["tip"] for f in factors]
    if not savings_factor:
        tips.append("Add your monthly income in Settings to enable the Savings Rate factor.")
    if not emergency_factor:
        tips.append("Update your Current Savings in Profile to track Emergency Runway.")
    if not adherence_factor:
        tips.append("Configure monthly budgets to enable the Budget Adherence factor.")

    return {
        "score": final_score,
        "tier": tier,
        "is_partial": len(factors) < 4,
        "month": target_month,
        "factors": factors,
        "tips": tips,
    }


# ======================================================================
# TIER 1: Monthly Export (PDF / Excel)
# ======================================================================

def generate_monthly_excel(user_id: int, user_email: str, month: str) -> bytes:
    """Generate a clean, professional Excel statement with Summary and Transactions sheets."""
    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "Summary"

    # Styling tokens
    font_title = Font(name="Segoe UI", size=14, bold=True, color="10B981")
    font_meta = Font(name="Segoe UI", size=9, color="64748B")
    font_sec = Font(name="Segoe UI", size=11, bold=True, color="0F172A")
    font_th = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_td = Font(name="Segoe UI", size=10, color="0F172A")
    font_bold = Font(name="Segoe UI", size=10, bold=True, color="0F172A")

    fill_th = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    fill_kpi = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0'),
    )

    # 1. Fetch data
    inc_data = get_income_summary(user_id=user_id, month=month)
    total_income = inc_data["total"]
    eff_budgets = get_effective_budgets(user_id=user_id, month=month)
    cat_spend = spend_by_category(user_id=user_id, month=month)
    transactions = get_transactions(user_id=user_id, month=month)
    total_spent = sum(cat_spend.values())
    net_savings = total_income - total_spent
    savings_rate = (net_savings / total_income * 100) if total_income > 0 else 0.0

    # Summary Sheet Header
    ws_summary["A1"] = "ABT — Monthly Financial Statement"
    ws_summary["A1"].font = font_title
    ws_summary["A2"] = f"Period: {month}   |   Account: {user_email}   |   Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws_summary["A2"].font = font_meta

    # Key Metrics Table
    ws_summary["A4"] = "Monthly Performance Overview"
    ws_summary["A4"].font = font_sec

    kpi_headers = ["Total Income", "Total Spending", "Net Savings", "Savings Rate"]
    kpi_values = [total_income, total_spent, net_savings, f"{savings_rate:.1f}%"]

    for col_idx, (h, v) in enumerate(zip(kpi_headers, kpi_values), start=1):
        cell_h = ws_summary.cell(row=5, column=col_idx, value=h)
        cell_h.font = font_th
        cell_h.fill = fill_th
        cell_h.alignment = Alignment(horizontal="center", vertical="center")
        cell_h.border = thin_border

        cell_v = ws_summary.cell(row=6, column=col_idx, value=v)
        cell_v.font = font_bold
        cell_v.fill = fill_kpi
        cell_v.alignment = Alignment(horizontal="center", vertical="center")
        cell_v.border = thin_border
        if isinstance(v, (int, float)):
            cell_v.number_format = '"Rs " #,##0.00'

    # Category Breakdown Table
    ws_summary["A8"] = "Category Breakdown & Budget Adherence"
    ws_summary["A8"].font = font_sec

    cat_headers = ["Category", "Base Budget", "Carried Rollover", "Effective Budget", "Actual Spent", "Remaining", "% Used"]
    for col_idx, h in enumerate(cat_headers, start=1):
        cell = ws_summary.cell(row=9, column=col_idx, value=h)
        cell.font = font_th
        cell.fill = fill_th
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    all_cats = sorted(set(list(eff_budgets.keys()) + list(cat_spend.keys())))
    row_num = 10
    total_effective_b = 0.0

    for cat in all_cats:
        b_info = eff_budgets.get(cat, {})
        base_b = b_info.get("base_limit", 0.0)
        carried = b_info.get("carried_amount", 0.0)
        eff_b = b_info.get("effective_budget", base_b + carried)
        spent = cat_spend.get(cat, 0.0)
        remaining = eff_b - spent if eff_b > 0 else 0.0
        pct = (spent / eff_b * 100) if eff_b > 0 else 0.0
        if eff_b > 0:
            total_effective_b += eff_b

        is_even = (row_num % 2 == 0)
        row_fill = fill_zebra if is_even else None

        values = [cat.capitalize(), base_b, carried, eff_b, spent, remaining, f"{pct:.1f}%"]
        for c_idx, val in enumerate(values, start=1):
            cell = ws_summary.cell(row=row_num, column=c_idx, value=val)
            cell.font = font_td
            if row_fill:
                cell.fill = row_fill
            cell.border = thin_border
            if c_idx in (2, 3, 4, 5, 6):
                cell.number_format = '"Rs " #,##0.00'
                cell.alignment = Alignment(horizontal="right")
            elif c_idx == 7:
                cell.alignment = Alignment(horizontal="right")
            else:
                cell.alignment = Alignment(horizontal="left")
        row_num += 1

    # Total Row
    ws_summary.cell(row=row_num, column=1, value="Total").font = font_bold
    ws_summary.cell(row=row_num, column=4, value=total_effective_b).font = font_bold
    ws_summary.cell(row=row_num, column=4).number_format = '"Rs " #,##0.00'
    ws_summary.cell(row=row_num, column=5, value=total_spent).font = font_bold
    ws_summary.cell(row=row_num, column=5).number_format = '"Rs " #,##0.00'
    ws_summary.cell(row=row_num, column=6, value=total_effective_b - total_spent).font = font_bold
    ws_summary.cell(row=row_num, column=6).number_format = '"Rs " #,##0.00'
    for c in range(1, 8):
        ws_summary.cell(row=row_num, column=c).border = thin_border

    # Sheet 2: Transactions
    ws_tx = wb.create_sheet(title="Transactions")
    ws_tx["A1"] = f"Transactions Log — {month}"
    ws_tx["A1"].font = font_title

    tx_headers = ["ID", "Date", "Category", "Amount", "Note"]
    for col_idx, h in enumerate(tx_headers, start=1):
        cell = ws_tx.cell(row=3, column=col_idx, value=h)
        cell.font = font_th
        cell.fill = fill_th
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    t_row = 4
    for t in transactions:
        d_str = t["date"][:10] if isinstance(t.get("date"), str) else str(t.get("date", ""))[:10]
        amt = float(t.get("amount", 0.0))
        vals = [t.get("id"), d_str, (t.get("category") or "").capitalize(), amt, t.get("note") or ""]

        is_even = (t_row % 2 == 0)
        row_fill = fill_zebra if is_even else None

        for c_idx, val in enumerate(vals, start=1):
            cell = ws_tx.cell(row=t_row, column=c_idx, value=val)
            cell.font = font_td
            if row_fill:
                cell.fill = row_fill
            cell.border = thin_border
            if c_idx == 4:
                cell.number_format = '"Rs " #,##0.00'
                cell.alignment = Alignment(horizontal="right")
            elif c_idx == 1:
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.alignment = Alignment(horizontal="left")
        t_row += 1

    # Auto-adjust column widths
    for sheet in (ws_summary, ws_tx):
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            sheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_monthly_pdf(user_id: int, user_email: str, month: str) -> bytes:
    """Generate a clean, professional PDF statement using ReportLab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
    )
    meta_style = ParagraphStyle(
        "MetaInfo",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#64748B"),
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=14,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0F172A"),
    )
    cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )

    # 1. Fetch data
    inc_data = get_income_summary(user_id=user_id, month=month)
    total_income = inc_data["total"]
    eff_budgets = get_effective_budgets(user_id=user_id, month=month)
    cat_spend = spend_by_category(user_id=user_id, month=month)
    transactions = get_transactions(user_id=user_id, month=month)
    total_spent = sum(cat_spend.values())
    net_savings = total_income - total_spent
    savings_rate = (net_savings / total_income * 100) if total_income > 0 else 0.0

    elements = []

    # Title & Metadata
    elements.append(Paragraph("ABT — Monthly Financial Statement", title_style))
    elements.append(Paragraph(
        f"Period: <b>{month}</b> &nbsp;|&nbsp; Account: <b>{user_email}</b> &nbsp;|&nbsp; Generated: <b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>",
        meta_style,
    ))
    elements.append(Spacer(1, 10))

    # KPI Table (Income, Expenses, Net Savings, Rate)
    kpi_data = [
        [
            Paragraph("<b>Total Income</b>", cell_style),
            Paragraph("<b>Total Expenses</b>", cell_style),
            Paragraph("<b>Net Savings</b>", cell_style),
            Paragraph("<b>Savings Rate</b>", cell_style),
        ],
        [
            Paragraph(f"<b>Rs {total_income:,.0f}</b>", cell_bold),
            Paragraph(f"<b>Rs {total_spent:,.0f}</b>", cell_bold),
            Paragraph(f"<b>Rs {net_savings:,.0f}</b>", cell_bold),
            Paragraph(f"<b>{savings_rate:.1f}%</b>", cell_bold),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[135, 135, 135, 135])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(kpi_table)

    # Category Breakdown Table
    elements.append(Paragraph("Category Breakdown & Budgets", section_style))
    cat_rows = [[
        Paragraph("<b>Category</b>", cell_bold),
        Paragraph("<b>Effective Budget</b>", cell_bold),
        Paragraph("<b>Actual Spent</b>", cell_bold),
        Paragraph("<b>Remaining</b>", cell_bold),
        Paragraph("<b>% Used</b>", cell_bold),
    ]]

    all_cats = sorted(set(list(eff_budgets.keys()) + list(cat_spend.keys())))
    total_eff_budget = 0.0

    for cat in all_cats:
        b_info = eff_budgets.get(cat, {})
        eff_b = b_info.get("effective_budget", 0.0)
        spent = cat_spend.get(cat, 0.0)
        rem = eff_b - spent if eff_b > 0 else 0.0
        pct = (spent / eff_b * 100) if eff_b > 0 else 0.0
        if eff_b > 0:
            total_eff_budget += eff_b

        cat_rows.append([
            Paragraph(cat.capitalize(), cell_style),
            Paragraph(f"Rs {eff_b:,.0f}" if eff_b > 0 else "—", cell_style),
            Paragraph(f"Rs {spent:,.0f}", cell_style),
            Paragraph(f"Rs {rem:,.0f}" if eff_b > 0 else "—", cell_style),
            Paragraph(f"{pct:.0f}%" if eff_b > 0 else "—", cell_style),
        ])

    # Totals row
    cat_rows.append([
        Paragraph("<b>Total</b>", cell_bold),
        Paragraph(f"<b>Rs {total_eff_budget:,.0f}</b>", cell_bold),
        Paragraph(f"<b>Rs {total_spent:,.0f}</b>", cell_bold),
        Paragraph(f"<b>Rs {total_eff_budget - total_spent:,.0f}</b>", cell_bold),
        Paragraph(f"<b>{(total_spent / total_eff_budget * 100):.0f}%</b>" if total_eff_budget > 0 else "—", cell_bold),
    ])

    cat_table = Table(cat_rows, colWidths=[140, 100, 100, 100, 100])
    cat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor("#0F172A")),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))
    elements.append(cat_table)

    # Transactions List Table
    elements.append(Paragraph("Transactions Log", section_style))
    tx_rows = [[
        Paragraph("<b>Date</b>", cell_bold),
        Paragraph("<b>Category</b>", cell_bold),
        Paragraph("<b>Amount</b>", cell_bold),
        Paragraph("<b>Note</b>", cell_bold),
    ]]

    for t in transactions[:40]:  # Limit to 40 most recent for clean single/double page format
        d_str = t["date"][:10] if isinstance(t.get("date"), str) else str(t.get("date", ""))[:10]
        amt = float(t.get("amount", 0.0))
        tx_rows.append([
            Paragraph(d_str, cell_style),
            Paragraph((t.get("category") or "").capitalize(), cell_style),
            Paragraph(f"Rs {amt:,.0f}", cell_style),
            Paragraph(t.get("note") or "—", cell_style),
        ])

    if len(transactions) > 40:
        tx_rows.append([
            Paragraph(f"<i>...and {len(transactions) - 40} more transactions (see Excel export for full log)</i>", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
        ])

    tx_table = Table(tx_rows, colWidths=[80, 100, 90, 270])
    tx_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    elements.append(tx_table)

    doc.build(elements)
    return buf.getvalue()


# ======================================================================
# USERNAME & AVATAR
# ======================================================================

def set_username(user_id: int, username: str) -> dict:
    """Set a username (3-20 chars, alphanumeric + underscores)."""
    clean = username.strip()
    if len(clean) < 3 or len(clean) > 20:
        raise ValueError("Username must be 3-20 characters.")
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE users SET username = %s WHERE id = %s RETURNING id, email, username, avatar_id, avatar_url",
            (clean, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def set_avatar(user_id: int, avatar_id: int) -> dict:
    """Set preset avatar_id (1-8) and clear uploaded photo."""
    aid = max(1, min(8, avatar_id))
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE users SET avatar_id = %s, avatar_url = NULL WHERE id = %s RETURNING id, email, username, avatar_id, avatar_url",
            (aid, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def set_user_avatar_url(user_id: int, avatar_url: Optional[str]) -> dict:
    """Set or clear avatar_url for photo upload."""
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE users SET avatar_url = %s WHERE id = %s RETURNING id, email, username, avatar_id, avatar_url",
            (avatar_url, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def get_user_display(user_id: int) -> dict:
    """Get display info: username, avatar_id, avatar_url, email."""
    with get_db_cursor() as cur:
        cur.execute("SELECT id, email, username, avatar_id, avatar_url FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return {}
        d = dict(row)
        d["needs_username"] = not bool(d.get("username"))
        return d


# ======================================================================
# MERCHANT NORMALIZATION
# ======================================================================

# Built-in merchant alias list: common Indian merchants
_BUILTIN_ALIASES: dict[str, str] = {
    "swiggy": "Swiggy",
    "zomato": "Zomato",
    "zepto": "Zepto",
    "blinkit": "Blinkit",
    "bigbasket": "BigBasket",
    "dmart": "DMart",
    "amazon": "Amazon",
    "flipkart": "Flipkart",
    "myntra": "Myntra",
    "uber": "Uber",
    "ola": "Ola",
    "rapido": "Rapido",
    "irctc": "IRCTC",
    "jio": "Jio",
    "airtel": "Airtel",
    "vi": "Vi",
    "bsnl": "BSNL",
    "netflix": "Netflix",
    "hotstar": "Hotstar",
    "spotify": "Spotify",
    "youtube": "YouTube",
    "gpay": "GPay",
    "paytm": "Paytm",
    "phonepe": "PhonePe",
    "cred": "CRED",
    "dunzo": "Dunzo",
    "nykaa": "Nykaa",
    "bookmyshow": "BookMyShow",
    "makemytrip": "MakeMyTrip",
    "goibibo": "Goibibo",
    "cleartrip": "Cleartrip",
    "ajio": "AJIO",
    "meesho": "Meesho",
    "reliance": "Reliance",
    "tata": "Tata",
    "bigbazaar": "BigBazaar",
    "starbucks": "Starbucks",
    "mcdonalds": "McDonald's",
    "kfc": "KFC",
    "dominos": "Domino's",
    "pizzahut": "Pizza Hut",
    "subway": "Subway",
    "haldirams": "Haldiram's",
    "decathlon": "Decathlon",
    "ikea": "IKEA",
    "hdfc": "HDFC",
    "sbi": "SBI",
    "icici": "ICICI",
    "kotak": "Kotak",
    "axis": "Axis",
}

import re as _re
import unicodedata as _ud

def _clean_merchant_text(text: str) -> str:
    """Lowercase, strip punctuation, remove order IDs and city suffixes."""
    s = text.lower().strip()
    # Remove order IDs like #12345, order-67890
    s = _re.sub(r'[#]?\b(order|txn|ref|id)[- _]?[a-z0-9]+\b', '', s, flags=_re.IGNORECASE)
    # Remove city suffixes like *BLR, *MUM etc
    s = _re.sub(r'\*[a-z]{2,5}\b', '', s)
    # Strip all non-alphanumeric except spaces
    s = _re.sub(r'[^a-z0-9\s]', ' ', s)
    s = _re.sub(r'\s+', ' ', s).strip()
    return s


def _fuzzy_match(needle: str, haystack: str, threshold: float = 0.7) -> bool:
    """Simple character-overlap similarity for fuzzy matching."""
    if not needle or not haystack:
        return False
    a, b = set(needle.lower()), set(haystack.lower())
    if not a or not b:
        return False
    overlap = len(a & b) / max(len(a | b), 1)
    # Also check if one contains the other
    if needle.lower() in haystack.lower() or haystack.lower() in needle.lower():
        return True
    return overlap >= threshold


def normalize_merchant(user_id: int, raw_note: str) -> str | None:
    """Deterministic merchant normalization. No LLM calls.
    1. Clean the text
    2. Check user's custom aliases
    3. Check built-in alias list
    4. Fuzzy match against user's prior merchants
    5. Return normalized name or None if no match
    """
    if not raw_note or len(raw_note.strip()) < 2:
        return None

    cleaned = _clean_merchant_text(raw_note)
    if not cleaned:
        return None

    # 1. Check user's custom aliases
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT normalized_name FROM merchant_aliases WHERE user_id = %s AND LOWER(raw_input) = LOWER(%s)",
            (user_id, cleaned),
        )
        row = cur.fetchone()
        if row:
            return row["normalized_name"]

    # 2. Check built-in aliases
    for key, canonical in _BUILTIN_ALIASES.items():
        if key in cleaned or _fuzzy_match(key, cleaned):
            return canonical

    # 3. Fuzzy match against user's prior merchant names
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT merchant FROM transactions
            WHERE user_id = %s AND merchant IS NOT NULL
            ORDER BY merchant
            LIMIT 100
            """,
            (user_id,),
        )
        priors = [r["merchant"] for r in cur.fetchall()]

    for prior in priors:
        if _fuzzy_match(cleaned, _clean_merchant_text(prior)):
            return prior

    # No match found -- title-case the cleaned text as a reasonable display name
    if len(cleaned) >= 3:
        return cleaned.title()

    return None


def add_merchant_alias(user_id: int, raw_input: str, normalized_name: str) -> dict:
    """Store a user correction for merchant normalization."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO merchant_aliases (user_id, raw_input, normalized_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, LOWER(raw_input))
            DO UPDATE SET normalized_name = EXCLUDED.normalized_name
            RETURNING id, raw_input, normalized_name
            """,
            (user_id, raw_input.strip().lower(), normalized_name.strip()),
        )
        row = cur.fetchone()
        return dict(row) if row else {}


# ======================================================================
# DUPLICATE DETECTION
# ======================================================================

def check_duplicate_expense(user_id: int, amount: float, category: str = "", note: str = "", entry_date: str | None = None) -> dict | None:
    """Check if a similar expense was logged today or on entry_date. Returns the existing record if found."""
    with get_db_cursor() as cur:
        if entry_date:
            cur.execute(
                """
                SELECT id, amount, category, note, merchant, date
                FROM transactions
                WHERE user_id = %s
                  AND amount = %s
                  AND DATE(date) = %s
                ORDER BY date DESC
                LIMIT 1
                """,
                (user_id, amount, entry_date),
            )
        else:
            cat_clause = "AND category = %s" if category else ""
            params = [user_id, amount]
            if category:
                params.append(category.lower().strip())
            cur.execute(
                f"""
                SELECT id, amount, category, note, merchant, date
                FROM transactions
                WHERE user_id = %s
                  AND amount = %s
                  {cat_clause}
                  AND DATE(date AT TIME ZONE 'UTC') = CURRENT_DATE
                ORDER BY date DESC
                LIMIT 1
                """,
                tuple(params),
            )
        row = cur.fetchone()
        if row:
            d = dict(row)
            d["amount"] = float(d["amount"])
            if hasattr(d.get("date"), "isoformat"):
                d["date"] = d["date"].isoformat()
            return d
    return None


# ======================================================================
# UNDO SYSTEM
# ======================================================================

def store_undo_state(user_id: int, action_type: str, entity_type: str, entity_id: int, previous_state: dict | None) -> None:
    """Store the last reversible action for a user. Only keeps the most recent one."""
    import json
    with get_db_cursor() as cur:
        # Delete all previous undo entries for this user (only keep latest)
        cur.execute("DELETE FROM undo_log WHERE user_id = %s", (user_id,))
        cur.execute(
            """
            INSERT INTO undo_log (user_id, action_type, entity_type, entity_id, previous_state)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, action_type, entity_type, entity_id,
             json.dumps(previous_state) if previous_state else None),
        )


def execute_undo(user_id: int) -> str:
    """Execute undo of the last reversible action. Expires after 10 minutes."""
    import json
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, action_type, entity_type, entity_id, previous_state, created_at
            FROM undo_log
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return "Nothing to undo."

        created = row["created_at"]
        if hasattr(created, "timestamp"):
            import time
            age = time.time() - created.timestamp()
        else:
            age = 0
        if age > 600:  # 10 minutes
            cur.execute("DELETE FROM undo_log WHERE id = %s", (row["id"],))
            return "The undo window has expired (10 minutes). Nothing to undo."

        action = row["action_type"]
        entity = row["entity_type"]
        eid = row["entity_id"]
        prev = json.loads(row["previous_state"]) if row["previous_state"] else None

        result_msg = "Nothing to undo."

        if entity == "transaction":
            if action == "log":
                # Undo a log = delete the transaction
                cur.execute(
                    "DELETE FROM transactions WHERE id = %s AND user_id = %s",
                    (eid, user_id),
                )
                if cur.rowcount > 0:
                    result_msg = f"Undone -- removed the last logged expense (Rs {prev['amount']:.0f} under {prev['category']})." if prev else "Undone -- removed the last logged expense."
                else:
                    result_msg = "Could not undo -- the transaction may have already been deleted."
            elif action == "update" and prev:
                # Undo an update = restore previous values
                cur.execute(
                    """
                    UPDATE transactions
                    SET amount = %s, category = %s, note = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (prev.get("amount"), prev.get("category"), prev.get("note", ""), eid, user_id),
                )
                result_msg = f"Undone -- restored transaction to Rs {float(prev['amount']):.0f} under {prev['category']}."
            elif action == "delete" and prev:
                # Undo a delete = re-insert the transaction
                cur.execute(
                    """
                    INSERT INTO transactions (id, user_id, amount, category, note, date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (eid, user_id, prev.get("amount"), prev.get("category"),
                     prev.get("note", ""), prev.get("date")),
                )
                result_msg = f"Undone -- restored deleted expense of Rs {float(prev['amount']):.0f} under {prev['category']}."

        # Remove the used undo entry
        cur.execute("DELETE FROM undo_log WHERE id = %s", (row["id"],))

    return result_msg


def get_undo_status(user_id: int) -> dict:
    """Check if undo is available for this user."""
    import json, time
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT action_type, entity_type, entity_id, previous_state, created_at
            FROM undo_log WHERE user_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"available": False}
        created = row["created_at"]
        age = time.time() - created.timestamp() if hasattr(created, "timestamp") else 0
        if age > 600:
            return {"available": False, "reason": "expired"}
        prev = json.loads(row["previous_state"]) if row["previous_state"] else {}
        return {
            "available": True,
            "action_type": row["action_type"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "description": f"{row['action_type']} {row['entity_type']}",
            "seconds_remaining": max(0, int(600 - age)),
            "previous_amount": float(prev.get("amount", 0)) if prev.get("amount") else None,
            "previous_category": prev.get("category"),
        }


def get_transaction_by_id(user_id: int, transaction_id: int) -> dict | None:
    """Get a single transaction by ID, owned by user_id. Used for undo state capture."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT id, amount, category, note, date, merchant FROM transactions WHERE id = %s AND user_id = %s",
            (transaction_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["amount"] = float(d["amount"])
        if hasattr(d.get("date"), "isoformat"):
            d["date"] = d["date"].isoformat()
        return d


# ======================================================================
# CUSTOM CATEGORIES
# ======================================================================

# System-level default categories
SYSTEM_CATEGORIES = [
    "food", "groceries", "travel", "rent", "bills", "entertainment",
    "shopping", "health", "other", "eating out", "utilities",
    "personal care", "emergency fund", "sip / investments", "miscellaneous",
]


def get_all_categories(user_id: int) -> list[str]:
    """Return system + user custom categories, deduplicated and sorted."""
    user_cats = get_user_categories(user_id)
    all_cats = set(c.lower() for c in SYSTEM_CATEGORIES)
    all_cats.update(c.lower() for c in user_cats)
    return sorted(all_cats)


def get_user_categories(user_id: int) -> list[str]:
    """Get user's custom categories."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT name FROM user_categories WHERE user_id = %s ORDER BY name",
            (user_id,),
        )
        return [r["name"] for r in cur.fetchall()]


def add_user_category(user_id: int, name: str) -> dict:
    """Add a custom category for a user. Case-insensitive duplicates prevented."""
    clean = name.strip().lower()
    if not clean or len(clean) < 2:
        raise ValueError("Category name must be at least 2 characters.")
    if clean in (c.lower() for c in SYSTEM_CATEGORIES):
        raise ValueError(f"'{clean}' is a built-in category.")
    with get_db_cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO user_categories (user_id, name)
                VALUES (%s, %s)
                RETURNING id, name
                """,
                (user_id, clean),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        except Exception:
            raise ValueError(f"Category '{clean}' already exists.")


def remove_user_category(user_id: int, name: str) -> bool:
    """Remove a user's custom category."""
    with get_db_cursor() as cur:
        cur.execute(
            "DELETE FROM user_categories WHERE user_id = %s AND LOWER(name) = LOWER(%s)",
            (user_id, name.strip()),
        )
        return cur.rowcount > 0


# ======================================================================
# TRANSACTION TAGS
# ======================================================================

def add_transaction_tag(user_id: int, transaction_id: int, tag: str) -> dict:
    """Add a tag to a transaction."""
    clean = tag.strip().lower()
    if not clean:
        raise ValueError("Tag cannot be empty.")
    with get_db_cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO transaction_tags (transaction_id, user_id, tag)
                VALUES (%s, %s, %s)
                ON CONFLICT (transaction_id, LOWER(tag)) DO NOTHING
                RETURNING id, transaction_id, tag
                """,
                (transaction_id, user_id, clean),
            )
            row = cur.fetchone()
            return dict(row) if row else {"transaction_id": transaction_id, "tag": clean}
        except Exception:
            return {"transaction_id": transaction_id, "tag": clean}


def remove_transaction_tag(user_id: int, transaction_id: int, tag: str) -> bool:
    """Remove a tag from a transaction."""
    with get_db_cursor() as cur:
        cur.execute(
            "DELETE FROM transaction_tags WHERE user_id = %s AND transaction_id = %s AND LOWER(tag) = LOWER(%s)",
            (user_id, transaction_id, tag.strip()),
        )
        return cur.rowcount > 0


def get_transaction_tags(user_id: int, transaction_id: int) -> list[str]:
    """Get all tags for a transaction."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT tag FROM transaction_tags WHERE user_id = %s AND transaction_id = %s ORDER BY tag",
            (user_id, transaction_id),
        )
        return [r["tag"] for r in cur.fetchall()]


def get_all_user_tags(user_id: int) -> list[str]:
    """Get all unique tags used by a user."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT DISTINCT tag FROM transaction_tags WHERE user_id = %s ORDER BY tag",
            (user_id,),
        )
        return [r["tag"] for r in cur.fetchall()]


# ======================================================================
# SEARCH & FILTER TRANSACTIONS
# ======================================================================

def search_transactions(
    user_id: int,
    text: str | None = None,
    category: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    tag: str | None = None,
    merchant: str | None = None,
    page: int = 1,
    per_page: int = 50,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    """Search and filter transactions with pagination and sorting."""
    conditions = ["t.user_id = %s"]
    params: list = [user_id]

    if text:
        conditions.append("(LOWER(t.note) LIKE %s OR LOWER(t.merchant) LIKE %s)")
        like_text = f"%{text.strip().lower()}%"
        params.extend([like_text, like_text])
    if category:
        conditions.append("t.category = %s")
        params.append(category.lower().strip())
    if amount_min is not None:
        conditions.append("t.amount >= %s")
        params.append(amount_min)
    if amount_max is not None:
        conditions.append("t.amount <= %s")
        params.append(amount_max)
    if start_date:
        conditions.append("DATE(t.date) >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("DATE(t.date) <= %s")
        params.append(end_date)
    if tag:
        conditions.append(
            "EXISTS (SELECT 1 FROM transaction_tags tt WHERE tt.transaction_id = t.id AND LOWER(tt.tag) = LOWER(%s))"
        )
        params.append(tag.strip())
    if merchant:
        conditions.append("LOWER(t.merchant) LIKE %s")
        params.append(f"%{merchant.strip().lower()}%")

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    valid_sort_cols = {
        "date": "t.date",
        "amount": "t.amount",
        "category": "t.category",
        "merchant": "t.merchant",
        "id": "t.id",
    }
    order_col = valid_sort_cols.get(sort_by.lower() if sort_by else "date", "t.date")
    order_dir = "ASC" if sort_order and sort_order.lower() == "asc" else "DESC"

    with get_db_cursor() as cur:
        # Count total
        cur.execute(f"SELECT COUNT(*) as total FROM transactions t WHERE {where}", tuple(params))
        total = cur.fetchone()["total"]

        # Fetch page
        cur.execute(
            f"""
            SELECT t.id, t.date, t.amount, t.category, t.note, t.merchant
            FROM transactions t
            WHERE {where}
            ORDER BY {order_col} {order_dir}, t.id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [per_page, offset]),
        )
        rows = cur.fetchall()
        tx_ids = [r["id"] for r in rows]
        tags_map = {}
        if tx_ids:
            cur.execute(
                "SELECT transaction_id, tag FROM transaction_tags WHERE user_id = %s AND transaction_id = ANY(%s) ORDER BY tag",
                (user_id, tx_ids),
            )
            for tr in cur.fetchall():
                tags_map.setdefault(tr["transaction_id"], []).append(tr["tag"])

        results = []
        for r in rows:
            d = dict(r)
            d["amount"] = float(d["amount"])
            if hasattr(d.get("date"), "isoformat"):
                d["date"] = d["date"].isoformat()
            d["tags"] = tags_map.get(d["id"], [])
            results.append(d)

    return {
        "transactions": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


# ======================================================================
# DATE-RANGE DASHBOARD
# ======================================================================

def get_dashboard_ranged(
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Dashboard data with optional date range filtering.
    If no dates given, defaults to current month."""
    t_overall_start = time.perf_counter()
    is_custom = bool(start_date or end_date)
    if not start_date and not end_date:
        month = current_month()
        start_date = f"{month}-01"
        y, m = map(int, month.split("-"))
        last_day = calendar.monthrange(y, m)[1]
        end_date = f"{month}-{last_day}"
    elif not start_date:
        start_date = "2020-01-01"
    elif not end_date:
        end_date = date.today().isoformat()

    t_cat_start = time.perf_counter()
    with get_db_cursor() as cur:
        # Category spend in range
        cur.execute(
            """
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE user_id = %s AND DATE(date) >= %s AND DATE(date) <= %s
            GROUP BY category
            """,
            (user_id, start_date, end_date),
        )
        spend = {r["category"]: float(r["total"]) for r in cur.fetchall()}
        t_cat_end = time.perf_counter()
        print(f"[DASHBOARD_TIMING] Category spend query: {(t_cat_end - t_cat_start)*1000:.2f}ms", flush=True)

        # Daily spend in range
        t_daily_start = time.perf_counter()
        cur.execute(
            """
            SELECT DATE(date AT TIME ZONE 'UTC') as day, SUM(amount) as total
            FROM transactions
            WHERE user_id = %s AND DATE(date) >= %s AND DATE(date) <= %s
            GROUP BY day ORDER BY day ASC
            """,
            (user_id, start_date, end_date),
        )
        daily = [
            {"day": r["day"].isoformat() if hasattr(r["day"], "isoformat") else str(r["day"]),
             "total": float(r["total"])}
            for r in cur.fetchall()
        ]
        t_daily_end = time.perf_counter()
        print(f"[DASHBOARD_TIMING] Daily spend query: {(t_daily_end - t_daily_start)*1000:.2f}ms", flush=True)

    # Monthly trends (always last 6 months regardless of range)
    t_trends_start = time.perf_counter()
    monthly_trends = get_monthly_totals(user_id, num_months=6)
    t_trends_end = time.perf_counter()
    print(f"[DASHBOARD_TIMING] Monthly trends query: {(t_trends_end - t_trends_start)*1000:.2f}ms", flush=True)

    # Budgets: only meaningful for single-month ranges
    t_budgets_start = time.perf_counter()
    month_str = start_date[:7] if start_date else current_month()
    eff_budgets = get_effective_budgets(user_id, month_str)
    t_budgets_end = time.perf_counter()
    print(f"[DASHBOARD_TIMING] Effective budgets query: {(t_budgets_end - t_budgets_start)*1000:.2f}ms", flush=True)

    # Udhar summary
    t_udhar_start = time.perf_counter()
    udhar = get_udhar_summary(user_id)
    t_udhar_end = time.perf_counter()
    print(f"[DASHBOARD_TIMING] Udhar summary query: {(t_udhar_end - t_udhar_start)*1000:.2f}ms", flush=True)

    # Recent transactions
    t_recent_start = time.perf_counter()
    recent = get_recent_expenses(user_id, limit=10)
    t_recent_end = time.perf_counter()
    print(f"[DASHBOARD_TIMING] Recent transactions query: {(t_recent_end - t_recent_start)*1000:.2f}ms", flush=True)

    all_categories = sorted(set(list(spend.keys()) + list(eff_budgets.keys())))
    categories = []
    total_spent = 0.0
    total_budget = 0.0

    for cat in all_categories:
        spent = spend.get(cat, 0.0)
        eff = eff_budgets.get(cat)
        limit = eff["effective_budget"] if eff else None
        base_limit = eff["base_limit"] if eff else None
        rollover_enabled = eff["rollover_enabled"] if eff else False
        carried = eff["carried_amount"] if eff else 0.0
        total_spent += spent

        entry = {
            "category": cat,
            "spent": round(spent, 2),
            "budget": round(limit, 2) if limit is not None else None,
            "base_budget": round(base_limit, 2) if base_limit is not None else None,
            "rollover_enabled": rollover_enabled,
            "carried_amount": round(carried, 2),
            "percentage": round((spent / limit) * 100, 1) if limit else None,
        }
        if limit is not None:
            total_budget += limit
        categories.append(entry)

    categories.sort(key=lambda x: x["spent"], reverse=True)

    budget_remaining = round(max(0.0, total_budget - total_spent), 2) if total_budget > 0 else 0.0

    total_time_ms = (time.perf_counter() - t_overall_start) * 1000
    print(f"[DASHBOARD_TIMING] Tier 1 total execution time: {total_time_ms:.2f}ms", flush=True)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "is_custom_range": is_custom,
        "total_spent": round(total_spent, 2),
        "total_budget": round(total_budget, 2) if total_budget > 0 else None,
        "budget_remaining": budget_remaining,
        "categories": categories,
        "recent_transactions": recent,
        "daily_spend": daily,
        "monthly_trends": monthly_trends,
        "udhar_net": udhar["net"],
        "udhar_lent": udhar["total_lent"],
        "udhar_borrowed": udhar["total_borrowed"],
        "tier1_time_ms": round(total_time_ms, 2),
    }


def get_dashboard_tier2(user_id: int) -> dict:
    """Tier 2 dashboard computation: health score, projections, potential savings, AI insight card.
    Loaded asynchronously after Tier 1 renders.
    """
    t_start = time.perf_counter()
    health_score = compute_health_score(user_id)
    t_health = time.perf_counter()
    print(f"[DASHBOARD_TIMING] Tier 2: Health score computed in {(t_health - t_start)*1000:.2f}ms", flush=True)

    projections = get_overspending_projections(user_id)
    t_proj = time.perf_counter()
    print(f"[DASHBOARD_TIMING] Tier 2: Overspending projections computed in {(t_proj - t_health)*1000:.2f}ms", flush=True)

    # Discretionary spend potential savings
    month = current_month()
    spend_map = spend_by_category(user_id, month)
    disc_cats = ["eating out", "shopping", "entertainment", "personal care", "miscellaneous", "food"]
    disc_spend = sum(spend_map.get(c, 0.0) for c in disc_cats)
    if disc_spend > 0:
        potential_savings = round(disc_spend * 0.15)
        potential_sub = "15% trim on discretionary"
    else:
        potential_savings = 0
        potential_sub = "Track expenses to unlock"

    raw_insights = get_insights(user_id)
    top_insight = raw_insights[0] if raw_insights else None
    t_ins = time.perf_counter()
    print(f"[DASHBOARD_TIMING] Tier 2: AI insights computed in {(t_ins - t_proj)*1000:.2f}ms", flush=True)
    total_tier2_ms = (t_ins - t_start) * 1000
    print(f"[DASHBOARD_TIMING] Tier 2: Total execution time {total_tier2_ms:.2f}ms", flush=True)

    return {
        "health_score": health_score,
        "projections": projections,
        "potential_savings": potential_savings,
        "potential_sub": potential_sub,
        "insights": raw_insights,
        "top_insight": top_insight,
        "tier2_time_ms": round(total_tier2_ms, 2),
    }


# ======================================================================
# CLEAR & DELETE DATA
# ======================================================================

def clear_transactions(user_id: int, start_date: str | None = None, end_date: str | None = None) -> int:
    """Clear transactions for a user. Optional date range."""
    with get_db_cursor() as cur:
        if start_date and end_date:
            cur.execute(
                "DELETE FROM transactions WHERE user_id = %s AND DATE(date) >= %s AND DATE(date) <= %s",
                (user_id, start_date, end_date),
            )
        else:
            cur.execute("DELETE FROM transactions WHERE user_id = %s", (user_id,))
        return cur.rowcount


def clear_udhar(user_id: int) -> int:
    """Clear all udhar entries for a user."""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM udhar_entries WHERE user_id = %s", (user_id,))
        return cur.rowcount


def clear_everything(user_id: int) -> dict:
    """Clear all user data except the account itself."""
    from app.storage import delete_from_storage
    counts = {}
    with get_db_cursor() as cur:
        # Get receipt paths to delete from storage
        cur.execute("SELECT path FROM receipts WHERE user_id = %s", (user_id,))
        receipt_paths = [r["path"] for r in cur.fetchall()]
        cur.execute("DELETE FROM receipts WHERE user_id = %s", (user_id,))
        counts["receipts"] = cur.rowcount

        cur.execute("DELETE FROM push_subscriptions WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM sent_notifications WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM undo_log WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM transaction_tags WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM merchant_aliases WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM user_categories WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM budget_rollovers WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM recurring_expenses WHERE user_id = %s", (user_id,))
        counts["recurring"] = cur.rowcount
        cur.execute("DELETE FROM chat_messages WHERE user_id = %s", (user_id,))
        counts["chats"] = cur.rowcount
        cur.execute("DELETE FROM savings_goals WHERE user_id = %s", (user_id,))
        counts["goals"] = cur.rowcount
        cur.execute("DELETE FROM income_entries WHERE user_id = %s", (user_id,))
        counts["income"] = cur.rowcount
        cur.execute("DELETE FROM udhar_entries WHERE user_id = %s", (user_id,))
        counts["udhar"] = cur.rowcount
        cur.execute("DELETE FROM transactions WHERE user_id = %s", (user_id,))
        counts["transactions"] = cur.rowcount
        cur.execute("DELETE FROM budgets WHERE user_id = %s", (user_id,))
        counts["budgets"] = cur.rowcount
        cur.execute("DELETE FROM user_profile WHERE user_id = %s", (user_id,))

    if receipt_paths:
        for p in receipt_paths:
            try:
                delete_from_storage(p)
            except Exception:
                pass

    return counts


def delete_account(user_id: int) -> bool:
    """Delete the entire user account and all associated files and data."""
    from app.storage import delete_from_storage
    receipt_paths = []
    with get_db_cursor() as cur:
        cur.execute("SELECT path FROM receipts WHERE user_id = %s", (user_id,))
        receipt_paths = [r["path"] for r in cur.fetchall()]
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        deleted = cur.rowcount > 0

    if deleted and receipt_paths:
        for p in receipt_paths:
            try:
                delete_from_storage(p)
            except Exception:
                pass

    return deleted


def export_all_data_json(user_id: int) -> dict:
    """Export all user data as a structured JSON dict for download."""
    import json
    with get_db_cursor() as cur:
        cur.execute("SELECT id, email, username, avatar_id, created_at FROM users WHERE id = %s", (user_id,))
        user_row = cur.fetchone()
        user_info = dict(user_row) if user_row else {}
        if hasattr(user_info.get("created_at"), "isoformat"):
            user_info["created_at"] = user_info["created_at"].isoformat()

    transactions = get_transactions(user_id=user_id)
    income = get_income_entries(user_id=user_id)
    budgets = get_budgets(user_id=user_id)
    goals = get_goals(user_id=user_id)
    udhar = get_udhar_summary(user_id=user_id)
    profile = get_user_profile(user_id=user_id)
    recurring = get_recurring_expenses(user_id=user_id)
    categories = get_user_categories(user_id=user_id)
    receipts_list = get_receipts(user_id=user_id)

    return {
        "user": user_info,
        "transactions": transactions,
        "income_entries": income,
        "budgets": budgets,
        "savings_goals": goals,
        "udhar": udhar,
        "profile": profile,
        "recurring_expenses": recurring,
        "custom_categories": categories,
        "receipts": receipts_list,
        "exported_at": datetime.now().isoformat(),
    }


# ======================================================================
# Tier 3 Features: Receipts, Import Caching, Udhar Nudge,
# Cash-Flow Calendar, Overspending Projections, Web Push
# ======================================================================

def add_receipt(user_id: int, transaction_id: Optional[int], path: str, mime: str, size: int) -> dict:
    """Record receipt metadata in Postgres."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO receipts (user_id, transaction_id, path, mime, size)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, user_id, transaction_id, path, mime, size, created_at
            """,
            (user_id, transaction_id, path, mime, size),
        )
        row = cur.fetchone()
        d = dict(row)
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        return d


def get_receipts(user_id: int) -> list[dict]:
    """List all receipts owned by user_id, joined with transaction info."""
    from app.storage import get_signed_url
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.user_id, r.transaction_id, r.path, r.mime, r.size, r.created_at,
                   t.amount, t.category, t.note, t.merchant, t.date as transaction_date
            FROM receipts r
            LEFT JOIN transactions t ON r.transaction_id = t.id
            WHERE r.user_id = %s
            ORDER BY r.created_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if hasattr(d.get("created_at"), "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            if hasattr(d.get("transaction_date"), "isoformat"):
                d["transaction_date"] = d["transaction_date"].isoformat()
            if d.get("amount") is not None:
                d["amount"] = float(d["amount"])
            d["signed_url"] = get_signed_url(d["path"])
            result.append(d)
        return result


def get_receipt_by_id(user_id: int, receipt_id: int) -> Optional[dict]:
    """Get a single receipt ensuring user ownership."""
    from app.storage import get_signed_url
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id, transaction_id, path, mime, size, created_at
            FROM receipts
            WHERE id = %s AND user_id = %s
            """,
            (receipt_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        d["signed_url"] = get_signed_url(d["path"])
        return d


def delete_receipt(user_id: int, receipt_id: int) -> Optional[str]:
    """Delete receipt record from DB. Returns storage path so caller deletes storage file."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT path FROM receipts WHERE id = %s AND user_id = %s",
            (receipt_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        path = row["path"]
        cur.execute("DELETE FROM receipts WHERE id = %s", (receipt_id,))
        return path


def get_transaction_receipts(user_id: int, transaction_id: int) -> list[dict]:
    """List receipts attached to a specific transaction."""
    from app.storage import get_signed_url
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id, transaction_id, path, mime, size, created_at
            FROM receipts
            WHERE transaction_id = %s AND user_id = %s
            ORDER BY created_at DESC
            """,
            (transaction_id, user_id),
        )
        rows = cur.fetchall()
        res = []
        for r in rows:
            d = dict(r)
            if hasattr(d.get("created_at"), "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            d["signed_url"] = get_signed_url(d["path"])
            res.append(d)
        return res


# ---------- Merchant Category Cache & Past Categorizations ----------

def get_cached_merchant_category(normalized_merchant: str) -> Optional[str]:
    """Get category for merchant from global cache."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT category FROM merchant_category_cache WHERE LOWER(normalized_merchant) = %s",
            (normalized_merchant.lower().strip(),),
        )
        row = cur.fetchone()
        return row["category"] if row else None


def set_cached_merchant_category(normalized_merchant: str, category: str) -> None:
    """Store category in merchant_category_cache."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO merchant_category_cache (normalized_merchant, category)
            VALUES (%s, %s)
            ON CONFLICT (normalized_merchant) DO UPDATE SET category = EXCLUDED.category
            """,
            (normalized_merchant.lower().strip(), category.strip()),
        )


def get_past_merchant_category(user_id: int, normalized_merchant: str) -> Optional[str]:
    """Check user's past transactions for a matching merchant or note."""
    norm = normalized_merchant.lower().strip()
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT category FROM transactions
            WHERE user_id = %s AND (
                LOWER(COALESCE(merchant, '')) = %s
                OR LOWER(COALESCE(note, '')) LIKE %s
            )
            ORDER BY date DESC
            LIMIT 1
            """,
            (user_id, norm, f"%{norm}%"),
        )
        row = cur.fetchone()
        return row["category"] if row else None


# ---------- Udhar Reminder Nudge ----------

def get_udhar_reminder_data(user_id: int, person_key: str) -> dict:
    """Generate a polite, deterministic reminder message for an udhar entry.
    No LLM call. No emojis anywhere."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT person_name, kind, amount, due_date
            FROM udhar_entries
            WHERE user_id = %s AND person_key = %s
            ORDER BY entry_date DESC
            """,
            (user_id, person_key.lower().strip()),
        )
        rows = cur.fetchall()

    if not rows:
        raise ValueError(f"No udhar records found for '{person_key}'.")

    person_name = rows[0]["person_name"]
    lent_total = sum(float(r["amount"]) for r in rows if r["kind"] == "lent")
    borrowed_total = sum(float(r["amount"]) for r in rows if r["kind"] == "borrowed")
    net_balance = lent_total - borrowed_total

    # Find earliest or latest due date for lent entries
    due_dates = [r["due_date"] for r in rows if r["kind"] == "lent" and r["due_date"]]
    due_date_str = ""
    if due_dates:
        latest_due = max(due_dates)
        if hasattr(latest_due, "strftime"):
            due_date_str = latest_due.strftime("%d %b %Y")
        else:
            due_date_str = str(latest_due)

    if net_balance <= 0:
        msg = f"Hi {person_name}, according to our records, all pending dues are settled. Thank you."
    elif due_date_str:
        msg = f"Hi {person_name}, gentle reminder regarding the pending amount of Rs {net_balance:.0f} which was due on {due_date_str}. Please let me know once settled. Thank you."
    else:
        msg = f"Hi {person_name}, gentle reminder regarding the pending balance of Rs {net_balance:.0f}. Please let me know once settled. Thank you."

    import urllib.parse
    wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"

    return {
        "person_name": person_name,
        "person_key": person_key,
        "net_balance": net_balance,
        "due_date": due_date_str,
        "message": msg,
        "wa_url": wa_url,
    }


# ---------- Cash-Flow Calendar ----------

def get_cashflow_calendar(user_id: int, month_str: Optional[str] = None) -> dict:
    """Generate calendar events and projected daily cash flow for a given month (YYYY-MM).
    Shows recurring bills, udhar due dates, and expected income.
    Works seamlessly on mobile and desktop."""
    if not month_str:
        month_str = current_month()

    try:
        year, month = map(int, month_str.split("-"))
    except ValueError:
        month_str = current_month()
        year, month = map(int, month_str.split("-"))

    num_days = calendar.monthrange(year, month)[1]

    # Initialize daily schedule
    days_data = {
        d: {
            "day": d,
            "date": f"{year:04d}-{month:02d}-{d:02d}",
            "bills": [],
            "udhar": [],
            "income": [],
            "net_flow": 0.0,
            "projected_balance": 0.0,
        }
        for d in range(1, num_days + 1)
    }

    total_bills = 0.0
    total_receivable = 0.0
    total_payable = 0.0
    total_income = 0.0

    # 1. Recurring bills
    recurring = get_recurring_expenses(user_id)
    for r in recurring:
        if not r.get("active"):
            continue
        amt = float(r["amount"])
        freq = r.get("frequency", "monthly")
        due = r.get("next_due_date")
        if not due:
            continue
        if isinstance(due, str):
            try:
                due_d = datetime.strptime(due[:10], "%Y-%m-%d").date()
            except Exception:
                due_d = date.today()
        else:
            due_d = due

        # Project occurrences in this month
        if freq == "monthly":
            day = min(due_d.day, num_days)
            item = {
                "id": r["id"],
                "name": r["name"],
                "amount": amt,
                "category": r["category"],
                "type": "bill",
            }
            days_data[day]["bills"].append(item)
            days_data[day]["net_flow"] -= amt
            total_bills += amt
        elif freq == "weekly":
            target_weekday = due_d.weekday()
            for d in range(1, num_days + 1):
                cur_d = date(year, month, d)
                if cur_d.weekday() == target_weekday:
                    item = {
                        "id": r["id"],
                        "name": r["name"],
                        "amount": amt,
                        "category": r["category"],
                        "type": "bill",
                    }
                    days_data[d]["bills"].append(item)
                    days_data[d]["net_flow"] -= amt
                    total_bills += amt
        elif freq == "yearly":
            if due_d.month == month:
                day = min(due_d.day, num_days)
                item = {
                    "id": r["id"],
                    "name": r["name"],
                    "amount": amt,
                    "category": r["category"],
                    "type": "bill",
                }
                days_data[day]["bills"].append(item)
                days_data[day]["net_flow"] -= amt
                total_bills += amt

    # 2. Udhar entries with due dates in this month
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, person_name, kind, amount, note, due_date
            FROM udhar_entries
            WHERE user_id = %s
              AND due_date IS NOT NULL
              AND TO_CHAR(due_date, 'YYYY-MM') = %s
            """,
            (user_id, month_str),
        )
        udhar_rows = cur.fetchall()

    for u in udhar_rows:
        amt = float(u["amount"])
        due_d = u["due_date"]
        if hasattr(due_d, "day"):
            day = due_d.day
        else:
            day = int(str(due_d)[8:10])

        if 1 <= day <= num_days:
            item = {
                "id": u["id"],
                "person_name": u["person_name"],
                "amount": amt,
                "kind": u["kind"],
                "note": u["note"],
                "type": "udhar",
            }
            days_data[day]["udhar"].append(item)
            if u["kind"] == "lent":
                days_data[day]["net_flow"] += amt
                total_receivable += amt
            else:
                days_data[day]["net_flow"] -= amt
                total_payable += amt

    # 3. Expected Income entries in this month
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, source, amount, date
            FROM income_entries
            WHERE user_id = %s AND TO_CHAR(date, 'YYYY-MM') = %s
            """,
            (user_id, month_str),
        )
        inc_rows = cur.fetchall()

    for inc in inc_rows:
        amt = float(inc["amount"])
        dt = inc["date"]
        day = dt.day if hasattr(dt, "day") else int(str(dt)[8:10])
        if 1 <= day <= num_days:
            item = {
                "id": inc["id"],
                "source": inc["source"],
                "amount": amt,
                "type": "income",
            }
            days_data[day]["income"].append(item)
            days_data[day]["net_flow"] += amt
            total_income += amt

    # 4. Running projected balance line
    profile = get_user_profile(user_id)
    running_balance = float(profile.get("current_savings") or 0.0)

    for d in range(1, num_days + 1):
        running_balance += days_data[d]["net_flow"]
        days_data[d]["projected_balance"] = round(running_balance, 2)

    return {
        "month": month_str,
        "year": year,
        "days_in_month": num_days,
        "days": days_data,
        "summary": {
            "total_bills": round(total_bills, 2),
            "total_receivable": round(total_receivable, 2),
            "total_payable": round(total_payable, 2),
            "total_income": round(total_income, 2),
            "start_balance": round(float(profile.get("current_savings") or 0.0), 2),
            "end_balance": round(running_balance, 2),
        },
    }


# ---------- Overspending Projections ----------

def get_overspending_projections(user_id: int) -> list[dict]:
    """Calculate projected month-end spend per category.
    Formula: projected = spent / days_elapsed * days_in_month
    Only shows warning when projected > budget AND days_elapsed >= 7."""
    today = date.today()
    days_elapsed = max(1, today.day)
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    # Condition: at least 7 days of data must exist
    if days_elapsed < 7:
        return []

    budgets = get_budgets(user_id)
    if not budgets:
        return []

    spend_map = spend_by_category(user_id, current_month())
    alerts = []

    for b in budgets:
        cat = b["category"]
        limit = float(b["monthly_limit"])
        spent = float(spend_map.get(cat, 0.0))

        if limit <= 0:
            continue

        projected = (spent / days_elapsed) * days_in_month
        if projected > limit:
            excess = round(projected - limit)
            alerts.append({
                "category": cat,
                "limit": limit,
                "spent": spent,
                "projected": round(projected),
                "excess": excess,
                "days_elapsed": days_elapsed,
                "days_in_month": days_in_month,
                "message": f"At this pace you will exceed {cat} by about Rs {excess}.",
            })

    return alerts


def get_overspending_projections_text(user_id: int) -> str:
    """Formatted deterministic text for agent tool."""
    today = date.today()
    days_elapsed = max(1, today.day)

    if days_elapsed < 7:
        return f"Only {days_elapsed} days have elapsed this month. Overspending projections require at least 7 days of data."

    alerts = get_overspending_projections(user_id)
    if not alerts:
        return "You are currently within your budget limits for all categories based on current spending pace."

    lines = ["Budget Pace Alerts:"]
    for a in alerts:
        lines.append(f"- {a['message']} (Limit: Rs {a['limit']:.0f}, Spent: Rs {a['spent']:.0f}, Projected: Rs {a['projected']:.0f})")
    return "\n".join(lines)


# ---------- Push Subscriptions & Sent Notifications ----------

def save_push_subscription(
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    preferences: Optional[dict] = None,
) -> dict:
    """Save or update browser push subscription."""
    import json
    prefs_json = json.dumps(preferences or {
        "budget_alerts": True,
        "bill_reminders": True,
        "weekly_recap": True,
    })
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, preferences)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (endpoint) DO UPDATE
            SET user_id = EXCLUDED.user_id,
                p256dh = EXCLUDED.p256dh,
                auth = EXCLUDED.auth,
                preferences = EXCLUDED.preferences
            RETURNING id, user_id, endpoint, preferences, created_at
            """,
            (user_id, endpoint, p256dh, auth, prefs_json),
        )
        row = cur.fetchone()
        d = dict(row)
        if hasattr(d.get("created_at"), "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        return d


def get_user_push_subscriptions(user_id: int) -> list[dict]:
    """Get all push subscriptions for a user."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id, endpoint, p256dh, auth, preferences, created_at
            FROM push_subscriptions
            WHERE user_id = %s
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if hasattr(d.get("created_at"), "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            result.append(d)
        return result


def remove_push_subscription(endpoint: str) -> bool:
    """Remove a subscription by endpoint (e.g. on 404/410 gone)."""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (endpoint,))
        return cur.rowcount > 0


def check_and_record_notification(user_id: int, notification_type: str, cycle: str) -> bool:
    """Check if notification has already been sent for this cycle.
    If not sent yet, records it and returns True (proceed with sending).
    If already sent, returns False (suppress duplicate)."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO sent_notifications (user_id, notification_type, cycle)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, notification_type, cycle) DO NOTHING
            RETURNING id
            """,
            (user_id, notification_type, cycle),
        )
        row = cur.fetchone()
        return row is not None


# ---------- User Password & Account Management ----------

def update_user_password(user_id: int, password_hash: str) -> bool:
    """Update user's password hash and clear force_password_reset flag."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET password_hash = %s, force_password_reset = FALSE
            WHERE id = %s
            """,
            (password_hash, user_id),
        )
        return cur.rowcount > 0


def update_user_last_login(user_id: int) -> None:
    """Record the user's latest login timestamp."""
    try:
        with get_db_cursor() as cur:
            cur.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user_id,))
    except Exception:
        pass


def set_user_suspended(user_id: int, suspended: bool) -> bool:
    """Suspend or unsuspend a user account."""
    with get_db_cursor() as cur:
        if suspended:
            cur.execute("UPDATE users SET suspended_at = NOW() WHERE id = %s", (user_id,))
        else:
            cur.execute("UPDATE users SET suspended_at = NULL WHERE id = %s", (user_id,))
        return cur.rowcount > 0


def set_user_force_password_reset(user_id: int, force: bool = True) -> bool:
    """Set or clear the force_password_reset flag on a user account."""
    with get_db_cursor() as cur:
        cur.execute("UPDATE users SET force_password_reset = %s WHERE id = %s", (force, user_id))
        return cur.rowcount > 0


# ---------- Server Errors Logging ----------

def log_server_error(route: str, message: str) -> None:
    """Log an unhandled server error (never contains user data)."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "INSERT INTO errors (route, message) VALUES (%s, %s)",
                (route[:500], message[:2000]),
            )
    except Exception:
        pass


def get_recent_server_errors(limit: int = 10) -> list[dict]:
    """Fetch recent server errors (up to limit)."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT id, route, message, created_at FROM errors ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if hasattr(d.get("created_at"), "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            result.append(d)
        return result


# ---------- App Settings (Live Config with 30s TTL Cache) ----------

_app_settings_cache: dict[str, str] = {}
_app_settings_cache_time: float = 0.0


def get_app_settings(force_refresh: bool = False) -> dict[str, str]:
    """Fetch all live app settings with a 30-second in-memory cache."""
    global _app_settings_cache, _app_settings_cache_time
    now = time.time()
    if not force_refresh and _app_settings_cache and (now - _app_settings_cache_time < 30.0):
        return dict(_app_settings_cache)

    defaults = {
        "daily_message_cap": "100",
        "maintenance_mode": "false",
        "push_notifications_enabled": "true",
        "csv_import_enabled": "true",
        "receipt_upload_enabled": "true",
    }
    with get_db_cursor() as cur:
        cur.execute("SELECT key, value FROM app_settings")
        rows = cur.fetchall()
        data = {r["key"]: r["value"] for r in rows}
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
        _app_settings_cache = data
        _app_settings_cache_time = now
        return dict(data)


def set_app_setting(key: str, value: str) -> None:
    """Upsert an app setting and update cache."""
    global _app_settings_cache, _app_settings_cache_time
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW()
            """,
            (key, str(value)),
        )
    _app_settings_cache[key] = str(value)
    _app_settings_cache_time = time.time()


def get_app_setting(key: str, default: str = "") -> str:
    """Helper to fetch a single live setting."""
    s = get_app_settings()
    return s.get(key, default)


def get_user_today_message_count(user_id: int) -> int:
    """Count user messages sent today for daily message cap."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM chat_messages
            WHERE user_id = %s
              AND role = 'user'
              AND created_at >= CURRENT_DATE
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return row["cnt"] if row else 0


# ---------- Admin Panel Data Access ----------

def get_admin_dashboard_stats() -> dict:
    """Aggregate statistics for admin dashboard overview."""
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM users")
        total_users = cur.fetchone()["count"]

        cur.execute("""
            SELECT COUNT(*) AS count FROM users
            WHERE (last_login_at >= NOW() - INTERVAL '7 days')
               OR (last_login_at IS NULL AND created_at >= NOW() - INTERVAL '7 days')
        """)
        active_7d = cur.fetchone()["count"]

        cur.execute("""
            SELECT COUNT(*) AS count FROM users
            WHERE (last_login_at >= NOW() - INTERVAL '30 days')
               OR (last_login_at IS NULL AND created_at >= NOW() - INTERVAL '30 days')
        """)
        active_30d = cur.fetchone()["count"]

        cur.execute("SELECT COUNT(*) AS count FROM transactions")
        total_tx = cur.fetchone()["count"]

        cur.execute("SELECT COUNT(*) AS count FROM udhar_entries")
        total_udhar = cur.fetchone()["count"]

        cur.execute("SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS total_bytes FROM receipts")
        rec_row = cur.fetchone()
        total_receipts = rec_row["count"]
        total_storage_bytes = int(rec_row["total_bytes"])

        # 30-day registration trend
        cur.execute("""
            SELECT d::date AS date, COALESCE(COUNT(u.id), 0) AS count
            FROM generate_series(CURRENT_DATE - INTERVAL '29 days', CURRENT_DATE, '1 day'::interval) d
            LEFT JOIN users u ON u.created_at::date = d::date
            GROUP BY d::date
            ORDER BY d::date ASC
        """)
        trend_rows = cur.fetchall()
        reg_trend = [{"date": str(r["date"]), "count": int(r["count"])} for r in trend_rows]

    return {
        "total_users": total_users,
        "active_users_7d": active_7d,
        "active_users_30d": active_30d,
        "total_transactions": total_tx,
        "total_udhar": total_udhar,
        "total_receipts": total_receipts,
        "total_storage_bytes": total_storage_bytes,
        "registration_trend": reg_trend,
    }


def get_admin_users(
    search: str = "",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Paginated, searchable, sortable users list for admin."""
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    allowed_sorts = {
        "created_at": "u.created_at",
        "last_login": "u.last_login_at",
        "transactions": "tx_count",
        "username": "u.username",
        "email": "u.email",
    }
    sort_column = allowed_sorts.get(sort_by, "u.created_at")
    order_dir = "ASC" if str(sort_order).lower() == "asc" else "DESC"

    where_clause = ""
    params: list[Any] = []
    if search.strip():
        s = f"%{search.strip().lower()}%"
        where_clause = "WHERE LOWER(u.email) LIKE %s OR LOWER(COALESCE(u.username, '')) LIKE %s"
        params.extend([s, s])

    with get_db_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM users u {where_clause}", tuple(params))
        total = cur.fetchone()["total"]

        query = f"""
            SELECT
                u.id,
                u.email,
                u.username,
                u.created_at,
                u.last_login_at,
                u.suspended_at,
                u.force_password_reset,
                (SELECT COUNT(*) FROM transactions WHERE user_id = u.id) AS tx_count,
                (SELECT COUNT(*) FROM udhar_entries WHERE user_id = u.id) AS udhar_count
            FROM users u
            {where_clause}
            ORDER BY {sort_column} {order_dir} NULLS LAST
            LIMIT %s OFFSET %s
        """
        cur.execute(query, tuple(params + [page_size, offset]))
        rows = cur.fetchall()

        items = []
        for r in rows:
            raw_id = str(r["id"])
            masked_id = f"...{raw_id[-6:]}" if len(raw_id) > 6 else f"...{raw_id}"
            items.append({
                "id": r["id"],
                "masked_id": masked_id,
                "username": r["username"] or "",
                "email": r["email"],
                "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                "last_login": r["last_login_at"].isoformat() if hasattr(r.get("last_login_at"), "isoformat") else (str(r["last_login_at"]) if r.get("last_login_at") else None),
                "tx_count": int(r["tx_count"]),
                "udhar_count": int(r["udhar_count"]),
                "status": "Suspended" if r.get("suspended_at") else "Active",
                "suspended_at": r["suspended_at"].isoformat() if hasattr(r.get("suspended_at"), "isoformat") else (str(r["suspended_at"]) if r.get("suspended_at") else None),
                "force_password_reset": bool(r.get("force_password_reset")),
            })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "users": items,
    }


def get_admin_user_detail(user_id: int) -> dict | None:
    """Fetch user detail for admin view (no raw notes or chat messages for privacy)."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT id, email, username, created_at, last_login_at, suspended_at, force_password_reset
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        u = cur.fetchone()
        if not u:
            return None
        user_data = dict(u)
        for k in ("created_at", "last_login_at", "suspended_at"):
            if hasattr(user_data.get(k), "isoformat"):
                user_data[k] = user_data[k].isoformat()

        # Budgets
        cur.execute(
            "SELECT category, monthly_limit, rollover_enabled FROM budgets WHERE user_id = %s ORDER BY category",
            (user_id,),
        )
        budgets = [dict(b) for b in cur.fetchall()]
        for b in budgets:
            b["monthly_limit"] = float(b["monthly_limit"])

        # Recent transactions: amounts and categories only, NO notes or raw_messages for privacy
        cur.execute(
            """
            SELECT id, date, amount, category, merchant
            FROM transactions
            WHERE user_id = %s
            ORDER BY date DESC
            LIMIT 25
            """,
            (user_id,),
        )
        tx_rows = cur.fetchall()
        txs = []
        for t in tx_rows:
            d = dict(t)
            d["amount"] = float(d["amount"])
            if hasattr(d.get("date"), "isoformat"):
                d["date"] = d["date"].isoformat()
            txs.append(d)

        # Storage used
        cur.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS total_bytes FROM receipts WHERE user_id = %s",
            (user_id,),
        )
        rec = cur.fetchone()
        storage_info = {
            "receipt_count": rec["count"],
            "total_bytes": int(rec["total_bytes"]),
        }

    # Udhar summary
    udhar = get_udhar_summary(user_id=user_id)

    return {
        "user": user_data,
        "budgets": budgets,
        "recent_transactions": txs,
        "udhar_summary": udhar,
        "storage": storage_info,
    }


def get_admin_llm_usage() -> dict:
    """30-day message counts (total and per user, no content) and top 5 users."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT d::date AS date,
                   COUNT(m.id) AS total_messages,
                   COUNT(DISTINCT m.user_id) AS active_users
            FROM generate_series(CURRENT_DATE - INTERVAL '29 days', CURRENT_DATE, '1 day'::interval) d
            LEFT JOIN chat_messages m ON m.created_at::date = d::date AND m.role = 'user'
            GROUP BY d::date
            ORDER BY d::date ASC
        """)
        daily_rows = cur.fetchall()
        daily_usage = [
            {
                "date": str(r["date"]),
                "total_messages": int(r["total_messages"]),
                "active_users": int(r["active_users"]),
            }
            for r in daily_rows
        ]

        cur.execute("""
            SELECT user_id, COUNT(*) AS message_count
            FROM chat_messages
            WHERE role = 'user'
              AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY user_id
            ORDER BY message_count DESC
            LIMIT 5
        """)
        top_rows = cur.fetchall()
        top_users = []
        for r in top_rows:
            uid = str(r["user_id"])
            masked = f"...{uid[-6:]}" if len(uid) > 6 else f"...{uid}"
            top_users.append({
                "masked_user_id": masked,
                "message_count": int(r["message_count"]),
            })

    return {
        "daily_usage": daily_usage,
        "top_users": top_users,
    }


ADMIN_EXPLORER_TABLES = [
    "users",
    "transactions",
    "budgets",
    "udhar_entries",
    "recurring_expenses",
    "savings_goals",
    "receipts",
]


def get_admin_table_overview() -> list[dict]:
    """Return row counts for all DB explorer tables."""
    overview = []
    with get_db_cursor() as cur:
        for tbl in ADMIN_EXPLORER_TABLES:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM {tbl}")
            cnt = cur.fetchone()["cnt"]
            overview.append({"table": tbl, "row_count": cnt})
    return overview


def get_admin_table_rows(
    table_name: str,
    search: str = "",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Paginated, searchable rows for a selected database table (read-only)."""
    if table_name not in ADMIN_EXPLORER_TABLES:
        raise ValueError(f"Table '{table_name}' is not accessible in database explorer")

    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        cols_info = cur.fetchall()
        columns = [c["column_name"] for c in cols_info]
        text_columns = [
            c["column_name"]
            for c in cols_info
            if c["data_type"] in ("character varying", "text", "character")
        ]

        where_sql = ""
        params: list[Any] = []
        if search.strip() and text_columns:
            s = f"%{search.strip().lower()}%"
            clauses = [f"LOWER({tc}) LIKE %s" for tc in text_columns]
            where_sql = "WHERE " + " OR ".join(clauses)
            params = [s] * len(text_columns)

        cur.execute(f"SELECT COUNT(*) AS cnt FROM {table_name} {where_sql}", tuple(params))
        total = cur.fetchone()["cnt"]

        order_col = "id" if "id" in columns else columns[0]
        cur.execute(
            f"SELECT * FROM {table_name} {where_sql} ORDER BY {order_col} DESC LIMIT %s OFFSET %s",
            tuple(params + [page_size, offset]),
        )
        rows = cur.fetchall()
        clean_rows = []
        for r in rows:
            row_dict = {}
            for k, v in dict(r).items():
                if k == "password_hash":
                    row_dict[k] = "[REDACTED_BCRYPT_HASH]"
                elif hasattr(v, "isoformat"):
                    row_dict[k] = v.isoformat()
                elif isinstance(v, (int, float, bool, str)) or v is None:
                    row_dict[k] = v
                else:
                    row_dict[k] = str(v)
            clean_rows.append(row_dict)

    return {
        "table": table_name,
        "total": total,
        "page": page,
        "page_size": page_size,
        "columns": columns,
        "rows": clean_rows,
    }


