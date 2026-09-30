"""
FastAPI app — serves the frontend and exposes auth, chat, summary, dashboard,
udhar, and health APIs.

Run from the project root:
    uvicorn app.main:app --reload
"""
import asyncio
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.db import (
    init_db, get_summary, create_user, get_user_by_email,
    get_udhar_summary, add_udhar, record_udhar_repayment,
    get_dashboard, save_chat_message, get_chat_history,
    get_goals, set_savings_goal, contribute_to_goal,
    get_financial_snapshot, get_insights, get_weekly_recap,
    get_logging_streak, add_income_entry, get_income_summary,
    get_user_profile, update_user_profile,
    suggest_budget_defaults, has_completed_onboarding, complete_onboarding,
    add_recurring_expense, get_recurring_expenses, deactivate_recurring_expense,
    check_and_process_recurring_reminders, get_effective_budgets, set_category_rollover,
    compute_health_score, split_expense, generate_monthly_excel, generate_monthly_pdf,
    current_month,
)
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from app.agent import handle_user_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("budget-tracker")

# __file__ is app/main.py -> parent is app/ -> parent.parent is project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


async def _daily_recurring_scheduler():
    while True:
        try:
            check_and_process_recurring_reminders()
        except Exception:
            logger.exception("Error in recurring bills background check")
        await asyncio.sleep(12 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    init_db()
    logger.info("Database initialized with Supabase Postgres.")
    try:
        check_and_process_recurring_reminders()
    except Exception:
        logger.exception("Initial recurring bills check failed")
    task = asyncio.create_task(_daily_recurring_scheduler())
    yield
    task.cancel()


app = FastAPI(title="ABT — AI Budget Tracker", lifespan=lifespan)

# Allow local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Request / Response Models ----------

class AuthRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    user_id: int | None = None


class UdharAddRequest(BaseModel):
    person_name: str
    kind: str  # "lent" or "borrowed"
    amount: float
    note: str = ""
    due_date: str | None = None


class UdharRepayRequest(BaseModel):
    person_name: str
    amount: float
    note: str = ""


class GoalContributeRequest(BaseModel):
    goal_id: int
    amount: float


class GoalCreateRequest(BaseModel):
    name: str
    target_amount: float
    target_date: str | None = None


class IncomeRequest(BaseModel):
    amount: float
    source: str = "salary"
    entry_date: str | None = None


class ProfileUpdateRequest(BaseModel):
    current_savings: float | None = None
    risk_comfort: str | None = None


class OnboardingCategoryItem(BaseModel):
    name: str
    amount: float
    enabled: bool


class OnboardingCompleteRequest(BaseModel):
    living_situation: str
    monthly_income: float | None = None
    categories: list[OnboardingCategoryItem]


class RecurringAddRequest(BaseModel):
    name: str
    amount: float
    category: str
    frequency: str = "monthly"
    start_date: str | None = None


class RolloverToggleRequest(BaseModel):
    category: str
    enabled: bool


class SplitParticipant(BaseModel):
    name: str
    share: float | None = None


class SplitExpenseRequest(BaseModel):
    total_amount: float | None = None
    amount: float | None = None
    category: str
    note: str = ""
    participants: list[SplitParticipant | str | dict]


# ---------- Auth Routes ----------

@app.post("/api/signup", response_model=AuthResponse)
def signup(req: AuthRequest):
    """Register a new user account with email and password."""
    email = req.email.strip().lower()
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid email address.",
        )
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )

    existing = get_user_by_email(email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    pw_hash = hash_password(req.password)
    user = create_user(email, pw_hash)
    token = create_access_token(user["id"], user["email"])

    return AuthResponse(
        token=token,
        user={"id": user["id"], "email": user["email"]},
    )


@app.post("/api/login", response_model=AuthResponse)
def login(req: AuthRequest):
    """Authenticate with email and password, returns a signed JWT."""
    email = req.email.strip().lower()
    user = get_user_by_email(email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token(user["id"], user["email"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "email": user["email"]},
    )


# ---------- Core API Routes ----------

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Send a message to the AI agent. Scoped strictly to the authenticated user."""
    try:
        # Save user message
        save_chat_message(user["id"], "user", req.message)

        reply = handle_user_message(user_id=user["id"], session_id=req.session_id, text=req.message)

        # Save assistant reply
        save_chat_message(user["id"], "assistant", reply)

    except Exception:
        logger.exception("Agent error")
        reply = "Something went wrong on my end — please try again in a moment."
    return ChatResponse(reply=reply, user_id=user["id"])


@app.get("/api/summary")
def summary(user: dict = Depends(get_current_user)):
    """Current month's category breakdown, budgets, and recent transactions for the authenticated user."""
    s = get_summary(user_id=user["id"])
    s["user_id"] = user["id"]
    s["user_email"] = user["email"]
    return s


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(get_current_user)):
    """Full dashboard data: trends, daily spend, category breakdown, udhar totals."""
    data = get_dashboard(user_id=user["id"])
    data["user_id"] = user["id"]
    return data


@app.get("/api/chat/history")
def chat_history(user: dict = Depends(get_current_user)):
    """Return the last 50 chat messages for the authenticated user."""
    messages = get_chat_history(user_id=user["id"], limit=50)
    return {"messages": messages, "user_id": user["id"]}


@app.get("/api/udhar")
def udhar_list(user: dict = Depends(get_current_user)):
    """Return udhar (lending/borrowing) summary for the authenticated user."""
    data = get_udhar_summary(user_id=user["id"])
    return data


@app.post("/api/udhar")
def udhar_add(req: UdharAddRequest, user: dict = Depends(get_current_user)):
    """Add a new udhar entry (lent or borrowed)."""
    if req.kind not in ("lent", "borrowed"):
        raise HTTPException(status_code=400, detail="kind must be 'lent' or 'borrowed'")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    entry = add_udhar(
        user_id=user["id"],
        person_name=req.person_name.strip(),
        kind=req.kind,
        amount=req.amount,
        note=req.note,
        due_date=req.due_date,
    )
    return entry


@app.post("/api/udhar/repay")
def udhar_repay(req: UdharRepayRequest, user: dict = Depends(get_current_user)):
    """Record a repayment for a person."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    entry = record_udhar_repayment(
        user_id=user["id"],
        person_name=req.person_name.strip(),
        amount=req.amount,
        note=req.note,
    )
    return entry


@app.get("/api/snapshot")
def snapshot(user: dict = Depends(get_current_user)):
    """Full financial snapshot: income, expenses, surplus, savings rate, goals, safe-to-spend."""
    return get_financial_snapshot(user_id=user["id"])


@app.get("/api/insights")
def insights(user: dict = Depends(get_current_user)):
    """3-5 deterministic insight cards for the authenticated user."""
    return {"insights": get_insights(user_id=user["id"])}


@app.get("/api/recap")
def recap(user: dict = Depends(get_current_user)):
    """Weekly recap: last 7 days spend, income, top category, streak."""
    return get_weekly_recap(user_id=user["id"])


@app.get("/api/streak")
def streak(user: dict = Depends(get_current_user)):
    """Current logging streak for the authenticated user."""
    return get_logging_streak(user_id=user["id"])


@app.get("/api/goals")
def goals_list(user: dict = Depends(get_current_user)):
    """List all savings goals with progress for the authenticated user."""
    return {"goals": get_goals(user_id=user["id"])}


@app.post("/api/goals")
def goal_create(req: GoalCreateRequest, user: dict = Depends(get_current_user)):
    """Create or update a savings goal."""
    if req.target_amount <= 0:
        raise HTTPException(status_code=400, detail="target_amount must be positive")
    goal = set_savings_goal(
        user_id=user["id"],
        name=req.name.strip(),
        target_amount=req.target_amount,
        target_date=req.target_date,
    )
    return goal


@app.post("/api/goals/contribute")
def goal_contribute(req: GoalContributeRequest, user: dict = Depends(get_current_user)):
    """Add to a goal's saved_amount."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    updated = contribute_to_goal(user_id=user["id"], goal_id=req.goal_id, amount=req.amount)
    if not updated:
        raise HTTPException(status_code=404, detail="Goal not found")
    return updated


@app.post("/api/income")
def log_income(req: IncomeRequest, user: dict = Depends(get_current_user)):
    """Log an income entry."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    return add_income_entry(
        user_id=user["id"],
        amount=req.amount,
        source=req.source,
        entry_date=req.entry_date,
    )


@app.get("/api/profile")
def profile_get(user: dict = Depends(get_current_user)):
    """Get the user financial profile."""
    return get_user_profile(user_id=user["id"])


@app.patch("/api/profile")
def profile_update(req: ProfileUpdateRequest, user: dict = Depends(get_current_user)):
    """Update current_savings and/or risk_comfort."""
    if req.risk_comfort and req.risk_comfort not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="risk_comfort must be low/medium/high")
    return update_user_profile(
        user_id=user["id"],
        current_savings=req.current_savings,
        risk_comfort=req.risk_comfort,
    )


# ---------- Onboarding ----------

@app.get("/api/onboarding/status")
def onboarding_status(user: dict = Depends(get_current_user)):
    """Check if the user needs onboarding (has no budgets set)."""
    done = has_completed_onboarding(user["id"])
    return {"completed": done}


@app.get("/api/onboarding/defaults")
def onboarding_defaults(
    income: float | None = None,
    living_situation: str = "alone",
):
    """Deterministic budget suggestions. No auth needed, no LLM call."""
    valid_situations = ("family", "alone", "pg", "roommates")
    if living_situation not in valid_situations:
        living_situation = "alone"
    defaults = suggest_budget_defaults(
        monthly_income=income,
        living_situation=living_situation,
    )
    return {"defaults": defaults, "income": income, "living_situation": living_situation}


@app.post("/api/onboarding/complete")
def onboarding_complete(
    req: OnboardingCompleteRequest,
    user: dict = Depends(get_current_user),
):
    """Save onboarding budgets. Pure DB writes, zero LLM tokens."""
    valid_situations = ("family", "alone", "pg", "roommates")
    sit = req.living_situation.lower().strip()
    if sit not in valid_situations:
        raise HTTPException(status_code=400, detail="Invalid living_situation")
    result = complete_onboarding(
        user_id=user["id"],
        living_situation=sit,
        monthly_income=req.monthly_income,
        categories=[c.model_dump() for c in req.categories],
    )
    return result


@app.get("/api/health")
def health():
    """Health check endpoint (public)."""
    return {"status": "ok"}


# ---------- Tier 1: Recurring Expenses & Bill Reminders ----------

@app.get("/api/recurring")
def recurring_list(user: dict = Depends(get_current_user)):
    """Fetch all active and past recurring bills for the authenticated user."""
    return {"recurring": get_recurring_expenses(user_id=user["id"])}


@app.post("/api/recurring")
def recurring_add(req: RecurringAddRequest, user: dict = Depends(get_current_user)):
    """Add a new recurring expense/bill reminder."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    return add_recurring_expense(
        user_id=user["id"],
        name=req.name.strip(),
        amount=req.amount,
        category=req.category.strip(),
        frequency=req.frequency,
        start_date=req.start_date,
    )


