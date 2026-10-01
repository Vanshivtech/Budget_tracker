"""
The AI agent: a LangGraph ReAct-style agent powering ABT -- AI Budget Tracker.
Tools cover expense logging, budget management, income tracking, savings goals,
user profile, and a holistic financial snapshot.

Multi-user scoped: user_id is injected from the authenticated session via
RunnableConfig and contextvar -- never exposed to the LLM or client.
"""
import contextvars
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.llm import llm_pool
from app import db

_current_user_var: contextvars.ContextVar[int | None] = contextvars.ContextVar("current_user_var", default=None)


def _get_user_id(config: RunnableConfig | None) -> int:
    """Extract user_id from RunnableConfig or the contextual variable."""
    if config:
        cfg = config.get("configurable", {})
        uid = cfg.get("user_id")
        if uid is not None:
            return int(uid)
    var_uid = _current_user_var.get()
    if var_uid is not None:
        return var_uid
    raise ValueError("User ID missing from execution context")


SYSTEM_PROMPT = """\
You are ABT, a friendly and concise AI money companion for AI Budget Tracker. You help users track \
expenses, manage budgets, log income, build savings goals, and develop better \
money habits. You give personalised insights grounded entirely in the user's \
own data from tools -- you never invent numbers.

== CORE BEHAVIOUR ==
- When the user mentions spending money, call log_expense.
- When they mention splitting or sharing a group expense (e.g. "I paid 1500 for dinner with Rahul and Priya"), call split_expense.
- When they mention regular or recurring bills (e.g. "I pay 12000 rent every month", "Netflix is 649 monthly"), call add_recurring_expense. Confirm using actual stored values returned from the tool, never invent.
- When they ask about upcoming bills or subscriptions, call get_recurring_expenses.
- When they ask to cancel or stop a recurring bill, call deactivate_recurring_expense.
- When they mention receiving money (salary, freelance, etc.), call add_income.
- When they ask to set a budget, call set_budget.
- When they ask about budget/spend status, call check_budget_status or get_monthly_summary.
- When they ask for a weekly recap or how their week went, call get_weekly_recap.
- When they ask about their financial health score or rating, call get_health_score.
- When they ask about budget pace, overspending pace, or spending projections, call check_overspending_projections.
- When they ask about their general financial snapshot, savings rate, or how much they \
can spend, call get_financial_snapshot. Use the numbers it returns exactly.
- When they set a savings goal (e.g. "I want to save for a phone"), call \
set_savings_goal. Always confirm the target, saved-so-far, and deadline before saving.
- When they contribute to a goal ("I saved 2000 for my trip"), call \
contribute_to_goal using the goal id from get_goals.
- When they say "undo" or "undo that" or "cancel the last one", call undo_last_action.
- When investing or insurance comes up, you may explain how financial \
instruments work (FDs, RDs, PPF, NPS, SIPs, index funds, mutual funds, gold, \
term insurance) and share general principles. Always add this one line: \
"Note: this is general financial education, not personalised investment advice -- \
a SEBI-registered investment adviser can give you that." 
- If asked "which fund/stock/crypto should I buy", do NOT name any specific \
product. Instead explain how to evaluate options (expense ratio, track record, \
risk profile, investment horizon, fund type) and direct them to SEBI's RIA \
search at https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFip=yes
- General principles you may always share: build an emergency fund first \
(3-6 months expenses), clear high-interest debt before investing, insure \
before investing, invest only surplus, match investment horizon to risk comfort, \
diversify across asset classes.
- When asked about current interest rates or returns, say "please check current \
rates at the institution's website or RBI/SEBI publications -- I don't have \
live rate data."
- Never give tax-filing specifics; refer users to a CA for that.
- Never predict or promise investment returns.
- Never present yourself as SEBI-registered.
- Ask the user for their current savings and risk comfort ONLY when it is \
genuinely needed for guidance (e.g. emergency fund calculation, investment \
horizon advice) AND only if you have not already recorded it via update_profile. \
Never ask repeatedly.
- When editing or deleting a past expense: call get_recent_expenses first, \
confirm the right transaction, then call update_expense or delete_expense.
- Tone and style: Sound natural, warm, and professional, not robotic, stiff, or clipped.
- Routine confirmations: Keep confirmations natural and concise (e.g. "Logged Rs 120 for snacks under Food."). Never append canned robotic questions like "Anything else you'd like to log or review?".
- Internal IDs: Never expose internal database IDs (like transaction #37 or user #) in routine confirmations or summaries. Only mention IDs when specifically disambiguating between multiple similar entries or confirming an explicit edit/delete.
- Keep replies SHORT -- 2-4 lines plus numbers. Use the Rs symbol (Rs) for amounts in INR.
- Do NOT use any emojis or emoji characters anywhere in your responses.
- Never repeat raw tool output verbatim -- summarise it conversationally.
- Never invent numbers -- every figure must come from a tool result.
"""


