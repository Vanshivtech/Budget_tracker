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
import calendar
import io
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
from psycopg2.extras import RealDictCursor

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
) -> dict:
    """Insert a new transaction scoped to user_id."""
    cat = category.lower().strip()
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO transactions (user_id, amount, category, note, raw_message)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, user_id, date, amount, category, note
            """,
            (user_id, amount, cat, note.strip(), raw_message),
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

        cur.execute(
            """
            UPDATE transactions
            SET amount = %s, category = %s, note = %s
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (new_amount, new_category, new_note, transaction_id, user_id),
        )
        updated = cur.fetchone()
        if not updated:
            return None

        d = dict(updated)
        if hasattr(d.get("date"), "isoformat"):
            d["date"] = d["date"].isoformat()
        if "amount" in d and d["amount"] is not None:
            d["amount"] = float(d["amount"])
        return d


def delete_expense(user_id: int, transaction_id: int) -> bool:
    """Delete a transaction owned by user_id. Returns True if deleted."""
    with get_db_cursor() as cur:
        cur.execute(
            "DELETE FROM transactions WHERE id = %s AND user_id = %s",
            (transaction_id, user_id),
        )
        return cur.rowcount > 0


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


def set_budget(user_id: int, category: str, monthly_limit: float) -> None:
    """Upsert a budget row for user_id."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO budgets (user_id, category, monthly_limit)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, category)
            DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit
            """,
            (user_id, category.lower().strip(), monthly_limit),
        )


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
            for item in to_record:
                cur.execute(
                    """
                    INSERT INTO budget_rollovers (user_id, category, month, carried_amount)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, category, month)
                    DO UPDATE SET carried_amount = EXCLUDED.carried_amount
                    """,
                    item,
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
) -> dict:
    """Add a new udhar (lent or borrowed) entry. Never counted in expenses."""
    person_key = person_name.strip().lower()
    due_dt = None
    if due_date:
        try:
            due_dt = datetime.fromisoformat(due_date)
        except ValueError:
            due_dt = None

    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO udhar_entries (user_id, person_name, person_key, kind, amount, note, due_date, is_split, transaction_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, person_name, kind, amount, note, entry_date, due_date, is_split, transaction_id
            """,
            (user_id, person_name.strip(), person_key, kind, amount, note.strip(), due_dt, is_split, transaction_id),
        )
        row = cur.fetchone()
        d = dict(row)
        for f in ("entry_date", "due_date"):
            if d.get(f) and hasattr(d[f], "isoformat"):
                d[f] = d[f].isoformat()
        d["amount"] = float(d["amount"])
        d["is_split"] = bool(d.get("is_split", False))
        return d


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
            updates.append("updated_at = NOW()")
            params.append(user_id)
            cur.execute(
                f"UPDATE user_profile SET {', '.join(updates)} WHERE user_id = %s",
                tuple(params),
            )
        else:
            cur.execute(
                """
                INSERT INTO user_profile (user_id, current_savings, risk_comfort)
                VALUES (%s, %s, %s)
                """,
                (user_id, current_savings, risk_comfort),
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
