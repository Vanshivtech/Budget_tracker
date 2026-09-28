"""
FastAPI app — serves the frontend and exposes auth, chat, summary, dashboard,
udhar, and health APIs.

Run from the project root:
    uvicorn app.main:app --reload
"""
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status
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
)
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from app.agent import handle_user_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("budget-tracker")

# __file__ is app/main.py -> parent is app/ -> parent.parent is project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    init_db()
    logger.info("Database initialized with Supabase Postgres.")
    yield


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


@app.get("/api/health")
def health():
    """Health check endpoint (public)."""
    return {"status": "ok"}


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