# ======================================================================
# TOOLS -- Expenses & Budgets
# ======================================================================

@tool
def log_expense(amount: float, category: str, note: str = "", force: bool = False, tags: str = "", config: RunnableConfig = None) -> str:
    """Log a new expense. amount is a positive number. category is a short word:
    food, groceries, travel, rent, bills, entertainment, shopping, health, other.
    note is an optional short description (e.g. the merchant or item name).
    tags is optional comma-separated labels (e.g. 'work,reimbursable').
    force: set to true only if the user explicitly confirms logging a duplicate entry."""
    user_id = _get_user_id(config)
    cat = category.lower().strip()
    clean_note = note.strip() if note else ""

    # Merchant normalization
    merchant = db.normalize_merchant(user_id, clean_note) if clean_note else None

    # Duplicate detection (unless force=True)
    if not force:
        dup = db.check_duplicate_expense(user_id, amount, cat, merchant or clean_note)
        if dup:
            return (
                f"This looks like a duplicate -- you already logged Rs {amount:.0f} "
                f"under {cat} today ({dup['note'] or 'no note'}). "
                f"Say 'log it anyway' or 'yes, log it' to confirm."
            )

    record = db.log_transaction(user_id=user_id, amount=amount, category=cat, note=clean_note, merchant=merchant)

    # Store undo state
    db.store_undo_state(user_id, "log", "transaction", record["id"], None)

    # Add tags if provided
    if tags:
        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
        for tag in tag_list:
            db.add_transaction_tag(user_id, record["id"], tag)

    note_str = f" for {clean_note}" if clean_note else ""
    merchant_str = f" ({merchant})" if merchant and merchant.lower() != clean_note.lower() else ""
    return f"Logged Rs {amount:.0f}{note_str}{merchant_str} under {cat.capitalize()}."


@tool
def set_budget(category: str, monthly_limit: float, config: RunnableConfig = None) -> str:
    """Set or update the monthly budget limit for a spending category."""
    user_id = _get_user_id(config)
    db.set_budget(user_id=user_id, category=category, monthly_limit=monthly_limit)
    return f"Monthly budget for {category.lower().strip().capitalize()} set to Rs {monthly_limit:.0f}."


@tool
def check_budget_status(category: str = "", config: RunnableConfig = None) -> str:
    """Check spend vs budget for the current month. If category is empty, returns
    status for ALL categories that have a budget set, including any rollover amounts."""
    user_id = _get_user_id(config)
    month = db.current_month()
    spend = db.spend_by_category(user_id, month)
    eff_budgets = db.get_effective_budgets(user_id, month)

    if category:
        category = category.lower().strip()
        b_info = eff_budgets.get(category)
        spent = spend.get(category, 0)
        if not b_info:
            return f"No budget set for '{category}'. You've spent Rs {spent:.0f} on it this month."
        limit = b_info["effective_budget"]
        carried = b_info.get("carried_amount", 0.0)
        pct = (spent / limit * 100) if limit else 0
        rollover_note = f" (includes Rs {carried:.0f} rolled over from last month)" if carried > 0 else ""
        return f"{category}: Rs {spent:.0f} / Rs {limit:.0f} ({pct:.0f}%) this month{rollover_note}."

    if not eff_budgets:
        return "No budgets set yet. Total spend this month: Rs %.0f" % sum(spend.values())

    lines = []
    for cat, b_info in eff_budgets.items():
        spent = spend.get(cat, 0)
        limit = b_info["effective_budget"]
        carried = b_info.get("carried_amount", 0.0)
        pct = (spent / limit * 100) if limit else 0
        flag = " [OVER BUDGET]" if spent > limit else ""
        rollover_note = f" (includes Rs {carried:.0f} rolled over)" if carried > 0 else ""
        lines.append(f"{cat}: Rs {spent:.0f}/Rs {limit:.0f} ({pct:.0f}%){flag}{rollover_note}")
    return "\n".join(lines)