@app.post("/api/recurring/{expense_id}/deactivate")
def recurring_deactivate(expense_id: int, user: dict = Depends(get_current_user)):
    """Deactivate a recurring expense."""
    ok = deactivate_recurring_expense(user_id=user["id"], expense_id=expense_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return {"status": "ok", "deactivated_id": expense_id}


@app.get("/api/recurring/reminders")
def recurring_reminders(user: dict = Depends(get_current_user)):
    """Get bills due within 2 days for the authenticated user."""
    reminders = check_and_process_recurring_reminders(user_id=user["id"])
    return {"reminders": reminders}


@app.post("/api/recurring/trigger-reminders")
def recurring_trigger_check(user: dict = Depends(get_current_user)):
    """Manually trigger check and due-date advancement."""
    reminders = check_and_process_recurring_reminders(user_id=user["id"])
    return {"status": "ok", "reminders": reminders}


# ---------- Tier 1: Monthly Export (PDF / Excel) ----------

@app.get("/api/export/monthly")
def export_monthly(
    month: str | None = None,
    format: str = "pdf",
    user: dict = Depends(get_current_user),
):
    """Download clean, professional PDF or Excel monthly financial statement."""
    target_month = month.strip() if month else current_month()
    export_fmt = format.lower().strip()
    if export_fmt not in ("pdf", "xlsx", "excel"):
        raise HTTPException(status_code=400, detail="format must be 'pdf' or 'xlsx'")

    if export_fmt in ("xlsx", "excel"):
        content = generate_monthly_excel(user_id=user["id"], user_email=user["email"], month=target_month)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"statement_{target_month}.xlsx"
    else:
        content = generate_monthly_pdf(user_id=user["id"], user_email=user["email"], month=target_month)
        media_type = "application/pdf"
        filename = f"statement_{target_month}.pdf"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


# ---------- Tier 1: Budget Rollover ----------

@app.get("/api/budgets/rollover")
def budgets_rollover(user: dict = Depends(get_current_user)):
    """Get all categories with their effective budget, base budget, carried amount, and rollover flag."""
    return {"budgets": get_effective_budgets(user_id=user["id"])}


@app.post("/api/budgets/rollover/toggle")
def budget_rollover_toggle(req: RolloverToggleRequest, user: dict = Depends(get_current_user)):
    """Enable or disable budget rollover for a specific category."""
    res = set_category_rollover(user_id=user["id"], category=req.category, enabled=req.enabled)
    if not res:
        raise HTTPException(status_code=404, detail="Category not found in budgets")
    return res


# ---------- Tier 1: Financial Health Score ----------

@app.get("/api/health-score")
def health_score_get(month: str | None = None, user: dict = Depends(get_current_user)):
    """Get deterministic 0-100 Financial Health Score with factor breakdown and tips."""
    target_month = month.strip() if month else None
    return compute_health_score(user_id=user["id"], month=target_month)


# ---------- Tier 1: Group / Split Expenses ----------

@app.post("/api/udhar/split")
def udhar_split(req: SplitExpenseRequest, user: dict = Depends(get_current_user)):
    """Split a group expense among user and participants."""
    tot = req.total_amount if req.total_amount is not None else (req.amount or 0.0)
    if tot <= 0:
        raise HTTPException(status_code=400, detail="total_amount must be positive")
    if not req.participants:
        raise HTTPException(status_code=400, detail="participants list cannot be empty")
    normalized_participants = []
    for p in req.participants:
        if isinstance(p, str):
            normalized_participants.append({"name": p.strip()})
        elif isinstance(p, SplitParticipant):
            normalized_participants.append(p.model_dump())
        elif isinstance(p, dict):
            normalized_participants.append(p)
    try:
        return split_expense(
            user_id=user["id"],
            total_amount=tot,
            category=req.category,
            note=req.note,
            participants=normalized_participants,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------- Frontend ----------

# Mount static assets (CSS, JS, images, manifest)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/sw.js")
def serve_sw():
    """Serve the PWA service worker at the root domain."""
    return FileResponse(
        str(FRONTEND_DIR / "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"}
    )


@app.get("/manifest.json")
def serve_manifest():
    """Serve the web app manifest."""
    return FileResponse(
        str(FRONTEND_DIR / "manifest.json"),
        media_type="application/manifest+json"
    )


@app.get("/")
def serve_frontend():
    """Serve the single-page frontend."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))
