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


def get_dashboard(user_id: int) -> dict:
    """
    Build the full dashboard payload for GET /api/dashboard.
    Includes 6-month trends, daily spend for current month, category breakdown,
    budget vs actual, and udhar totals.
    """
    month = current_month()
    spend = spend_by_category(user_id, month)
    budgets = get_budgets(user_id)
    daily = get_daily_spend(user_id, month)
    monthly_trends = get_monthly_totals(user_id, num_months=6)
    udhar = get_udhar_summary(user_id)

    # Category breakdown with budget comparison
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
            INSERT INTO udhar_entries (user_id, person_name, person_key, kind, amount, note, due_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, person_name, kind, amount, note, entry_date, due_date
            """,
            (user_id, person_name.strip(), person_key, kind, amount, note.strip(), due_dt),
        )
        row = cur.fetchone()
        d = dict(row)
        for f in ("entry_date", "due_date"):
            if d.get(f) and hasattr(d[f], "isoformat"):
                d[f] = d[f].isoformat()
        d["amount"] = float(d["amount"])
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
            SELECT id, person_name, person_key, kind, amount, note, entry_date, due_date
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
