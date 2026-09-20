"""
The AI agent: a LangGraph ReAct-style agent with tools for logging expenses,
checking/setting budgets, summarizing spend, and editing/deleting expenses.
Multi-user scoped: user_id is injected securely from the authenticated session
via config/context and is never exposed to the LLM or client tampering.
"""
import contextvars
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
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
You are a friendly, concise personal finance assistant. The user logs expenses, \
sets budgets, asks about spending, and corrects or removes transactions through you.

Rules:
- When the user mentions spending money (e.g. "spent 500 on groceries", "300 for uber"), \
call log_expense with a sensible category (food, groceries, travel, rent, bills, \
entertainment, shopping, health, other, etc.) — infer the category from context, ask only \
if truly ambiguous.
- When the user asks to set a budget ("set food budget to 10000"), call set_budget.
- When the user asks how they're doing / how much they've spent / budget status, call \
check_budget_status.
- When the user wants a full monthly summary/breakdown, call get_monthly_summary.
- When the user wants to correct, edit, or adjust an expense (e.g. "actually it was 650", \
"change the last food expense to groceries", "edit dinner to 400"):
  1. Call get_recent_expenses to view their recent transactions.
  2. Locate the intended transaction. If there are multiple plausible matches, ask the user \
which one they mean by listing the candidate IDs, amounts, and notes instead of guessing.
  3. Once identified, call update_expense with the transaction_id and the updated fields.
  4. Confirm the update using the actual updated values returned by the tool result, never from assumption.
- When the user asks to delete or remove an expense (e.g. "delete the food expense", \
"remove the last coffee expense"):
  1. Call get_recent_expenses to locate the transaction.
  2. If more than one plausible match exists, ask which one instead of guessing.
  3. Call delete_expense with the transaction_id.
  4. Confirm deletion based on the tool result.
- Keep replies SHORT — this is a chat app, not an essay. Use at most 2-3 short lines plus \
numbers. Use the ₹ symbol for amounts (INR).
- Be encouraging but honest if they're over budget. Suggest one concrete tip when relevant.
- Never invent numbers — always use tool results for any amount or confirmation you state.
- Do not repeat the raw tool output verbatim — summarize it naturally and conversationally.
"""


@tool
def log_expense(amount: float, category: str, note: str = "", config: RunnableConfig = None) -> str:
    """Log a new expense. amount is a positive number, category is a short word
    like 'food', 'travel', 'rent', 'shopping', 'bills', 'entertainment', 'health',
    'groceries', or 'other'. note is an optional short description."""
    user_id = _get_user_id(config)
    record = db.log_transaction(user_id=user_id, amount=amount, category=category.lower().strip(), note=note)
    return f"Logged ₹{amount:.0f} under '{category.lower().strip()}' (Transaction ID: {record['id']})."


@tool
def set_budget(category: str, monthly_limit: float, config: RunnableConfig = None) -> str:
    """Set (or update) the monthly budget limit for a category."""
    user_id = _get_user_id(config)
    db.set_budget(user_id=user_id, category=category, monthly_limit=monthly_limit)
    return f"Budget for '{category.lower().strip()}' set to ₹{monthly_limit:.0f}/month."


@tool
def check_budget_status(category: str = "", config: RunnableConfig = None) -> str:
    """Check spend vs budget for the current month. If category is empty,
    returns status for ALL categories that have a budget set. If category is
    given, returns just that one."""
    user_id = _get_user_id(config)
    month = db.current_month()
    spend = db.spend_by_category(user_id, month)
    budgets = db.get_budgets(user_id)

    if category:
        category = category.lower().strip()
        limit = budgets.get(category)
        spent = spend.get(category, 0)
        if limit is None:
            return f"No budget set for '{category}'. You've spent ₹{spent:.0f} on it this month."
        pct = (spent / limit * 100) if limit else 0
        return f"{category}: ₹{spent:.0f} / ₹{limit:.0f} ({pct:.0f}%) this month."

    if not budgets:
        return "No budgets set yet. Total spend this month: ₹%.0f" % sum(spend.values())

    lines = []
    for cat, limit in budgets.items():
        spent = spend.get(cat, 0)
        pct = (spent / limit * 100) if limit else 0
        flag = " ⚠️ OVER" if spent > limit else ""
        lines.append(f"{cat}: ₹{spent:.0f}/₹{limit:.0f} ({pct:.0f}%){flag}")
    return "\n".join(lines)


@tool
def get_monthly_summary(config: RunnableConfig = None) -> str:
    """Get a full breakdown of this month's spending by category, including
    categories with no budget set, plus the total."""
    user_id = _get_user_id(config)
    month = db.current_month()
    spend = db.spend_by_category(user_id, month)
    if not spend:
        return "No transactions logged this month yet."
    total = sum(spend.values())
    lines = [f"{cat}: ₹{amt:.0f}" for cat, amt in sorted(spend.items(), key=lambda x: -x[1])]
    lines.append(f"Total: ₹{total:.0f}")
    return "\n".join(lines)


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
        lines.append(f"ID #{t['id']}: ₹{t['amount']:.0f} ({t['category']}) on {t['date'][:10]}{note_str}")
    return "\n".join(lines)


@tool
def update_expense(
    transaction_id: int,
    amount: float | None = None,
    category: str | None = None,
    note: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """Update an existing expense by transaction_id. Only provides fields that should be changed."""
    user_id = _get_user_id(config)
    updated = db.update_expense(
        user_id=user_id,
        transaction_id=transaction_id,
        amount=amount,
        category=category,
        note=note,
    )
    if not updated:
        return f"Could not find transaction #{transaction_id} to update."
    note_display = f" (note: '{updated['note']}')" if updated.get("note") else ""
    return f"Updated transaction #{transaction_id}: ₹{updated['amount']:.0f} under '{updated['category']}'{note_display}."


@tool
def delete_expense(transaction_id: int, config: RunnableConfig = None) -> str:
    """Delete an existing expense by its transaction ID."""
    user_id = _get_user_id(config)
    success = db.delete_expense(user_id=user_id, transaction_id=transaction_id)
    if success:
        return f"Successfully deleted transaction #{transaction_id}."
    return f"Transaction #{transaction_id} not found or already deleted."


TOOLS = [
    log_expense,
    set_budget,
    check_budget_status,
    get_monthly_summary,
    get_recent_expenses,
    update_expense,
    delete_expense,
]

_llm = ChatGroq(
    model=settings.GROQ_MODEL,
    api_key=settings.GROQ_API_KEY,
)
_checkpointer = MemorySaver()

agent = create_react_agent(
    model=_llm,
    tools=TOOLS,
    prompt=SYSTEM_PROMPT,           # ✅ current parameter name
    checkpointer=_checkpointer,
)


def handle_user_message(user_id: int, session_id: str, text: str) -> str:
    """Run the agent for an authenticated user on one incoming message.
    session_id and user_id are combined as thread_id for conversation state."""
    thread_id = f"user_{user_id}_{session_id}"
    token = _current_user_var.set(user_id)
    try:
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }
        result = agent.invoke({"messages": [("user", text)]}, config=config)
        last_message = result["messages"][-1]
        return last_message.content or "Sorry, I couldn't process that — try rephrasing?"
    finally:
        _current_user_var.reset(token)
