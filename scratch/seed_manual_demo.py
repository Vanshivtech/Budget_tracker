import sys
sys.path.insert(0, ".")

from app.db import (
    get_user_by_email, create_user, delete_account,
    log_transaction, set_budget, add_udhar, set_savings_goal,
    contribute_to_goal, add_recurring_expense, add_transaction_tag
)
from app.auth import hash_password

email = "manual_demo@budgettracker.local"
password = "Password123!"

existing = get_user_by_email(email)
if existing:
    delete_account(existing["id"])

user = create_user(email, hash_password(password))
uid = user["id"]

# Transactions
e1 = log_transaction(uid, 450.0, "Food", "Team Lunch", "manual", merchant="Cafeteria", entry_date="2026-10-02T13:00:00Z")
add_transaction_tag(uid, e1["id"], "work")

e2 = log_transaction(uid, 1200.0, "Shopping", "Weekly groceries", "manual", merchant="Supermart", entry_date="2026-10-01T18:30:00Z")
add_transaction_tag(uid, e2["id"], "household")

e3 = log_transaction(uid, 150.0, "Transport", "Metro smartcard recharge", "manual", merchant="Metro", entry_date="2026-10-03T09:15:00Z")

e4 = log_transaction(uid, 3500.0, "Utilities", "Electricity bill", "manual", merchant="State Power", entry_date="2026-09-28T11:00:00Z")

# Budgets
set_budget(uid, "Food", 15000.0, rollover_enabled=True)
set_budget(uid, "Shopping", 8000.0, rollover_enabled=False)
set_budget(uid, "Transport", 3000.0, rollover_enabled=True)

# Udhar
add_udhar(uid, "Rahul Sharma", "lent", 2500.0, "Dinner share lent", due_date="2026-10-15", entry_date="2026-10-01T20:00:00Z")
add_udhar(uid, "Priya Patel", "borrowed", 800.0, "Cab split payment", due_date="2026-10-10", entry_date="2026-10-02T10:00:00Z")

# Savings goals
g1 = set_savings_goal(uid, "Emergency Fund", 100000.0, target_date="2026-12-31")
contribute_to_goal(uid, g1["id"], 45000.0)
g2 = set_savings_goal(uid, "New Laptop", 75000.0, target_date="2027-03-31")
contribute_to_goal(uid, g2["id"], 20000.0)

# Recurring
add_recurring_expense(uid, "Netflix Subscription", 649.0, "Entertainment", "monthly", start_date="2026-10-15")
add_recurring_expense(uid, "Gym Membership", 2000.0, "Health", "monthly", start_date="2026-11-01")

print(f"Demo user seeded successfully: {email} / {password} (UID: {uid})")
