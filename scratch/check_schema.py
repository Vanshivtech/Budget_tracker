import sys, os
sys.path.insert(0, ".")
from app.db import get_db_cursor

with get_db_cursor() as cur:
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'recurring_expenses' AND table_schema = 'public'
        ORDER BY ordinal_position
    """)
    print("--- recurring_expenses ---")
    for r in cur.fetchall():
        print(f"{r['column_name']}: {r['data_type']}")

    # Check check constraints
    cur.execute("""
        SELECT conname, pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE t.relname = 'udhar_entries'
    """)
    for r in cur.fetchall():
        print("Constraint:", r['conname'], r['pg_get_constraintdef'])
