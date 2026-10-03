import json
import sys
sys.path.insert(0, ".")
from app.db import get_db_cursor

target_tables = [
    'users', 'transactions', 'budgets', 'budget_rollovers', 'udhar_entries',
    'recurring_expenses', 'savings_goals', 'income_entries', 'user_profile',
    'chat_messages', 'push_subscriptions', 'receipts', 'merchant_aliases',
    'user_categories', 'app_settings', 'errors'
]

with get_db_cursor() as cur:
    # 1. Get all public tables
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    all_public_tables = [r['table_name'] for r in cur.fetchall()]
    
    print('ALL PUBLIC TABLES IN DB:')
    print(all_public_tables)
    print('\n' + '='*60)
    
    # 2. Check each target table and get its columns
    results = {}
    for tbl in target_tables:
        exists = tbl in all_public_tables
        results[tbl] = {'exists': exists, 'columns': []}
        if exists:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (tbl,))
            cols = cur.fetchall()
            results[tbl]['columns'] = [c['column_name'] for c in cols]
            print(f"TABLE: {tbl:20} -> Exists: {exists} | Columns ({len(cols)}): {results[tbl]['columns']}")
        else:
            print(f"TABLE: {tbl:20} -> Exists: FALSE (MISSING)")

    # 3. Check extra tables
    extra_tables = [t for t in all_public_tables if t not in target_tables]
    print(f"\nEXTRA TABLES IN DB NOT IN USER LIST: {extra_tables}")
    for tbl in extra_tables:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
        """, (tbl,))
        cols = [c['column_name'] for c in cur.fetchall()]
        print(f"  {tbl}: {cols}")