@tool
def get_monthly_summary(config: RunnableConfig = None) -> str:
    """Full breakdown of this month's spending by category including totals."""
    user_id = _get_user_id(config)
    month = db.current_month()
    spend = db.spend_by_category(user_id, month)
    if not spend:
        return "No transactions logged this month yet."
    total = sum(spend.values())
    lines = [f"{cat}: Rs {amt:.0f}" for cat, amt in sorted(spend.items(), key=lambda x: -x[1])]
    lines.append(f"Total: Rs {total:.0f}")
    return "\n".join(lines)


@tool
def get_weekly_recap(config: RunnableConfig = None) -> str:
    """Weekly spending recap for the last 7 days: total spent, comparison to prior week,
    top expense category, income, and active logging streak."""
    user_id = _get_user_id(config)
    recap = db.get_weekly_recap(user_id=user_id)
    return recap.get("narration") or f"Total spent over the past 7 days: Rs {recap['total_spent']:.0f}."


@tool
def get_recent_expenses(limit: int = 10, config: RunnableConfig = None) -> str:
    """Fetch the user's most recent transactions to inspect, edit, or delete them."""
    user_id = _get_user_id(config)
    txs = db.get_recent_expenses(user_id=user_id, limit=limit)
    if not txs:
        return "No recent transactions found."
    lines = []
    for t in txs:
        note_str = f" | Note: {t['note']}" if t.get("note") else ""
        merchant_str = f" | Merchant: {t['merchant']}" if t.get("merchant") else ""
        lines.append(f"ID #{t['id']}: Rs {t['amount']:.0f} ({t['category']}) on {t['date'][:10]}{note_str}{merchant_str}")
    return "\n".join(lines)


