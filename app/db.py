"""
Database storage layer powered by Supabase Postgres.

Tables:
    users         — id (SERIAL PK), email (unique), password_hash, created_at
    transactions  — id (SERIAL PK), user_id (FK), date, amount, category, note, raw_message
    budgets       — user_id (FK), category, monthly_limit (PK: user_id, category)

All queries are strictly scoped by user_id. Connection pooling via psycopg2.
"""
from datetime import datetime, date
from contextlib import contextmanager

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

            CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date DESC);
            CREATE INDEX IF NOT EXISTS idx_budgets_user ON budgets(user_id);
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


def get_summary(user_id: int) -> dict:
    """
    Build the full summary payload for GET /api/summary.
    Returns categories sorted by spend, total spent/budget, and recent transactions.
    """
    month = current_month()
    spend = spend_by_category(user_id, month)
    budgets = get_budgets(user_id)
    recent = get_recent_expenses(user_id, limit=10)

    # Merge all categories from both spend and budgets
    all_categories = sorted(set(list(spend.keys()) + list(budgets.keys())))

    categories = []
    total_spent = 0.0
    total_budget = 0.0

    for cat in all_categories:
        spent = spend.get(cat, 0.0)
        limit = budgets.get(cat)
        total_spent += spent

        entry = {
            "category": cat,
            "spent": round(spent, 2),
            "budget": round(limit, 2) if limit is not None else None,
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
