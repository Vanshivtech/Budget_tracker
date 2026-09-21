"""
FastAPI app — serves the frontend and exposes auth, chat, summary, and health APIs.

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
from pydantic import BaseModel, EmailStr

from app.config import settings
from app.db import init_db, get_summary, create_user, get_user_by_email
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


app = FastAPI(title="AI Budget Tracker", lifespan=lifespan)

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
    if len(req.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long.",
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
        reply = handle_user_message(user_id=user["id"], session_id=req.session_id, text=req.message)
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