@tool
def update_expense(
    transaction_id: int,
    amount: float | None = None,
    category: str | None = None,
    note: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """Update an existing expense by transaction_id. Only provide fields to change."""
    user_id = _get_user_id(config)
    # Store previous state for undo
    old = db.get_transaction_by_id(user_id, transaction_id)
    if old:
        db.store_undo_state(user_id, "update", "transaction", transaction_id, old)

    updated = db.update_expense(user_id=user_id, transaction_id=transaction_id,
                                amount=amount, category=category, note=note)
    if not updated:
        return f"Could not find transaction #{transaction_id} to update."
    note_display = f" (note: '{updated['note']}')" if updated.get("note") else ""
    return f"Updated #{transaction_id}: Rs {updated['amount']:.0f} under '{updated['category']}'{note_display}."


@tool
def delete_expense(transaction_id: int, config: RunnableConfig = None) -> str:
    """Delete an existing expense by its transaction ID."""
    user_id = _get_user_id(config)
    # Store previous state for undo
    old = db.get_transaction_by_id(user_id, transaction_id)
    if old:
        db.store_undo_state(user_id, "delete", "transaction", transaction_id, old)

    success = db.delete_expense(user_id=user_id, transaction_id=transaction_id)
    if success:
        return f"Deleted transaction #{transaction_id}."
    return f"Transaction #{transaction_id} not found or already deleted."


# ======================================================================
# TOOLS -- Income
# ======================================================================

@tool
def add_income(
    amount: float,
    source: str = "salary",
    entry_date: str = "",
    config: RunnableConfig = None,
) -> str:
    """Log an income entry. amount is positive. source is a short label like
    'salary', 'freelance', 'interest', 'rental', 'other'.
    entry_date is optional YYYY-MM-DD; defaults to today."""
    user_id = _get_user_id(config)
    entry = db.add_income_entry(
        user_id=user_id,
        amount=amount,
        source=source.strip() or "salary",
        entry_date=entry_date or None,
    )
    return f"Logged income of Rs {amount:.0f} from {entry['source'].capitalize()}."


@tool
def get_income_summary(month: str = "", config: RunnableConfig = None) -> str:
    """Return total income for a given month (YYYY-MM). Defaults to current month."""
    user_id = _get_user_id(config)
    target_month = month.strip() or db.current_month()
    data = db.get_income_summary(user_id=user_id, month=target_month)
    if not data["total"]:
        return f"No income logged for {target_month}."
    lines = [f"Total income ({target_month}): Rs {data['total']:.0f}"]
    for src, amt in data["by_source"].items():
        lines.append(f"  {src}: Rs {amt:.0f}")
    return "\n".join(lines)


# ======================================================================
# TOOLS -- Savings Goals
# ======================================================================

@tool
def set_savings_goal(
    name: str,
    target_amount: float,
    target_date: str = "",
    config: RunnableConfig = None,
) -> str:
    """Create or update a savings goal. name is a short label (e.g. 'Emergency fund',
    'New phone'). target_amount is the total amount to reach. target_date is optional
    YYYY-MM-DD deadline."""
    user_id = _get_user_id(config)
    goal = db.set_savings_goal(
        user_id=user_id,
        name=name.strip(),
        target_amount=target_amount,
        target_date=target_date or None,
    )
    summary = f"Goal '{goal['name']}' set: Rs {goal['target_amount']:.0f} target."
    if goal.get("months_left") is not None:
        summary += f" {goal['months_left']} months to deadline."
    if goal.get("required_monthly") is not None:
        summary += f" Need to save Rs {goal['required_monthly']:.0f}/month."
    return summary


@tool
def contribute_to_goal(goal_id: int, amount: float, config: RunnableConfig = None) -> str:
    """Add an amount to a savings goal's saved_amount. Use get_goals to find the
    goal_id first."""
    user_id = _get_user_id(config)
    updated = db.contribute_to_goal(user_id=user_id, goal_id=goal_id, amount=amount)
    if not updated:
        return f"Goal #{goal_id} not found."
    return (
        f"Added Rs {amount:.0f} to '{updated['name']}'. "
        f"Progress: Rs {updated['saved_amount']:.0f} / Rs {updated['target_amount']:.0f} "
        f"({updated['pct_complete']}%). Remaining: Rs {updated['remaining']:.0f}."
    )


@tool
def get_goals(config: RunnableConfig = None) -> str:
    """List all savings goals with progress, required monthly saving, and pace."""
    user_id = _get_user_id(config)
    goals = db.get_goals(user_id=user_id)
    if not goals:
        return "No savings goals set yet."
    lines = []
    for g in goals:
        line = (
            f"#{g['id']} '{g['name']}': Rs {g['saved_amount']:.0f}/"
            f"Rs {g['target_amount']:.0f} ({g['pct_complete']}%)"
        )
        if g.get("required_monthly") is not None:
            line += f" -- need Rs {g['required_monthly']:.0f}/month"
        if g.get("months_left") is not None:
            line += f" ({g['months_left']} months left)"
        lines.append(line)
    return "\n".join(lines)


# ======================================================================
# TOOLS -- Profile & Snapshot
# ======================================================================

@tool
def update_profile(
    current_savings: float | None = None,
    risk_comfort: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """Update the user's financial profile. current_savings is total savings in Rs.
    risk_comfort is 'low', 'medium', or 'high'. Provide only fields to update."""
    user_id = _get_user_id(config)
    if risk_comfort and risk_comfort not in ("low", "medium", "high"):
        return "risk_comfort must be 'low', 'medium', or 'high'."
    profile = db.update_user_profile(
        user_id=user_id,
        current_savings=current_savings,
        risk_comfort=risk_comfort,
    )
    parts = []
    if profile.get("current_savings") is not None:
        parts.append(f"current savings: Rs {profile['current_savings']:.0f}")
    if profile.get("risk_comfort"):
        parts.append(f"risk comfort: {profile['risk_comfort']}")
    return f"Profile updated -- {', '.join(parts)}." if parts else "Profile updated."


@tool
def get_financial_snapshot(config: RunnableConfig = None) -> str:
    """
    Returns a full financial snapshot for the current month:
    income, expenses, net surplus, savings rate, budget adherence,
    emergency fund coverage (months), safe-to-spend today, and goal pace.
    Use this when the user asks about their overall financial health.
    """
    user_id = _get_user_id(config)
    snap = db.get_financial_snapshot(user_id=user_id)

    lines = [f"Financial snapshot -- {snap['month']}:"]
    lines.append(f"Income: Rs {snap['monthly_income']:.0f}  |  Expenses: Rs {snap['monthly_expenses']:.0f}  |  Surplus: Rs {snap['net_surplus']:.0f}")

    if snap["savings_rate_pct"] is not None:
        lines.append(f"Savings rate: {snap['savings_rate_pct']}%")
    if snap["budget_adherence_pct"] is not None:
        lines.append(f"Budget adherence: {snap['budget_adherence_pct']}% of categories within limit")
    if snap["emergency_months"] is not None:
        lines.append(f"Emergency fund: {snap['emergency_months']} months of expenses covered")
    if snap["safe_to_spend_today"] is not None:
        lines.append(f"Safe to spend today: Rs {snap['safe_to_spend_today']:.0f} (remaining budget / days left)")

    if snap["goals"]:
        lines.append("Goals:")
        for g in snap["goals"]:
            pace_str = f" [{g['pace']}]" if g.get("pace") else ""
            req = f" (need Rs {g['required_monthly']:.0f}/month)" if g.get("required_monthly") else ""
            lines.append(f"  '{g['name']}': {g['pct_complete']}% complete{req}{pace_str}")

    return "\n".join(lines)


# ======================================================================
# TOOLS -- Recurring Expenses & Bill Reminders
# ======================================================================

@tool
def add_recurring_expense(
    name: str,
    amount: float,
    category: str,
    frequency: str = "monthly",
    start_date: str = "",
    config: RunnableConfig = None,
) -> str:
    """Register a recurring expense or bill reminder. name is the bill name (e.g. 'Rent', 'Netflix', 'Electricity').
    amount is the payment amount. category is a standard category (bills, rent, entertainment, etc.).
    frequency is 'monthly', 'weekly', or 'yearly' (defaults to 'monthly').
    start_date is optional YYYY-MM-DD next due date."""
    user_id = _get_user_id(config)
    exp = db.add_recurring_expense(
        user_id=user_id,
        name=name.strip(),
        amount=amount,
        category=category.lower().strip(),
        frequency=frequency.lower().strip() or "monthly",
        start_date=start_date or None,
    )
    return (
        f"Added recurring {exp['frequency']} bill for '{exp['name']}' of Rs {exp['amount']:.0f}. "
        f"Next due date is {exp['next_due_date']}."
    )


@tool
def get_recurring_expenses(config: RunnableConfig = None) -> str:
    """List all recurring expenses and upcoming bill reminders for the user."""
    user_id = _get_user_id(config)
    expenses = db.get_recurring_expenses(user_id=user_id, active_only=True)
    if not expenses:
        return "No recurring expenses or bills configured."
    lines = ["Recurring bills & expenses:"]
    for e in expenses:
        lines.append(f"#{e['id']} '{e['name']}': Rs {e['amount']:.0f} ({e['frequency']}) -- Next due: {e['next_due_date']}")
    return "\n".join(lines)


@tool
def deactivate_recurring_expense(expense_id: int, config: RunnableConfig = None) -> str:
    """Deactivate or cancel an existing recurring bill reminder by its ID."""
    user_id = _get_user_id(config)
    ok = db.deactivate_recurring_expense(user_id=user_id, expense_id=expense_id)
    if ok:
        return f"Recurring expense #{expense_id} has been deactivated."
    return f"Recurring expense #{expense_id} not found."


# ======================================================================
# TOOLS -- Health Score & Group Split
# ======================================================================

@tool
def get_health_score(month: str = "", config: RunnableConfig = None) -> str:
    """Get the user's deterministic Financial Health Score (0-100) and factor breakdown.
    month is optional YYYY-MM; defaults to current month."""
    user_id = _get_user_id(config)
    res = db.compute_health_score(user_id=user_id, month=month.strip() or None)
    lines = [f"Financial Health Score: {res['score']}/100 ({res['tier']})"]
    for f in res["factors"]:
        lines.append(f"- {f['name']}: {f['score']}/100 ({f['status']}) -- {f['description']}")
    if res["tips"]:
        lines.append(f"Recommendation: {res['tips'][0]}")
    return "\n".join(lines)


@tool
def split_expense(
    total_amount: float,
    category: str,
    participants: str,
    note: str = "",
    config: RunnableConfig = None,
) -> str:
    """Split a shared expense among yourself and friends.
    total_amount is the full amount you paid.
    category is the spending category (food, travel, entertainment, etc.).
    participants can be comma-separated names (e.g. 'Rahul, Priya') for an equal split,
    or a JSON string list of objects with names and shares (e.g. '[{"name": "Rahul", "share": 500}]').
    note is a short description of the expense."""
    user_id = _get_user_id(config)
    import json
    parts = []
    cleaned = participants.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        try:
            parsed = json.loads(cleaned)
            for item in parsed:
                if isinstance(item, str):
                    parts.append({"name": item.strip()})
                elif isinstance(item, dict) and "name" in item:
                    parts.append({"name": str(item["name"]).strip(), "share": item.get("share")})
        except Exception:
            pass

    if not parts:
        names = [n.strip() for n in cleaned.split(",") if n.strip()]
        for n in names:
            parts.append({"name": n})

    if not parts:
        return "Please specify at least one person to split the expense with."

    try:
        res = db.split_expense(
            user_id=user_id,
            total_amount=total_amount,
            category=category,
            note=note,
            participants=parts,
        )
        return res["summary"]
    except Exception as e:
        return f"Could not split expense: {str(e)}"


# ======================================================================
# TOOLS -- Undo
# ======================================================================

@tool
def undo_last_action(config: RunnableConfig = None) -> str:
    """Undo the most recent reversible action (log, edit, or delete).
    Only works within 10 minutes of the action. Call this when the user says
    'undo', 'undo that', or 'cancel the last one'."""
    user_id = _get_user_id(config)
    result = db.execute_undo(user_id)
    return result


@tool
def check_overspending_projections(config: RunnableConfig = None) -> str:
    """Check projected month-end spending pace per category.
    Uses deterministic math (spent / days_elapsed * days_in_month).
    Requires at least 7 days of spending data in the current month."""
    user_id = _get_user_id(config)
    return db.get_overspending_projections_text(user_id)


# ======================================================================
# TOOL REGISTRY & AGENT
# ======================================================================

TOOLS = [
    # Expenses
    log_expense,
    split_expense,
    set_budget,
    check_budget_status,
    check_overspending_projections,
    get_monthly_summary,
    get_weekly_recap,
    get_recent_expenses,
    update_expense,
    delete_expense,
    # Recurring
    add_recurring_expense,
    get_recurring_expenses,
    deactivate_recurring_expense,
    # Income
    add_income,
    get_income_summary,
    # Goals
    set_savings_goal,
    contribute_to_goal,
    get_goals,
    # Profile & Health
    update_profile,
    get_financial_snapshot,
    get_health_score,
    # Undo
    undo_last_action,
]

_checkpointer = MemorySaver()

# The agent is created once. The LLM model used is selected per-call via the pool.
# We initialize with the first available model.
_initial_pair = llm_pool.get_available_model()
if _initial_pair:
    _initial_llm = _initial_pair[0]
else:
    # Deferred -- will fail gracefully at call time
    from langchain_groq import ChatGroq as _FallbackChatGroq
    _initial_llm = _FallbackChatGroq(model=settings.GROQ_MODEL, api_key="placeholder")

agent = create_react_agent(
    model=_initial_llm,
    tools=TOOLS,
    state_modifier=SYSTEM_PROMPT,
    checkpointer=_checkpointer,
)


def handle_user_message(user_id: int, session_id: str, text: str) -> str:
    """Run the agent for an authenticated user on one incoming message."""
    thread_id = f"user_{user_id}_{session_id}"
    token = _current_user_var.set(user_id)
    try:
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }

        def _invoke(model, messages, cfg):
            # Swap the model on the agent if it differs
            agent.nodes["agent"].runnable.first = model
            return agent.invoke({"messages": messages}, config=cfg)

        result = llm_pool.invoke_with_retry(
            _invoke,
            [("user", text)],
            config,
        )

        # If the pool returned a friendly error string
        if isinstance(result, str):
            return result

        last_message = result["messages"][-1]
        return last_message.content or "Sorry, I could not process that -- try rephrasing?"
    except Exception:
        import logging
        logging.getLogger("budget-tracker").exception("Agent error")
        return "Something went wrong on my end -- please try again in a moment."
    finally:
        _current_user_var.reset(token)


def clear_user_agent_sessions(user_id: int) -> None:
    """Clear all LangGraph checkpoints/memory sessions for a user."""
    prefix = f"user_{user_id}_"
    if hasattr(_checkpointer, "storage"):
        # Storage dictionary in InMemorySaver / MemorySaver
        for t in list(_checkpointer.storage.keys()):
            if str(t).startswith(prefix) or t == f"user_{user_id}":
                try:
                    _checkpointer.delete_thread(t)
                except Exception:
                    _checkpointer.storage.pop(t, None)

