import sys
sys.path.insert(0, '.')
import psycopg2
from app.config import settings
DATABASE_URL = settings.DATABASE_URL

target_tables = [
    'users', 'transactions', 'budgets', 'budget_rollovers', 'udhar_entries', 
    'recurring_expenses', 'savings_goals', 'income_entries', 'user_profile', 
    'chat_messages', 'push_subscriptions', 'receipts', 'merchant_aliases', 
    'user_categories', 'app_settings', 'errors'
]

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name;
""")
all_tables = [r[0] for r in cur.fetchall()]

print("ALL_TABLES:", all_tables)

table_columns = {}
for t in all_tables:
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position;
    """, (t,))
    table_columns[t] = cur.fetchall()

print("\n--- TARGET TABLES VERIFICATION ---")
for t in target_tables:
    exists = t in all_tables
    print(f"TABLE: {t} | EXISTS: {exists}")
    if exists:
        cols = [c[0] for c in table_columns[t]]
        print(f"  COLS: {', '.join(cols)}")

other_tables = set(all_tables) - set(target_tables)
print("\n--- OTHER TABLES IN DB ---")
for ot in sorted(list(other_tables)):
    cols = [c[0] for c in table_columns[ot]]
    print(f"TABLE: {ot} | COLS: {', '.join(cols)}")

cur.close()
conn.close()
