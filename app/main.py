"""
FastAPI app -- serves the frontend and exposes auth, chat, summary, dashboard,
udhar, settings, and health APIs.

Run from the project root:
    uvicorn app.main:app --reload
"""
import asyncio
import base64
import calendar
import json
import logging
import re
from datetime import datetime, timezone, timedelta, date as d_date
from contextlib import asynccontextmanager
from pathlib import Path

from typing import Any
from fastapi import FastAPI, Depends, HTTPException, status, Response, Query, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, field_validator

from app.config import settings
from app.db import (
    init_db, get_db_cursor, get_summary, create_user, get_user_by_email, get_user_by_id,
    get_udhar_summary, add_udhar, record_udhar_repayment, get_linked_udhar_entries,
    get_dashboard, save_chat_message, get_chat_history,
    get_goals, set_savings_goal, contribute_to_goal,
    get_financial_snapshot, get_insights, get_weekly_recap,
    get_logging_streak, add_income_entry, get_income_summary,
    get_user_profile, update_user_profile,
    VALID_LIVING_SITUATIONS, sanitize_living_situation,
    suggest_budget_defaults, has_completed_onboarding, get_onboarding_status, complete_onboarding,
    add_recurring_expense, get_recurring_expenses, deactivate_recurring_expense,
    check_and_process_recurring_reminders, get_effective_budgets, set_category_rollover,
    compute_health_score, split_expense,
    current_month, spend_by_category,
    # User & Categories
    set_username, set_avatar, get_user_display, set_user_avatar_url, search_users_by_username,
    get_dashboard_tier2,
    add_user_category, remove_user_category, get_all_categories, get_user_categories,
    add_transaction_tag, remove_transaction_tag, get_all_user_tags,
    add_merchant_alias, search_transactions, get_dashboard_ranged,
    clear_transactions, clear_udhar, clear_everything, delete_account,
    export_all_data_json, get_transaction_by_id, get_recent_top_categories,
    # Tier 3 additions
    get_udhar_reminder_data, get_cashflow_calendar,
    save_push_subscription, save_fcm_token, get_user_push_subscriptions, remove_push_subscription, clear_all_push_subscriptions,
    check_and_record_notification, normalize_merchant, check_duplicate_expense,
    log_transaction, increment_scan_count, get_scan_usage_stats,
    # Engagement Notification System
    get_users_for_engagement_notifications, log_engagement_notification,
    has_engagement_notification_today, has_engagement_type_within_days, has_budget_alert_today,
    # Password Change, Admin, and Live Settings
    update_user_password, update_user_last_login, set_user_suspended, set_user_force_password_reset,
    log_server_error, get_recent_server_errors, get_app_settings, set_app_setting, get_app_setting,
    get_user_today_message_count, get_admin_dashboard_stats, get_admin_users, get_admin_user_detail,
    get_admin_llm_usage, get_admin_table_overview, get_admin_table_rows,
    # Manual Entry & Management additions
    update_expense, delete_expense, set_budget, delete_budget, get_budgets_manager,
    update_udhar_entry, delete_udhar_entry, resolve_udhar_due_date,
    update_savings_goal, delete_savings_goal,
    update_recurring_expense, delete_recurring_expense, toggle_recurring_expense,
    # Email Verification & OTP
    set_user_otp, verify_user_email, set_user_bypass_verification,
    # App Version Management
    get_app_version, set_app_version, get_latest_app_version, create_app_version,
)
from app.auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, decode_refresh_token, get_current_user,
    create_admin_token, get_current_admin,
)
from app.email import (
    validate_email_address, generate_otp, send_otp_email, DISPOSABLE_EMAIL_DOMAINS,
)
from app.agent import handle_user_message, clear_user_agent_sessions
from app.llm import llm_pool
from app.push import send_web_push, send_engagement_notification, send_push_to_user, send_fcm_notification
from pywebpush import webpush, WebPushException
from app.scheduler import (
    start_scheduler,
    stop_scheduler,
    check_budget_alerts,
    check_large_expense,
    check_goal_milestones,
    send_daily_morning_notifications,
    send_bill_due_notifications,
)

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


async def _engagement_notification_scheduler():
    """Run engagement notifications once every 24 hours, offset by 4 hours from startup."""
    await asyncio.sleep(4 * 3600)
    while True:
        try:
            run_engagement_notifications()
        except Exception:
            logger.exception("Error in engagement notification scheduler")
        await asyncio.sleep(24 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    init_db()
    logger.info("Database initialized with Supabase Postgres.")

    # One-time cleanup of stale push subscriptions after VAPID key change
    if get_app_setting("push_subscriptions_cleared_after_vapid_change") != "true":
        count = clear_all_push_subscriptions()
        print(f"[STARTUP] Cleared {count} stale push subscriptions after VAPID key change")
        set_app_setting("push_subscriptions_cleared_after_vapid_change", "true")

    # Startup check: Ensure Android app version points to release 1.0.2 in database
    try:
        github_release_apk = "https://github.com/Vanshivtech/Budget_tracker/releases/download/v1.0.2/saarth-release.apk"
        v = get_app_version("android")
        curr_ver = (v.get("version") or "").strip() if isinstance(v, dict) else ""
        curr_url = (v.get("download_url") or "").strip() if isinstance(v, dict) else ""
        if curr_ver != "1.0.2" or not curr_url or "saarth-v1.0.0.apk" in curr_url or "v1.0.0" in curr_url:
            set_app_version(
                platform="android",
                version="1.0.2",
                download_url=github_release_apk,
                changelog="Release v1.0.2: Notifications, adaptive icon fixes, and stability improvements",
                is_forced=False,
            )
            print("[STARTUP] Updated Android app version to 1.0.2 in database.")
    except Exception as e:
        logger.warning(f"Error checking initial app version: {e}")

    try:
        check_and_process_recurring_reminders()
    except Exception:
        logger.exception("Initial recurring bills check failed")
    task_recurring = asyncio.create_task(_daily_recurring_scheduler())
    task_engagement = asyncio.create_task(_engagement_notification_scheduler())
    try:
        start_scheduler()
    except Exception:
        logger.exception("Failed to start APScheduler")
    yield
    try:
        stop_scheduler()
    except Exception:
        pass
    task_recurring.cancel()
    task_engagement.cancel()


app = FastAPI(title="SAARTH -- Make money meaningful", lifespan=lifespan)


def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


from fastapi.middleware.cors import CORSMiddleware
import os

ADMIN_ALLOWED_ORIGINS = [
    "https://saarthh.in",
    "https://www.saarthh.in",
    "https://api.saarthh.in",
    "http://localhost:5173",
    "http://localhost:8000",
]

default_origins = [
    "https://saarthai.lovable.app",
    "https://saarthh.in",
    "https://www.saarthh.in",
    "https://api.saarthh.in",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]

env_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

allowed_origins = list(dict.fromkeys(default_origins + env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://.*\.lovable\.(app|dev)$|^https://.*\.lovableproject\.com$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "*"],
)


@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    """Explicit preflight handler ensuring preflight checks return 200 OK."""
    return {"ok": True}


@app.get("/api/ping")
def ping():
    """Connectivity test endpoint (public, no auth)."""
    return {
        "ok": True,
        "service": "SAARTH",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", ".saarthh.in")


def _set_refresh_token_cookie(response: Response, refresh_token: str):
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="None",
        domain=".saarthh.in",
        max_age=2592000,
        path="/",
    )


def _delete_refresh_token_cookie(response: Response):
    response.delete_cookie(
        key="refresh_token",
        domain=".saarthh.in",
        path="/",
        httponly=True,
        secure=True,
        samesite="None",
    )
    response.delete_cookie(
        key="refresh_token",
        path="/",
        httponly=True,
        secure=True,
        samesite="None",
    )


# ---------- Request / Response Models ----------

class AuthRequest(BaseModel):
    email: str
    password: str
    username: str | None = None


class AuthResponse(BaseModel):
    access_token: str = ""
    token: str = ""
    expires_in: int = 2592000
    user: dict = {}
    requires_verification: bool = False
    message: str | None = None
    refresh_token: str | None = None


class SendOtpRequest(BaseModel):
    email: str


class VerifyOtpRequest(BaseModel):
    email: str
    otp: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    user_id: int | None = None


class TransactionCreateRequest(BaseModel):
    amount: float
    category: str
    note: str | None = ""
    date: str | None = None
    tag: str | None = None
    merchant: str | None = None


class BatchExpenseItem(BaseModel):
    amount: Any
    category: Any
    note: str | None = ""
    date: str | None = None
    merchant: str | None = None


class BatchTransactionsRequest(BaseModel):
    expenses: list[BatchExpenseItem]


class TransactionUpdateRequest(BaseModel):
    amount: float | None = None
    category: str | None = None
    note: str | None = None
    date: str | None = None
    tags: list[str] | None = None
    merchant: str | None = None


class ScanConfirmRequest(BaseModel):
    amount: float
    merchant: str | None = None
    date: str | None = None
    category: str
    note: str | None = None
    source: str = "scan"


class BudgetCreateRequest(BaseModel):
    category: str
    monthly_limit: float
    rollover_enabled: bool | None = False


class BudgetUpdateRequest(BaseModel):
    monthly_limit: float | None = None
    rollover_enabled: bool | None = None


class UdharAddRequest(BaseModel):
    person_name: str
    kind: str  # "lent", "borrowed", "received_back", "paid_back"
    amount: float
    note: str = ""
    date: str | None = None
    due_date: str | None = None
    linked_user_id: int | None = None


class UdharUpdateRequest(BaseModel):
    amount: float | None = None
    note: str | None = None
    date: str | None = None
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


class GoalUpdateRequest(BaseModel):
    name: str | None = None
    target_amount: float | None = None
    target_date: str | None = None


class RecurringUpdateRequest(BaseModel):
    name: str | None = None
    amount: float | None = None
    category: str | None = None
    frequency: str | None = None
    next_due_date: str | None = None
    active: bool | None = None


class IncomeRequest(BaseModel):
    amount: float
    source: str = "salary"
    date: str | None = None
    entry_date: str | None = None


class ProfileUpdateRequest(BaseModel):
    current_savings: float | None = None
    risk_comfort: str | None = None
    living_situation: str | None = None

    @field_validator("living_situation", mode="before")
    @classmethod
    def sanitize_living_situation_field(cls, v: Any) -> str | None:
        if v is not None and isinstance(v, str):
            sanitized = sanitize_living_situation(v)
            if sanitized:
                return sanitized
        return v


class OnboardingCategoryItem(BaseModel):
    name: str
    amount: float
    enabled: bool = True


class OnboardingCompleteRequest(BaseModel):
    living_situation: str = "alone"
    monthly_income: float | None = None
    categories: list[OnboardingCategoryItem] = []

    @field_validator("living_situation", mode="before")
    @classmethod
    def sanitize_living_situation_field(cls, v: Any) -> str:
        if isinstance(v, str):
            sanitized = sanitize_living_situation(v)
            if sanitized:
                return sanitized
        return str(v) if v is not None else "alone"


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


class UsernameRequest(BaseModel):
    username: str


class AvatarRequest(BaseModel):
    avatar_id: int


class CategoryRequest(BaseModel):
    name: str


class TagRequest(BaseModel):
    tag: str


class MerchantCorrectionRequest(BaseModel):
    raw_input: str
    normalized_name: str


class ClearTransactionsRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


class ClearConfirmRequest(BaseModel):
    confirmation: str
    export_token: str | None = None


class DeleteAccountRequest(BaseModel):
    confirmation: str
    export_token: str | None = None


class PushSubscribeRequest(BaseModel):
    endpoint: str | None = None
    keys: dict | None = None
    preferences: dict | None = None
    subscription: dict | None = None


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class FcmTokenRequest(BaseModel):
    token: str
    platform: str = "android"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminSuspendRequest(BaseModel):
    suspended: bool


class AdminForceResetRequest(BaseModel):
    force: bool = True


class AdminDeleteUserRequest(BaseModel):
    confirm_email: str


class AppVersionResponse(BaseModel):
    version: str
    download_url: str
    changelog: str | None = ""
    is_forced: bool = False
    platform: str = "android"


class AppVersionUpdateRequest(BaseModel):
    version: str
    download_url: str
    changelog: str | None = ""
    is_forced: bool = False
    platform: str | None = "android"


class SmsIngestPayload(BaseModel):
    sender: str | None = None
    body: str | None = None
    timestamp: Any | None = None
    batch: list[dict] | None = None
    sms: list[dict] | None = None



# ---------- Auth Routes ----------

@app.post("/api/signup", response_model=AuthResponse)
@app.post("/auth/signup", response_model=AuthResponse)
@app.post("/auth/register", response_model=AuthResponse)
@app.post("/api/auth/register", response_model=AuthResponse)
@app.post("/api/register", response_model=AuthResponse)
def signup(req: AuthRequest, response: Response):
    """Register a new user account with email and password."""
    email = req.email.strip().lower()
    valid_email, err_msg = validate_email_address(email)
    if not valid_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long.",
        )

    existing = get_user_by_email(email)
    if existing:
        if existing.get("email_verified") or existing.get("bypass_verification"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists.",
            )
        # Unverified existing account: update password and refresh OTP
        otp = generate_otp()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        set_user_otp(email, otp, expires_at)
        pw_hash = hash_password(req.password)
        update_user_password(existing["id"], pw_hash)
        send_otp_email(email, otp)
        token = create_access_token(existing["id"], email)
        refresh_token = create_refresh_token(existing["id"], email)
        _set_refresh_token_cookie(response, refresh_token)
        return AuthResponse(
            access_token=token,
            token=token,
            expires_in=2592000,
            refresh_token=refresh_token,
            user={"id": existing["id"], "email": email},
            requires_verification=True,
            message="Verification code sent to your email. Please verify your account.",
        )

    pw_hash = hash_password(req.password)
    is_bypass = (email == "shiv@gmail.com")

    if is_bypass:
        user = create_user(
            email=email,
            password_hash=pw_hash,
            email_verified=True,
            bypass_verification=True,
        )
        update_user_last_login(user["id"])
        token = create_access_token(user["id"], user["email"])
        refresh_token = create_refresh_token(user["id"], user["email"])
        _set_refresh_token_cookie(response, refresh_token)
        _safe_print(f"🍪 [AUTH] Set refresh_token cookie for user {user['id']} (domain=.saarthh.in, SameSite=None, Secure=True)")
        if req.username and req.username.strip():
            try:
                set_username(user["id"], req.username.strip())
            except ValueError:
                pass
        user_display = get_user_display(user["id"])
        return AuthResponse(
            access_token=token,
            token=token,
            expires_in=2592000,
            refresh_token=refresh_token,
            user={
                "id": user["id"],
                "email": user["email"],
                "username": user_display.get("username"),
                "avatar_id": user_display.get("avatar_id", 1),
                "needs_username": user_display.get("needs_username", True),
                "force_password_reset": False,
            },
            requires_verification=False,
        )

    # Regular new user requiring email verification
    otp = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    user = create_user(
        email=email,
        password_hash=pw_hash,
        email_verified=False,
        bypass_verification=False,
        otp=otp,
        otp_expires_at=expires_at,
    )
    if req.username and req.username.strip():
        try:
            set_username(user["id"], req.username.strip())
        except ValueError:
            pass

    send_otp_email(email, otp)
    token = create_access_token(user["id"], user["email"])
    refresh_token = create_refresh_token(user["id"], user["email"])
    _set_refresh_token_cookie(response, refresh_token)
    user_display = get_user_display(user["id"])
    return AuthResponse(
        access_token=token,
        token=token,
        expires_in=2592000,
        refresh_token=refresh_token,
        user={
            "id": user["id"],
            "email": user["email"],
            "username": user_display.get("username"),
            "avatar_id": user_display.get("avatar_id", 1),
            "needs_username": user_display.get("needs_username", True),
        },
        requires_verification=True,
        message="Verification code sent to your email. Please verify your account before logging in.",
    )


@app.post("/api/login", response_model=AuthResponse)
@app.post("/auth/login", response_model=AuthResponse)
def login(req: AuthRequest, response: Response):
    """Authenticate with email and password, returns signed JWT and sets refresh cookie."""
    email = req.email.strip().lower()
    user = get_user_by_email(email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.get("suspended_at"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended, contact support",
        )

    # Email verification check
    if not user.get("email_verified") and not user.get("bypass_verification"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email before logging in.",
        )

    update_user_last_login(user["id"])
    token = create_access_token(user["id"], user["email"])
    refresh_token = create_refresh_token(user["id"], user["email"])

    _set_refresh_token_cookie(response, refresh_token)
    _safe_print(f"🍪 [AUTH] Set refresh_token cookie for user {user['id']} (domain=.saarthh.in, SameSite=None, Secure=True)")

    user_display = get_user_display(user["id"])

    return AuthResponse(
        access_token=token,
        token=token,
        expires_in=2592000,
        refresh_token=refresh_token,
        user={
            "id": user["id"],
            "email": user["email"],
            "username": user_display.get("username"),
            "avatar_id": user_display.get("avatar_id", 1),
            "needs_username": user_display.get("needs_username", False),
            "force_password_reset": bool(user.get("force_password_reset")),
        },
    )


@app.post("/auth/send-otp")
@app.post("/api/auth/send-otp")
def send_otp_endpoint(req: SendOtpRequest):
    """Send or resend a 6-digit OTP code to the given email."""
    email = req.email.strip().lower()
    valid_email, err_msg = validate_email_address(email)
    if not valid_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )

    user = get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found with this email.",
        )

    otp = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    set_user_otp(email, otp, expires_at)
    send_otp_email(email, otp)

    return {"status": "ok", "message": "Verification code sent to your email."}


@app.post("/auth/verify-otp")
@app.post("/api/auth/verify-otp")
def verify_otp_endpoint(req: VerifyOtpRequest, response: Response):
    """Verify 6-digit OTP code, activate account, and issue tokens."""
    email = req.email.strip().lower()
    otp = req.otp.strip()

    user = get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found with this email.",
        )

    if user.get("bypass_verification") or user.get("email_verified"):
        token = create_access_token(user["id"], user["email"])
        refresh_token = create_refresh_token(user["id"], user["email"])
        _set_refresh_token_cookie(response, refresh_token)
        _safe_print(f"🍪 [AUTH] Set refresh_token cookie for user {user['id']} (domain=.saarthh.in, SameSite=None, Secure=True)")
        user_display = get_user_display(user["id"])
        return {
            "status": "ok",
            "message": "Email is already verified.",
            "access_token": token,
            "token": token,
            "expires_in": 2592000,
            "refresh_token": refresh_token,
            "user": user_display,
        }

    stored_otp = user.get("otp")
    if not stored_otp or stored_otp != otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    expires_at = user.get("otp_expires_at")
    now = datetime.now(timezone.utc)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not expires_at or now > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new code.",
        )

    verify_user_email(email)
    update_user_last_login(user["id"])
    token = create_access_token(user["id"], user["email"])
    refresh_token = create_refresh_token(user["id"], user["email"])

    _set_refresh_token_cookie(response, refresh_token)
    _safe_print(f"🍪 [AUTH] Set refresh_token cookie for user {user['id']} (domain=.saarthh.in, SameSite=None, Secure=True)")

    user_display = get_user_display(user["id"])
    return {
        "status": "ok",
        "message": "Email verified successfully.",
        "access_token": token,
        "token": token,
        "expires_in": 2592000,
        "refresh_token": refresh_token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user_display.get("username"),
            "avatar_id": user_display.get("avatar_id", 1),
            "needs_username": user_display.get("needs_username", False),
        },
    }


@app.post("/auth/refresh")
@app.post("/api/auth/refresh")
@app.post("/api/refresh")
def refresh_token_endpoint(
    request: Request,
    response: Response,
    req: RefreshTokenRequest | None = None,
):
    """Validate refresh token from HttpOnly cookie and rotate with new access token and 30-day refresh cookie."""
    _safe_print(f"🔄 [REFRESH] Received cookies: {dict(request.cookies)}, origin: {request.headers.get('origin')}")
    token = request.cookies.get("refresh_token")
    if not token and req and req.refresh_token:
        token = req.refresh_token
        _safe_print("🔄 [REFRESH] Token extracted from JSON request body")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            _safe_print("🔄 [REFRESH] Token extracted from Authorization Bearer header")

    if not token:
        _safe_print(f"❌ [REFRESH] No refresh token found. Available cookies: {list(request.cookies.keys())}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required in cookie or body",
        )

    payload = decode_refresh_token(token)
    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if user.get("suspended_at"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended, contact support",
        )

    new_access_token = create_access_token(user["id"], user["email"])
    new_refresh_token = create_refresh_token(user["id"], user["email"])

    _set_refresh_token_cookie(response, new_refresh_token)
    _safe_print(f"🍪 [REFRESH] Rotated refresh_token cookie for user {user['id']} (domain=.saarthh.in, SameSite=None, Secure=True)")

    user_display = get_user_display(user["id"])
    return {
        "access_token": new_access_token,
        "expires_in": 2592000,
        "token": new_access_token,
        "refresh_token": new_refresh_token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user_display.get("username"),
            "avatar_id": user_display.get("avatar_id", 1),
            "needs_username": user_display.get("needs_username", False),
            "force_password_reset": bool(user.get("force_password_reset")),
        },
    }


@app.post("/auth/logout")
@app.post("/api/auth/logout")
@app.post("/api/logout")
def logout_endpoint(response: Response):
    """Clear refresh token cookie."""
    _delete_refresh_token_cookie(response)
    return {"status": "ok", "message": "Logged out successfully"}


@app.get("/api/debug/cookies")
@app.get("/debug/cookies")
def debug_cookies(request: Request):
    """Temporary debug endpoint to inspect cookies and CORS headers."""
    client_origin = request.headers.get("origin", "")
    is_allowed = (
        client_origin in allowed_origins
        or client_origin.endswith(".saarthh.in")
        or client_origin == "https://saarthh.in"
        or bool(re.match(r"^https://.*\.lovable\.(app|dev)$|^https://.*\.lovableproject\.com$", client_origin))
    )
    return {
        "cookies_received": dict(request.cookies),
        "has_refresh_token_cookie": "refresh_token" in request.cookies,
        "client_origin": client_origin,
        "is_origin_allowed": is_allowed,
        "configured_allowed_origins": allowed_origins,
        "cors_allow_credentials": True,
        "cookie_settings": {
            "samesite": "None",
            "secure": True,
            "httponly": True,
            "path": "/",
            "domain": COOKIE_DOMAIN,
            "max_age": 30 * 24 * 60 * 60,
        },
        "request_headers": {
            k: v for k, v in request.headers.items()
            if k.lower() in ("origin", "cookie", "referer", "user-agent", "host", "authorization")
        },
    }


@app.post("/api/account/change-password")
def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    """Change current user's password. Requires current password verification."""
    if not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    if len(req.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )
    if req.new_password == req.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password cannot be identical to current password",
        )

    new_hash = hash_password(req.new_password)
    update_user_password(user["id"], new_hash)
    clear_user_agent_sessions(user["id"])
    return {"status": "ok", "message": "Password changed successfully"}


# ---------- Core API Routes ----------

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Send a message to the AI agent. Scoped strictly to the authenticated user."""
    try:
        # Check global daily message cap per user
        cap_val = get_app_setting("daily_message_cap", "100")
        try:
            cap = int(cap_val)
        except ValueError:
            cap = 100
        today_count = get_user_today_message_count(user["id"])
        if today_count >= cap:
            return ChatResponse(
                reply="Daily message limit reached. Please try again tomorrow.",
                user_id=user["id"],
            )

        # Save user message
        save_chat_message(user["id"], "user", req.message)

        reply = handle_user_message(user_id=user["id"], session_id=req.session_id, text=req.message)

        # Save assistant reply
        save_chat_message(user["id"], "assistant", reply)

    except Exception:
        logger.exception("Agent error")
        reply = "Something went wrong on my end -- please try again in a moment."
    return ChatResponse(reply=reply, user_id=user["id"])


@app.get("/api/summary")
def summary(user: dict = Depends(get_current_user)):
    """Current month's category breakdown, budgets, and recent transactions for the authenticated user."""
    s = get_summary(user_id=user["id"])
    s["user_id"] = user["id"]
    s["user_email"] = user["email"]
    return s


@app.get("/api/dashboard")
def dashboard(
    user: dict = Depends(get_current_user),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    range: str | None = Query(None),
    tier: str | None = Query(None),
):
    """Dashboard data endpoint.
    By default returns Tier 1 (fast SQL aggregates <500ms): total spend, budget remaining,
    categories, and recent transactions.
    If tier=2 is requested, returns Tier 2 data.
    """
    if tier == "2":
        return dashboard_tier2(user=user)

    from datetime import date as d_date
    import calendar as cal

    today = d_date.today()
    sd, ed = start_date, end_date

    if range == "last_month":
        if today.month == 1:
            m, y = 12, today.year - 1
        else:
            m, y = today.month - 1, today.year
        sd = f"{y}-{m:02d}-01"
        ed = f"{y}-{m:02d}-{cal.monthrange(y, m)[1]}"
    elif range == "last_3_months":
        from datetime import timedelta
        three_months_ago = today - timedelta(days=90)
        sd = three_months_ago.isoformat()
        ed = today.isoformat()
    elif range == "this_month" or (not sd and not ed):
        month = current_month()
        sd = f"{month}-01"
        y, m = map(int, month.split("-"))
        ed = f"{month}-{cal.monthrange(y, m)[1]}"

    data = get_dashboard_ranged(user_id=user["id"], start_date=sd, end_date=ed)
    data["user_id"] = user["id"]
    if tier == "full":
        data["projections"] = []
    return data


@app.get("/api/dashboard/tier2")
@app.get("/api/dashboard/tier-2")
def dashboard_tier2(user: dict = Depends(get_current_user)):
    """Tier 2 expensive computations (health score, projections, potential savings, AI insights).
    Loaded asynchronously after Tier 1 renders.
    """
    data = get_dashboard_tier2(user["id"])
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


@app.get("/api/udhar/linked")
def udhar_linked_list(user: dict = Depends(get_current_user)):
    """Return udhar entries where current user is linked_user_id (debts other users have recorded involving them)."""
    return get_linked_udhar_entries(user_id=user["id"])


@app.post("/api/udhar")
def udhar_add(req: UdharAddRequest, user: dict = Depends(get_current_user)):
    """Add a new udhar entry (lent, borrowed, received_back, paid_back)."""
    valid_kinds = ("lent", "borrowed", "received_back", "paid_back", "received back", "paid back")
    if req.kind.strip().lower() not in valid_kinds:
        raise HTTPException(status_code=400, detail="kind must be 'lent', 'borrowed', 'received_back', or 'paid_back'")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    if not req.person_name.strip():
        raise HTTPException(status_code=400, detail="person_name is required")

    linked_uid = None
    if req.linked_user_id is not None:
        linked_user = get_user_by_id(int(req.linked_user_id))
        if not linked_user:
            raise HTTPException(status_code=404, detail="Linked user not found")
        linked_uid = int(req.linked_user_id)

    entry = add_udhar(
        user_id=user["id"],
        person_name=req.person_name.strip(),
        kind=req.kind,
        amount=req.amount,
        note=req.note,
        due_date=req.due_date,
        entry_date=req.date,
        linked_user_id=linked_uid,
    )
    return entry


@app.put("/api/udhar/{entry_id}")
def udhar_update(entry_id: int, req: UdharUpdateRequest, user: dict = Depends(get_current_user)):
    """Update an existing udhar entry."""
    if req.amount is not None and req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    entry = update_udhar_entry(
        user_id=user["id"],
        entry_id=entry_id,
        amount=req.amount,
        note=req.note,
        entry_date=req.date,
        due_date=req.due_date,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Udhar entry not found")
    return entry


@app.delete("/api/udhar/{entry_id}")
def udhar_delete(entry_id: int, user: dict = Depends(get_current_user)):
    """Delete an existing udhar entry."""
    ok = delete_udhar_entry(user_id=user["id"], entry_id=entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Udhar entry not found")
    return {"status": "ok", "deleted_id": entry_id, "summary": get_udhar_summary(user["id"])}


@app.post("/api/udhar/{entry_id}/resolve")
def udhar_resolve(entry_id: int, user: dict = Depends(get_current_user)):
    """Resolve due date for an udhar entry, clearing overdue highlight."""
    resolved = resolve_udhar_due_date(user_id=user["id"], entry_id=entry_id)
    if not resolved:
        raise HTTPException(status_code=404, detail="Udhar entry not found")

    linked_uid = resolved.get("linked_user_id")
    if linked_uid:
        try:
            display = get_user_display(user["id"])
            uname = display.get("username") or user.get("username") or user.get("email", "").split("@")[0] or "A user"
            send_push_to_user(
                user_id=int(linked_uid),
                title="SAARTH Udhar Update",
                body=f"{uname} marked a debt as settled",
                url="/udhar",
            )
        except Exception as e:
            logger.error(f"Error sending push notification to linked user {linked_uid}: {e}")

    return {"status": "ok", "resolved_id": entry_id, "summary": get_udhar_summary(user["id"])}


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
    if goal and goal.get("id"):
        try:
            check_goal_milestones(user["id"], goal["id"])
        except Exception as e:
            logger.error(f"Error checking goal milestones: {e}")
    return goal


@app.post("/api/goals/contribute")
def goal_contribute(req: GoalContributeRequest, user: dict = Depends(get_current_user)):
    """Add to a goal's saved_amount."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    updated = contribute_to_goal(user_id=user["id"], goal_id=req.goal_id, amount=req.amount)
    if not updated:
        raise HTTPException(status_code=404, detail="Goal not found")
    try:
        check_goal_milestones(user["id"], req.goal_id)
    except Exception as e:
        logger.error(f"Error checking goal milestones: {e}")
    return updated


@app.put("/api/goals/{goal_id}")
def goal_update(goal_id: int, req: GoalUpdateRequest, user: dict = Depends(get_current_user)):
    """Update an existing savings goal."""
    if req.target_amount is not None and req.target_amount <= 0:
        raise HTTPException(status_code=400, detail="target_amount must be positive")
    updated = update_savings_goal(
        user_id=user["id"],
        goal_id=goal_id,
        name=req.name,
        target_amount=req.target_amount,
        target_date=req.target_date,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Goal not found")
    try:
        check_goal_milestones(user["id"], goal_id)
    except Exception as e:
        logger.error(f"Error checking goal milestones: {e}")
    return updated


@app.delete("/api/goals/{goal_id}")
def goal_delete(goal_id: int, user: dict = Depends(get_current_user)):
    """Delete an existing savings goal."""
    ok = delete_savings_goal(user_id=user["id"], goal_id=goal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"status": "ok", "deleted_id": goal_id}


@app.post("/api/income")
def log_income(req: IncomeRequest, user: dict = Depends(get_current_user)):
    """Log an income entry."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    return add_income_entry(
        user_id=user["id"],
        amount=req.amount,
        source=req.source,
        entry_date=req.date or req.entry_date,
    )


@app.get("/api/profile")
def profile_get(user: dict = Depends(get_current_user)):
    """Get the user financial profile."""
    return get_user_profile(user_id=user["id"])


@app.patch("/api/profile")
def profile_update(req: ProfileUpdateRequest, user: dict = Depends(get_current_user)):
    """Update current_savings, risk_comfort, and/or living_situation."""
    if req.risk_comfort and req.risk_comfort not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="risk_comfort must be low/medium/high")
    sit = None
    if req.living_situation:
        sit = sanitize_living_situation(req.living_situation)
        if not sit:
            raise HTTPException(
                status_code=400,
                detail=f"living_situation must be one of: {', '.join(VALID_LIVING_SITUATIONS)}",
            )
    return update_user_profile(
        user_id=user["id"],
        current_savings=req.current_savings,
        risk_comfort=req.risk_comfort,
        living_situation=sit,
    )


# ---------- User Settings: Username, Search & Avatar ----------

@app.get("/api/users/search")
def users_search(
    q: str = Query(""),
    user: dict = Depends(get_current_user),
):
    """Case-insensitive partial match on username field, excluding requesting user (max 10 results)."""
    return search_users_by_username(query=q, exclude_user_id=user["id"], limit=10)


@app.get("/api/user/display")
def user_display(user: dict = Depends(get_current_user)):
    """Get username, avatar, email, and needs_username flag."""
    return get_user_display(user["id"])


@app.patch("/api/user/username")
@app.post("/api/user/username")
def user_set_username(req: UsernameRequest, user: dict = Depends(get_current_user)):
    """Set or update the user's display name."""
    try:
        return set_username(user["id"], req.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/user/avatar")
@app.post("/api/user/avatar")
def user_set_avatar(req: AvatarRequest, user: dict = Depends(get_current_user)):
    """Set the user's avatar (1-8)."""
    return set_avatar(user["id"], req.avatar_id)


@app.post("/api/user/avatar-upload")
async def user_avatar_upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """Upload custom avatar profile photo."""
    raise HTTPException(
        status_code=503,
        detail="Photo upload requires cloud storage to be configured"
    )


@app.get("/api/user/avatar-url")
def user_avatar_url(user: dict = Depends(get_current_user)):
    """Get signed URL for user's uploaded avatar photo, or null if using preset icon."""
    return {"signed_url": None}


@app.delete("/api/user/avatar-photo")
def user_remove_avatar_photo(user: dict = Depends(get_current_user)):
    """Remove user's uploaded avatar photo and revert to preset icon."""
    set_user_avatar_url(user["id"], None)
    return {"status": "ok"}


# ---------- Custom Categories ----------

@app.get("/api/categories")
def categories_list(user: dict = Depends(get_current_user)):
    """List all available categories (system + custom)."""
    return {
        "categories": get_all_categories(user["id"]),
        "custom": get_user_categories(user["id"]),
    }


@app.post("/api/categories")
def category_add(req: CategoryRequest, user: dict = Depends(get_current_user)):
    """Add a custom category."""
    try:
        return add_user_category(user["id"], req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/categories/{name}")
def category_remove(name: str, user: dict = Depends(get_current_user)):
    """Remove a custom category."""
    ok = remove_user_category(user["id"], name)
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"status": "ok"}


# ---------- Tags ----------

@app.post("/api/transactions/{tid}/tags")
def tag_add(tid: int, req: TagRequest, user: dict = Depends(get_current_user)):
    """Add a tag to a transaction."""
    return add_transaction_tag(user["id"], tid, req.tag)


@app.delete("/api/transactions/{tid}/tags/{tag}")
def tag_remove(tid: int, tag: str, user: dict = Depends(get_current_user)):
    """Remove a tag from a transaction."""
    ok = remove_transaction_tag(user["id"], tid, tag)
    if not ok:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"status": "ok"}


@app.get("/api/tags")
def tags_list(user: dict = Depends(get_current_user)):
    """List all tags used by this user."""
    return {"tags": get_all_user_tags(user["id"])}


# ---------- Transaction Manual Entry, Search & Management ----------

@app.get("/api/transactions/recent-categories")
def transactions_recent_categories(user: dict = Depends(get_current_user)):
    """Return the 5 most frequently used categories by this user in the last 30 days."""
    return {"categories": get_recent_top_categories(user_id=user["id"], days=30, limit=5)}


# ---------- Groq Vision Receipt / Screenshot Scanning ----------

MAX_SCAN_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_SCAN_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
ALLOWED_SCAN_MIMES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}
VALID_SCAN_CATEGORIES = {
    "food": "Food",
    "transport": "Transport",
    "shopping": "Shopping",
    "bills": "Bills",
    "entertainment": "Entertainment",
    "health": "Health",
    "education": "Education",
    "transfer": "Transfer",
    "other": "Other",
}


def _validate_scan_image(file: UploadFile, content: bytes) -> tuple[bool, str, str]:
    """Validate uploaded image format (jpg, jpeg, png, webp, gif) and size (max 10MB).
    Returns (is_valid, mime_type, error_message).
    """
    if not content:
        return False, "", "Empty image file"
    if len(content) > MAX_SCAN_IMAGE_BYTES:
        return False, "", "Image exceeds maximum size of 10MB"

    filename = (file.filename or "").lower().strip()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    content_type = (file.content_type or "").lower().strip()

    # Check magic bytes first
    mime = ""
    if content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif content.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        mime = "image/webp"

    if not mime:
        if ext in ALLOWED_SCAN_EXTENSIONS:
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        elif content_type in ALLOWED_SCAN_MIMES:
            mime = "image/jpeg" if content_type == "image/jpg" else content_type
        else:
            return False, "", "Unsupported image format. Supported formats: jpg, jpeg, png, webp, gif"

    return True, mime, ""


def _build_vision_scan_prompt(today_date: str) -> str:
    return (
        "You are a financial transaction extractor for an Indian\n"
        "personal finance app. Look at this image carefully.\n\n"
        "It may show:\n"
        "1. A single payment confirmation screen\n"
        "2. A list of multiple transactions (like a bank/UPI history)\n\n"
        "If it shows MULTIPLE transactions, extract ALL of them.\n"
        "Navi app format: merchant name on left, amount on right,\n"
        "UPI ID below merchant name, date and time below that.\n"
        "Debit transactions show plain ₹amount.\n"
        "Credit transactions show +₹amount in green.\n\n"
        "Additional Indian fintech app formats:\n"
        '- Navi: amount shown as "₹X,XXX" with green color,\n'
        '  merchant shown as "To: [name]" or "Paid to [name]"\n'
        '- PhonePe: "Paid ₹X to [name]"\n'
        '- Google Pay: "You paid ₹X to [name]"\n'
        '- BHIM: "Transaction of ₹X"\n'
        '- Paytm: "₹X paid to [merchant]"\n'
        '- Bank apps: "Debit of ₹X", "Dr ₹X"\n\n'
        "Respond ONLY with valid JSON, no other text:\n"
        "{\n"
        '  "type": "single" or "list",\n'
        '  "found": true or false,\n'
        '  "transactions": [\n'
        "    {\n"
        '      "amount": number (positive for debit, negative for credit),\n'
        '      "merchant": "merchant name or person name",\n'
        '      "upi_id": "upi id if visible",\n'
        '      "date": "YYYY-MM-DD",\n'
        '      "time": "HH:MM if visible",\n'
        '      "type": "debit" or "credit",\n'
        '      "category": "best guess from: Food, Transport,\n'
        "                   Shopping, Bills, Entertainment,\n"
        '                   Health, Education, Transfer, Other",\n'
        '      "confidence": "high/medium/low"\n'
        "    }\n"
        "  ],\n"
        '  "raw_text": "key text you could read"\n'
        "}\n\n"
        "For Navi transaction history:\n"
        "- Merchant is the person/business name in bold\n"
        "- Amount is on the right side\n"
        "- UPI shows below merchant name\n"
        "- Date format: 'Yesterday', 'X Nov 2026' etc\n"
        "- Convert relative dates like 'Yesterday' to actual date\n"
        f"  based on today being {today_date}\n"
        "- Skip credit transactions (shown with + prefix) unless\n"
        "  amount is significant (>100)\n"
        "- Max 20 transactions per image"
    )


def _normalize_scan_date(raw_date: Any, today_date: str) -> str:
    """Normalize YYYY-MM-DD or relative date strings like 'Yesterday' / '12 Nov 2026'."""
    if not raw_date or not isinstance(raw_date, str):
        return today_date
    s = raw_date.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    lower_s = s.lower()
    try:
        base_dt = d_date.fromisoformat(today_date)
    except ValueError:
        base_dt = d_date.today()
    if lower_s == "today":
        return base_dt.isoformat()
    if lower_s == "yesterday":
        return (base_dt - timedelta(days=1)).isoformat()
    for fmt in ("%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %b %y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return today_date


def _parse_single_tx_item(item: dict, today_date: str) -> dict | None:
    """Validate and normalize a single extracted transaction object."""
    if not isinstance(item, dict):
        return None

    raw_amt = item.get("amount")
    if raw_amt is None:
        return None

    tx_type = str(item.get("type") or "debit").strip().lower()
    if tx_type not in ("debit", "credit"):
        tx_type = "debit"

    try:
        amt_str = str(raw_amt).replace(",", "").replace("₹", "").replace(" ", "").strip()
        if amt_str.startswith("+"):
            tx_type = "credit"
        val = float(amt_str)
    except (ValueError, TypeError):
        return None

    if val == 0:
        return None
    if val < 0:
        tx_type = "credit"

    abs_val = abs(val)
    # Skip credit transactions unless amount is significant (>100)
    if tx_type == "credit" and abs_val <= 100:
        return None

    signed_amt = -abs_val if tx_type == "credit" else abs_val
    clean_amt = int(signed_amt) if signed_amt == int(signed_amt) else round(signed_amt, 2)

    merchant = item.get("merchant")
    if isinstance(merchant, str):
        merchant = merchant.strip() or None
    else:
        merchant = None

    upi_id = item.get("upi_id")
    if isinstance(upi_id, str):
        upi_id = upi_id.strip() or None
    else:
        upi_id = None

    date_str = _normalize_scan_date(item.get("date"), today_date)

    time_str = item.get("time")
    if isinstance(time_str, str):
        time_str = time_str.strip() or None
    else:
        time_str = None

    raw_cat = str(item.get("category") or "Other").strip().lower()
    category = VALID_SCAN_CATEGORIES.get(raw_cat, "Other")

    conf = str(item.get("confidence") or "medium").strip().lower()
    if conf not in ("high", "medium", "low"):
        conf = "medium"

    if merchant:
        if category in ("Food", "Shopping"):
            suggested_note = f"{merchant} order"
        else:
            suggested_note = f"{merchant} payment"
    else:
        suggested_note = f"{category} expense"

    return {
        "amount": clean_amt,
        "merchant": merchant,
        "upi_id": upi_id,
        "date": date_str,
        "time": time_str,
        "type": tx_type,
        "category": category,
        "confidence": conf,
        "suggested_note": suggested_note,
    }


def _parse_vision_json(raw_output: str, today_date: str) -> dict:
    """Parse and normalize JSON returned by the Groq vision model (single or list)."""
    cleaned = (raw_output or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        cleaned = match.group(0)

    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Vision output is not a JSON object")

    found = bool(data.get("found"))
    raw_text = str(data.get("raw_text") or "").strip()

    raw_txs = data.get("transactions")
    if not isinstance(raw_txs, list):
        # Fallback if model returned flat single-transaction fields
        if data.get("amount") is not None:
            raw_txs = [data]
        else:
            raw_txs = []

    parsed_txs = []
    for item in raw_txs[:20]:
        norm_item = _parse_single_tx_item(item, today_date)
        if norm_item is not None:
            parsed_txs.append(norm_item)

    if not found or not parsed_txs:
        return {
            "found": False,
            "type": "single",
            "transaction": None,
            "transactions": [],
            "count": 0,
            "confidence": str(data.get("confidence") or "low").lower(),
            "amount": None,
            "merchant": None,
            "date": None,
            "category": None,
            "raw_text": raw_text,
            "suggested_note": None,
        }

    declared_type = str(data.get("type") or "").strip().lower()
    if len(parsed_txs) > 1 or declared_type == "list":
        scan_type = "list" if len(parsed_txs) > 1 else ("list" if declared_type == "list" else "single")
    else:
        scan_type = "single"

    # Overall confidence: use first item's confidence or top-level confidence
    overall_conf = str(data.get("confidence") or parsed_txs[0].get("confidence") or "high").strip().lower()
    if overall_conf not in ("high", "medium", "low"):
        overall_conf = parsed_txs[0].get("confidence", "medium")

    first_tx = parsed_txs[0]

    if scan_type == "single":
        return {
            "found": True,
            "type": "single",
            "transaction": first_tx,
            "transactions": parsed_txs,
            "count": 1,
            "confidence": first_tx["confidence"],
            # Backward-compatible top-level single transaction fields
            "amount": abs(first_tx["amount"]),
            "merchant": first_tx["merchant"],
            "upi_id": first_tx.get("upi_id"),
            "date": first_tx["date"],
            "time": first_tx.get("time"),
            "category": first_tx["category"],
            "raw_text": raw_text,
            "suggested_note": first_tx["suggested_note"],
        }

    return {
        "found": True,
        "type": "list",
        "transaction": first_tx,
        "transactions": parsed_txs,
        "count": len(parsed_txs),
        "confidence": overall_conf,
        "raw_text": raw_text,
    }


@app.post("/api/transactions/scan")
async def transaction_scan(
    image: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Scan a single receipt/screenshot image using Groq vision and extract transaction details."""
    try:
        content = await image.read()
    except Exception as e:
        log_server_error("/api/transactions/scan", f"FileReadError: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={"detail": "Could not process image, please try again"},
        )

    is_valid, mime_type, err_msg = _validate_scan_image(image, content)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err_msg)

    increment_scan_count(1)
    today_str = d_date.today().isoformat()
    prompt = _build_vision_scan_prompt(today_str)
    image_b64 = base64.b64encode(content).decode("utf-8")

    try:
        raw_response = llm_pool.invoke_vision(
            image_base64=image_b64,
            prompt=prompt,
            mime_type=mime_type,
        )
        extracted = _parse_vision_json(raw_response, today_str)
    except Exception as e:
        logger.exception("Groq vision scan failed")
        try:
            log_server_error("/api/transactions/scan", f"{type(e).__name__}: {str(e)}")
        except Exception:
            pass
        return JSONResponse(
            status_code=503,
            content={"detail": "Could not process image, please try again"},
        )

    if not extracted.get("found"):
        return JSONResponse(
            status_code=404,
            content={
                "found": False,
                "detail": "No transaction found in this image",
                "message": "No transaction found in this image",
            },
        )

    return extracted


@app.post("/api/transactions/scan-bulk")
async def transaction_scan_bulk(
    images: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    """Scan up to 10 receipt/screenshot images sequentially using Groq vision."""
    if not images:
        raise HTTPException(status_code=400, detail="No images provided")
    if len(images) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 images allowed per bulk scan")

    today_str = d_date.today().isoformat()
    prompt = _build_vision_scan_prompt(today_str)

    results = []
    found_count = 0
    not_found_count = 0

    for idx, img in enumerate(images):
        try:
            content = await img.read()
            is_valid, mime_type, err_msg = _validate_scan_image(img, content)
            if not is_valid:
                not_found_count += 1
                results.append({
                    "index": idx,
                    "found": False,
                    "error": True,
                    "detail": err_msg,
                })
                continue

            increment_scan_count(1)
            image_b64 = base64.b64encode(content).decode("utf-8")
            raw_response = llm_pool.invoke_vision(
                image_base64=image_b64,
                prompt=prompt,
                mime_type=mime_type,
            )
            extracted = _parse_vision_json(raw_response, today_str)
            if extracted.get("found"):
                found_count += 1
            else:
                not_found_count += 1
            results.append({
                "index": idx,
                **extracted,
            })
        except Exception as e:
            logger.error(f"Bulk scan error at index {idx}: {e}")
            try:
                log_server_error("/api/transactions/scan-bulk", f"Index {idx} {type(e).__name__}: {str(e)}")
            except Exception:
                pass
            not_found_count += 1
            results.append({
                "index": idx,
                "found": False,
                "error": True,
                "detail": "Could not process image, please try again",
            })

    return {
        "results": results,
        "total": len(images),
        "found": found_count,
        "not_found": not_found_count,
    }


@app.post("/api/transactions/scan-confirm")
def transaction_scan_confirm(
    req: ScanConfirmRequest,
    user: dict = Depends(get_current_user),
):
    """Confirm and save a scanned transaction after checking for duplicates."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    if not req.category or not req.category.strip():
        raise HTTPException(status_code=400, detail="category is required")

    clean_cat = req.category.strip()
    clean_merchant = req.merchant.strip() if req.merchant and req.merchant.strip() else None
    clean_note = (req.note or "").strip()
    if not clean_note and clean_merchant:
        clean_note = f"{clean_merchant} order" if clean_cat.lower() in ("food", "shopping") else f"{clean_merchant} payment"

    existing = check_duplicate_expense(
        user_id=user["id"],
        amount=req.amount,
        category=clean_cat,
        note=clean_note,
        entry_date=req.date,
    )
    if existing:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Similar transaction already exists",
                "existing": existing,
            },
        )

    tx = log_transaction(
        user_id=user["id"],
        amount=req.amount,
        category=clean_cat,
        note=clean_note,
        raw_message="scan",
        merchant=clean_merchant,
        entry_date=req.date,
        source=req.source or "scan",
    )
    tx["tags"] = []

    try:
        check_budget_alerts(user["id"], tx["category"], tx["amount"])
        check_large_expense(user["id"], tx["amount"], tx["category"], tx.get("merchant"))
    except Exception as e:
        logger.error(f"Error triggering push alerts on scan-confirm: {e}")

    return tx


@app.get("/api/stats/scan-usage")
def stats_scan_usage(user: dict = Depends(get_current_user)):
    """Return total scanned and total confirmed counts for scan feature usage tracking."""
    return get_scan_usage_stats()


@app.post("/api/transactions")
@app.post("/api/expenses")
def transaction_create(req: TransactionCreateRequest, user: dict = Depends(get_current_user)):
    """Manually add a new transaction."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    if not req.category.strip():
        raise HTTPException(status_code=400, detail="category is required")

    tx = log_transaction(
        user_id=user["id"],
        amount=req.amount,
        category=req.category.strip(),
        note=req.note or "",
        raw_message="manual",
        merchant=req.merchant,
        entry_date=req.date,
    )
    if req.tag and req.tag.strip():
        clean_tag = req.tag.strip().lstrip("#").lower()
        add_transaction_tag(user_id=user["id"], transaction_id=tx["id"], tag=clean_tag)
        tx["tags"] = [clean_tag]
    else:
        tx["tags"] = []

    # Trigger automatic notification checks
    try:
        check_budget_alerts(user["id"], tx["category"], tx["amount"])
        check_large_expense(user["id"], tx["amount"], tx["category"], tx.get("merchant"))
    except Exception as e:
        logger.error(f"Error triggering push alerts on transaction create: {e}")

    return tx


@app.post("/api/transactions/batch")
def transactions_batch_create(
    req: BatchTransactionsRequest,
    user: dict = Depends(get_current_user),
):
    """Batch log expenses directly to the database in a single transaction."""
    if len(req.expenses) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 items allowed per batch request",
        )
    if not req.expenses:
        raise HTTPException(
            status_code=400,
            detail="No expenses provided in batch request",
        )

    errors = []
    validated_items = []
    for idx, item in enumerate(req.expenses):
        item_errors = []
        amt = None
        if item.amount is None:
            item_errors.append("amount is required")
        else:
            try:
                amt = float(item.amount)
                if amt <= 0:
                    item_errors.append(f"amount must be positive (received {item.amount})")
            except (ValueError, TypeError):
                item_errors.append(f"amount must be a valid number (received {item.amount})")

        cat = None
        if item.category is None or not str(item.category).strip():
            item_errors.append("category is required and cannot be empty")
        else:
            cat = str(item.category).strip().lower()

        if item_errors:
            errors.append(f"Item {idx}: {', '.join(item_errors)}")
        else:
            clean_note = (item.note or "").strip()
            validated_items.append({
                "amount": amt,
                "category": cat,
                "note": clean_note,
                "date": item.date or None,
                "merchant": item.merchant,
            })

    if errors:
        raise HTTPException(
            status_code=400,
            detail=f"Validation failed: {'; '.join(errors)}",
        )

    inserted_items = []
    try:
        with get_db_cursor() as cur:
            for item in validated_items:
                norm_merchant = normalize_merchant(user["id"], item["note"]) if item["note"] else None
                merchant = item["merchant"] or norm_merchant
                tx = log_transaction(
                    user_id=user["id"],
                    amount=item["amount"],
                    category=item["category"],
                    note=item["note"],
                    raw_message="batch_api",
                    merchant=merchant,
                    entry_date=item["date"],
                    cur=cur,
                )
                inserted_items.append({
                    "id": tx["id"],
                    "amount": tx["amount"],
                    "category": tx["category"],
                    "note": tx["note"],
                    "date": tx["date"],
                })
    except Exception as e:
        logger.exception(f"Error executing batch transaction insert: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error during batch insert: {str(e)}",
        )

    # Trigger notification checks
    try:
        for itm in validated_items:
            check_budget_alerts(user["id"], itm["category"], itm["amount"])
            check_large_expense(user["id"], itm["amount"], itm["category"], itm.get("merchant"))
    except Exception as e:
        logger.error(f"Error triggering push alerts on batch transaction create: {e}")

    return {
        "logged": len(inserted_items),
        "items": inserted_items,
    }


@app.get("/api/transactions")
def transactions_search(
    user: dict = Depends(get_current_user),
    text: str | None = Query(None),
    category: str | None = Query(None),
    amount_min: float | None = Query(None),
    amount_max: float | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    tag: str | None = Query(None),
    merchant: str | None = Query(None),
    month: str | None = Query(None),
    limit: int | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("date"),
    sort_order: str = Query("desc"),
):
    """Search, filter, and sort transactions with pagination."""
    import calendar as cal
    if month and not start_date and not end_date:
        start_date = f"{month}-01"
        try:
            y, m = map(int, month.split("-"))
            end_date = f"{month}-{cal.monthrange(y, m)[1]}"
        except Exception:
            pass

    actual_per_page = limit if limit is not None else per_page
    return search_transactions(
        user_id=user["id"],
        text=text,
        category=category,
        amount_min=amount_min,
        amount_max=amount_max,
        start_date=start_date,
        end_date=end_date,
        tag=tag,
        merchant=merchant,
        page=page,
        per_page=actual_per_page,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@app.put("/api/transactions/{tid}")
def transaction_update(tid: int, req: TransactionUpdateRequest, user: dict = Depends(get_current_user)):
    """Edit an existing transaction."""
    if req.amount is not None and req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    updated = update_expense(
        user_id=user["id"],
        transaction_id=tid,
        amount=req.amount,
        category=req.category,
        note=req.note,
        entry_date=req.date,
        merchant=req.merchant,
        tags=req.tags,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated


@app.delete("/api/transactions/{tid}")
def transaction_delete(tid: int, user: dict = Depends(get_current_user)):
    """Delete a single transaction."""
    ok = delete_expense(user_id=user["id"], transaction_id=tid)
    if not ok:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "ok", "deleted_id": tid}


# ---------- Merchant Correction ----------

@app.post("/api/merchant/correct")
def merchant_correct(req: MerchantCorrectionRequest, user: dict = Depends(get_current_user)):
    """Store a merchant name correction."""
    return add_merchant_alias(user["id"], req.raw_input, req.normalized_name)


# ---------- Clear & Delete Data ----------

@app.post("/api/data/clear-transactions")
def data_clear_transactions(req: ClearTransactionsRequest, user: dict = Depends(get_current_user)):
    """Clear transactions, optionally within a date range."""
    count = clear_transactions(user["id"], req.start_date, req.end_date)
    return {"cleared": count, "type": "transactions"}


@app.post("/api/data/clear-udhar")
def data_clear_udhar(user: dict = Depends(get_current_user)):
    """Clear all udhar entries."""
    count = clear_udhar(user["id"])
    return {"cleared": count, "type": "udhar"}


@app.post("/api/data/clear-everything")
def data_clear_everything(req: ClearConfirmRequest, user: dict = Depends(get_current_user)):
    """Clear everything. Requires typed confirmation 'CLEAR EVERYTHING' and prior export."""
    if req.confirmation != "CLEAR EVERYTHING":
        raise HTTPException(status_code=400, detail="Type 'CLEAR EVERYTHING' to confirm.")
    counts = clear_everything(user["id"])
    return {"status": "ok", "cleared": counts}


@app.delete("/api/data/account")
def data_delete_account(req: ClearConfirmRequest, user: dict = Depends(get_current_user)):
    """Delete the entire account. Requires typed confirmation 'DELETE MY ACCOUNT' and prior export."""
    if req.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(status_code=400, detail="Type 'DELETE MY ACCOUNT' to confirm.")
    ok = delete_account(user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "ok", "deleted": True}


@app.get("/api/data/export-all")
def data_export_all(user: dict = Depends(get_current_user)):
    """Export all user data as JSON."""
    data = export_all_data_json(user["id"])
    content = json.dumps(data, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="abt_export_{user["id"]}.json"',
            "Cache-Control": "no-cache",
        },
    )


# ---------- Onboarding ----------


@app.get("/api/onboarding/status")
def onboarding_status(user: dict = Depends(get_current_user)):
    """Check onboarding status including transactions, income, and budgets flags."""
    return get_onboarding_status(user["id"])


@app.get("/api/onboarding/defaults")
def onboarding_defaults(
    income: float | None = None,
    living_situation: str = "alone",
):
    """Deterministic budget suggestions. No auth needed, no LLM call."""
    sit = sanitize_living_situation(living_situation) or "alone"
    defaults = suggest_budget_defaults(
        monthly_income=income,
        living_situation=sit,
    )
    return {"defaults": defaults, "income": income, "living_situation": sit}


@app.post("/api/onboarding/complete")
def onboarding_complete(
    req: OnboardingCompleteRequest,
    user: dict = Depends(get_current_user),
):
    """Save onboarding budgets. Pure DB writes, zero LLM tokens."""
    sit = sanitize_living_situation(req.living_situation)
    if not sit:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid living_situation. Must be one of: {', '.join(VALID_LIVING_SITUATIONS)}",
        )
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


@app.post("/api/recurring/{expense_id}/toggle")
def recurring_toggle(expense_id: int, user: dict = Depends(get_current_user)):
    """Toggle active status of a recurring expense."""
    res = toggle_recurring_expense(user_id=user["id"], expense_id=expense_id)
    if not res:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return res


@app.put("/api/recurring/{expense_id}")
def recurring_update(expense_id: int, req: RecurringUpdateRequest, user: dict = Depends(get_current_user)):
    """Update fields of an existing recurring expense."""
    if req.amount is not None and req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    res = update_recurring_expense(
        user_id=user["id"],
        expense_id=expense_id,
        name=req.name,
        amount=req.amount,
        category=req.category,
        frequency=req.frequency,
        next_due_date=req.next_due_date,
        active=req.active,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return res


@app.delete("/api/recurring/{expense_id}")
def recurring_delete(expense_id: int, user: dict = Depends(get_current_user)):
    """Delete a recurring expense."""
    ok = delete_recurring_expense(user_id=user["id"], expense_id=expense_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return {"status": "ok", "deleted_id": expense_id}


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


# ---------- Budget Manager (Manual CRUD & Overview) ----------

@app.get("/api/budgets")
def budgets_manager_get(user: dict = Depends(get_current_user)):
    """Get all categories with monthly limits, current month spend, and rollover."""
    return {"budgets": get_budgets_manager(user_id=user["id"])}


@app.post("/api/budgets")
def budget_create(req: BudgetCreateRequest, user: dict = Depends(get_current_user)):
    """Add or set a budget for a category."""
    if req.monthly_limit < 0:
        raise HTTPException(status_code=400, detail="monthly_limit must be non-negative")
    cat = req.category.strip()
    if not cat:
        raise HTTPException(status_code=400, detail="category name is required")
    set_budget(user["id"], cat, req.monthly_limit, req.rollover_enabled)
    return {
        "status": "ok",
        "category": cat,
        "monthly_limit": req.monthly_limit,
        "rollover_enabled": bool(req.rollover_enabled),
    }


@app.patch("/api/budgets/{category}")
def budget_update(category: str, req: BudgetUpdateRequest, user: dict = Depends(get_current_user)):
    """Update monthly limit or rollover for a specific category."""
    cat = category.strip().lower()
    if req.monthly_limit is not None and req.monthly_limit < 0:
        raise HTTPException(status_code=400, detail="monthly_limit must be non-negative")
    if req.monthly_limit is not None:
        set_budget(user["id"], cat, req.monthly_limit, req.rollover_enabled)
    elif req.rollover_enabled is not None:
        set_category_rollover(user["id"], cat, req.rollover_enabled)
    return {"status": "ok", "category": cat}


@app.delete("/api/budgets/{category}")
def budget_delete(category: str, user: dict = Depends(get_current_user)):
    """Delete a budget row entirely."""
    ok = delete_budget(user["id"], category)
    if not ok:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"status": "ok", "deleted_category": category}


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


# ---------- Tier 3: Udhar Reminder Nudge ----------

@app.get("/api/udhar/person/{person_key}/reminder")
def udhar_person_reminder(person_key: str, user: dict = Depends(get_current_user)):
    """Generate deterministic reminder text and share URL for udhar debtor. Zero LLM, zero emojis."""
    try:
        data = get_udhar_reminder_data(user["id"], person_key)
        return {
            **data,
            "text": data.get("message", ""),
            "wa_link": data.get("wa_url", ""),
            "balance": data.get("net_balance", 0.0),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------- Tier 3: Cash-Flow Calendar ----------

@app.get("/api/calendar")
def calendar_view(month: str | None = None, user: dict = Depends(get_current_user)):
    """Get month grid data: recurring bills due, udhar due dates, expected income,
    and running projected balance line."""
    target_month = month.strip() if month else current_month()
    data = get_cashflow_calendar(user["id"], target_month)
    days_dict = data.get("days", {})
    days_list = [days_dict[d] for d in sorted(days_dict.keys())] if isinstance(days_dict, dict) else days_dict
    summ = data.get("summary", {})
    return {
        **data,
        "days": days_list,
        "days_dict": days_dict,
        "kpis": {
            "recurring_bills_total": summ.get("total_bills", 0.0),
            "udhar_receivable_total": summ.get("total_receivable", 0.0),
            "udhar_payable_total": summ.get("total_payable", 0.0),
            "running_balance_end": summ.get("end_balance", 0.0),
        },
    }


# ---------- Tier 3: Web Push Notifications ----------

@app.get("/api/push/vapid-key")
@app.get("/api/push/vapid-public-key")
def push_vapid_key():
    """Return the public VAPID key and key_hash for web push subscription."""
    pub = settings.VAPID_PUBLIC_KEY
    key_hash = pub[:8] if pub else ""
    return {"public_key": pub, "vapid_public_key": pub, "key_hash": key_hash}


@app.get("/api/push/subscription-status")
def push_subscription_status(user: dict = Depends(get_current_user)):
    """Check if the current authenticated user has any active push subscriptions."""
    subs = get_user_push_subscriptions(user["id"])
    count = len(subs)
    return {
        "has_subscription": count > 0,
        "subscription_count": count,
    }


@app.post("/api/push/subscribe")
def push_subscribe(req: PushSubscribeRequest, user: dict = Depends(get_current_user)):
    """Register or update a browser Web Push subscription."""
    if get_app_setting("push_notifications_enabled", "true").lower() != "true":
        raise HTTPException(status_code=403, detail="Push notifications are currently disabled by administrator")

    endpoint = req.endpoint
    keys = req.keys or {}
    if req.subscription and isinstance(req.subscription, dict):
        if not endpoint:
            endpoint = req.subscription.get("endpoint")
        if not keys:
            keys = req.subscription.get("keys", {})

    if not endpoint:
        raise HTTPException(status_code=400, detail="Missing push endpoint.")

    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")
    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Missing p256dh or auth in push keys.")

    sub = save_push_subscription(
        user_id=user["id"],
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        preferences=req.preferences,
    )
    _safe_print(f"📱 New subscription saved for user {user['id']}")
    return {"status": "ok", "subscription": sub}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(req: PushUnsubscribeRequest, user: dict = Depends(get_current_user)):
    """Unsubscribe a browser push endpoint."""
    ok = remove_push_subscription(req.endpoint)
    return {"status": "ok", "removed": ok}


@app.post("/api/push/fcm-token")
def register_fcm_token(req: FcmTokenRequest, user: dict = Depends(get_current_user)):
    """Register or update an Android FCM token in push_subscriptions with type='fcm'."""
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing or empty FCM token.")
    sub = save_fcm_token(user_id=user["id"], token=token, platform=req.platform)
    _safe_print(f"📱 FCM token registered for user {user['id']} (platform={req.platform})")
    return {"status": "ok", "subscription": sub}


@app.get("/api/push/debug")
def push_debug(user: dict = Depends(get_current_user)):
    """Debug endpoint for VAPID configuration, FCM, and push subscriptions."""
    vapid_pub = (os.environ.get("VAPID_PUBLIC_KEY") or settings.VAPID_PUBLIC_KEY or "").strip().strip('"\'')
    vapid_priv = (os.environ.get("VAPID_PRIVATE_KEY") or settings.VAPID_PRIVATE_KEY or "").strip().strip('"\'')
    fcm_configured = bool(settings.FIREBASE_SERVICE_ACCOUNT_JSON)

    total_subs = 0
    user_subs = 0
    last_created = None

    from app.db import get_db_cursor

    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM push_subscriptions;")
        total_subs = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM push_subscriptions WHERE user_id = %s;", (user["id"],))
        user_subs = cur.fetchone()["cnt"]

        cur.execute("SELECT created_at FROM push_subscriptions ORDER BY created_at DESC LIMIT 1;")
        row = cur.fetchone()
        if row and row.get("created_at"):
            last_created = row["created_at"].isoformat()

    return {
        "vapid_public_key_set": bool(vapid_pub),
        "vapid_private_key_set": bool(vapid_priv),
        "fcm_configured": fcm_configured,
        "subscriptions_count": total_subs,
        "user_subscriptions": user_subs,
        "last_subscription_created": last_created,
    }


@app.post("/api/push/test")
def push_test_trigger(user: dict = Depends(get_current_user)):
    """Send a test push notification to user's registered devices (FCM or Web Push)."""
    subs = get_user_push_subscriptions(user["id"])
    _safe_print(f"🔔 /api/push/test called for user {user['id']} ({user.get('email')}), found {len(subs)} subscription(s)")
    if not subs:
        return {
            "status": "no_subscribers",
            "message": "No active subscriptions. Please enable notifications first.",
            "sent": 0,
        }

    sent = 0
    failed = 0
    last_error = ""
    for s in subs:
        sub_type = (s.get("type") or "web").lower()
        if sub_type == "fcm":
            success, err = send_fcm_notification(
                token=s["endpoint"],
                title="SAARTH Alert",
                body="Test notification received successfully. Your SAARTH alerts are active.",
                url="/",
                tag="test-alert",
            )
            if success:
                sent += 1
            else:
                failed += 1
                last_error = err or "FCM delivery failed"
        else:
            sub_info = {
                "endpoint": s["endpoint"],
                "keys": {
                    "p256dh": s["p256dh"],
                    "auth": s["auth"],
                },
            }
            try:
                success, code, err = send_web_push(
                    subscription_info=sub_info,
                    title="SAARTH Alert",
                    body="Test notification received successfully. Your SAARTH alerts are active.",
                    url="/",
                    tag="test-alert",
                )
                if success:
                    sent += 1
                else:
                    failed += 1
                    last_error = err or f"HTTP {code}"
            except WebPushException as ex:
                failed += 1
                status_code = ex.response.status_code if ex.response is not None else 0
                resp_text = ex.response.text if ex.response is not None else ""
                last_error = f"WebPushException HTTP {status_code}: {resp_text or str(ex)}"
            except Exception as ex:
                failed += 1
                last_error = str(ex)

    if sent == 0 and failed > 0:
        raise HTTPException(
            status_code=500,
            detail=f"Push notification delivery failed: {last_error}",
        )

    return {"status": "ok", "sent": sent, "failed": failed}


def run_engagement_notifications() -> dict:
    """Evaluate and dispatch engagement notifications to all eligible users.
    Returns: {"processed": processed_count, "sent": sent_count, "skipped": skipped_count}
    """
    eligible_users = get_users_for_engagement_notifications()
    now = datetime.now(timezone.utc)
    month = current_month()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_elapsed = now.day
    day_of_year = now.timetuple().tm_yday
    week_of_year = now.isocalendar()[1]

    processed = 0
    sent = 0
    skipped = 0

    for user in eligible_users:
        processed += 1
        user_id = user["user_id"]
        push_subs = user.get("push_subscriptions", [])
        if not push_subs:
            skipped += 1
            continue

        # Skip check 1: Active in the last 2 hours
        last_login = user.get("last_login_at")
        if last_login is not None:
            if last_login.tzinfo is None:
                last_login = last_login.replace(tzinfo=timezone.utc)
            if 0 <= (now - last_login).total_seconds() < 2 * 3600:
                logger.info(f"[ENGAGEMENT] Skipping user {user_id}: active within last 2 hours")
                skipped += 1
                continue

        # Skip check 2: Already received any engagement notification today
        if has_engagement_notification_today(user_id):
            logger.info(f"[ENGAGEMENT] Skipping user {user_id}: already received engagement notification today")
            skipped += 1
            continue

        notification_to_send = None

        # --- Rule 1: no_budget_set ---
        created_at = user.get("created_at")
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_over_1_day = bool(created_at and (now - created_at).total_seconds() > 86400)

        if not user.get("has_budgets") and created_over_1_day:
            notification_to_send = {
                "type": "no_budget_set",
                "title": "SAARTH is ready for you",
                "body": "You haven't set your budgets yet. It takes 2 minutes and helps SAARTH guide you better. Set them now.",
                "url": "/settings",
            }

        # --- Rule 2: no_transactions_this_month ---
        if not notification_to_send:
            if user.get("transaction_count_this_month", 0) == 0 and user.get("has_budgets") and now.day >= 3:
                notification_to_send = {
                    "type": "no_transactions_this_month",
                    "title": "How's the month going?",
                    "body": "You haven't logged any spends this month yet. Tell SAARTH what you've spent and it'll tell you where you stand.",
                    "url": "/dashboard",
                }

        # --- Rule 3: re_engagement (inactive user) ---
        if not notification_to_send:
            ref_date = last_login if last_login is not None else created_at
            if ref_date and (now - ref_date).total_seconds() > 3 * 86400:
                bodies = [
                    "SAARTH has been keeping your data safe. Come back and see where your money stands this month.",
                    "Your budgets are waiting. A quick check-in with SAARTH takes less than a minute.",
                    "Did you know SAARTH can tell you exactly how much you can safely spend today? Open the app to find out.",
                    "Your financial goals aren't going to track themselves. SAARTH missed you.",
                    "Small check-ins lead to big savings. SAARTH is ready when you are.",
                ]
                notification_to_send = {
                    "type": "re_engagement",
                    "title": "It's been a while",
                    "body": bodies[day_of_year % 5],
                    "url": "/",
                }

        # --- Rule 4: goal_behind_pace ---
        if not notification_to_send and user.get("has_goals"):
            goals = get_goals(user_id)
            expected_fraction = (days_elapsed / days_in_month) - 0.1
            for g in goals:
                tgt = float(g.get("target_amount") or 0.0)
                saved = float(g.get("saved_amount") or 0.0)
                if tgt > 0:
                    if (saved / tgt) < expected_fraction:
                        notification_to_send = {
                            "type": "goal_behind_pace",
                            "title": "Your goal needs attention",
                            "body": "You're behind pace on one of your savings goals. SAARTH can show you how to catch up.",
                            "url": "/goals",
                        }
                        break

        # --- Rule 5: over_budget_alert ---
        if not notification_to_send and user.get("has_budgets"):
            effective_budgets = get_effective_budgets(user_id, month)
            spends = spend_by_category(user_id, month)
            is_over_90 = False
            for cat, binfo in effective_budgets.items():
                limit = float(binfo.get("effective_budget") or binfo.get("base_limit") or 0.0)
                if limit > 0 and spends.get(cat, 0.0) > limit * 0.9:
                    is_over_90 = True
                    break
            if is_over_90 and not has_budget_alert_today(user_id):
                notification_to_send = {
                    "type": "over_budget_alert",
                    "title": "Heads up on your spending",
                    "body": "You're close to or over budget in one of your categories. Open SAARTH to see where and adjust.",
                    "url": "/dashboard",
                }

        # --- Rule 6: positive_reinforcement ---
        if not notification_to_send:
            last_login_within_24h = last_login is not None and (now - last_login).total_seconds() <= 86400
            tx_count = user.get("transaction_count_this_month", 0)
            if last_login_within_24h and tx_count >= 5 and user.get("has_budgets"):
                effective_budgets = get_effective_budgets(user_id, month)
                spends = spend_by_category(user_id, month)
                all_within = True
                for cat, binfo in effective_budgets.items():
                    limit = float(binfo.get("effective_budget") or binfo.get("base_limit") or 0.0)
                    if limit > 0 and spends.get(cat, 0.0) > limit:
                        all_within = False
                        break
                if all_within and not has_engagement_type_within_days(user_id, "positive_reinforcement", 7):
                    bodies_pos = [
                        "You're on track this month. Keep it up and SAARTH will help you finish strong.",
                        "Great consistency! Logging your spends regularly is the single best financial habit you can build.",
                        "All your categories are within budget. SAARTH is proud of you.",
                    ]
                    notification_to_send = {
                        "type": "positive_reinforcement",
                        "title": "You're doing great",
                        "body": bodies_pos[week_of_year % 3],
                        "url": "/insights",
                    }

        if not notification_to_send:
            skipped += 1
            continue

        # Send notification to all registered subscriptions for this user
        user_sent = False
        for s in push_subs:
            sub_info = {
                "endpoint": s["endpoint"],
                "type": s.get("type", "web"),
                "keys": {
                    "p256dh": s.get("p256dh", ""),
                    "auth": s.get("auth", ""),
                },
            }
            success, code, err = send_engagement_notification(
                subscription_info=sub_info,
                title=notification_to_send["title"],
                body=notification_to_send["body"],
                url=notification_to_send["url"],
            )
            if success:
                user_sent = True
            else:
                if code in (404, 410):
                    print(f"[PUSH] Pruning expired/invalid subscription {s['endpoint']} (HTTP {code})")
                    remove_push_subscription(s["endpoint"])

        if user_sent:
            log_engagement_notification(user_id, notification_to_send["type"])
            print(f"[ENGAGEMENT] Sent {notification_to_send['type']} notification to user {user_id}")
            sent += 1
        else:
            skipped += 1

    return {"processed": processed, "sent": sent, "skipped": skipped}


@app.post("/api/push/trigger-engagement")
def push_trigger_engagement(admin: dict = Depends(get_current_admin)):
    """Manually trigger the engagement notification process for all eligible users (Admin only)."""
    return run_engagement_notifications()



# ---------- App Status (Public) ----------

@app.get("/api/app-status")
def app_status():
    """Return live maintenance mode and feature flag status."""
    return {
        "maintenance_mode": get_app_setting("maintenance_mode", "false").lower() == "true",
        "features": {
            "push_notifications": get_app_setting("push_notifications_enabled", "true").lower() == "true",
            "csv_import": get_app_setting("csv_import_enabled", "true").lower() == "true",
            "receipt_upload": get_app_setting("receipt_upload_enabled", "true").lower() == "true",
        },
    }


# ---------- Admin API Endpoints ----------

@app.post("/api/admin/login")
def admin_login(req: AdminLoginRequest, response: Response, request: Request):
    """Authenticate admin user using environment-configured credentials."""
    email_clean = req.email.strip().lower()
    admin_email_clean = settings.ADMIN_EMAIL.strip().lower()
    if email_clean != admin_email_clean or not verify_password(req.password, settings.ADMIN_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )
    token = create_admin_token(settings.ADMIN_EMAIL)

    # Admin session cookie
    response.set_cookie(
        key="admin_token",
        value=token,
        domain=".saarthh.in",
        secure=True,
        samesite="None",
        httponly=True,
        max_age=30 * 24 * 60 * 60,
        path="/",
    )

    # Set explicit CORS response headers for admin login
    origin = request.headers.get("origin")
    if origin and (origin in ADMIN_ALLOWED_ORIGINS or origin in allowed_origins):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"

    return {"token": token, "email": settings.ADMIN_EMAIL, "role": "admin"}


@app.post("/api/admin/logout")
def admin_logout(response: Response):
    """Clear admin session cookie."""
    response.delete_cookie(
        key="admin_token",
        domain=".saarthh.in",
        path="/",
        secure=True,
        samesite="None",
        httponly=True,
    )
    response.delete_cookie(
        key="admin_token",
        path="/",
        secure=True,
        samesite="None",
        httponly=True,
    )
    return {"status": "ok", "message": "Admin logged out successfully"}


@app.get("/api/admin/dashboard")
def admin_dashboard(admin: dict = Depends(get_current_admin)):
    """Admin overview metrics, registration trend, LLM key pool status, and recent errors."""
    stats = get_admin_dashboard_stats()
    pool_status = llm_pool.get_pool_status()
    recent_errors = get_recent_server_errors(10)
    return {
        "stats": stats,
        "llm_pool": pool_status,
        "recent_errors": recent_errors,
    }


@app.get("/api/admin/users")
def admin_users_list(
    search: str = "",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 25,
    admin: dict = Depends(get_current_admin),
):
    """Searchable, paginated, sortable users list for admin."""
    return get_admin_users(
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@app.get("/api/admin/users/{user_id}")
def admin_user_detail(user_id: int, admin: dict = Depends(get_current_admin)):
    """Get details for a single user (no notes or chat messages)."""
    detail = get_admin_user_detail(user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="User not found")
    return detail


@app.post("/api/admin/users/{user_id}/suspend")
def admin_user_suspend(user_id: int, req: AdminSuspendRequest, admin: dict = Depends(get_current_admin)):
    """Suspend or unsuspend user account."""
    ok = set_user_suspended(user_id, req.suspended)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "ok", "user_id": user_id, "suspended": req.suspended}


@app.post("/api/admin/users/{user_id}/force-reset")
def admin_user_force_reset(user_id: int, req: AdminForceResetRequest, admin: dict = Depends(get_current_admin)):
    """Flag user account for mandatory password reset on next login."""
    ok = set_user_force_password_reset(user_id, req.force)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "ok", "user_id": user_id, "force_password_reset": req.force}


@app.delete("/api/admin/users/{user_id}")
def admin_user_delete(user_id: int, req: AdminDeleteUserRequest, admin: dict = Depends(get_current_admin)):
    """Delete user and all associated data/storage. Requires confirming target email."""
    from app.db import get_user_by_id
    target_user = get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    if req.confirm_email.strip().lower() != target_user["email"].strip().lower():
        raise HTTPException(status_code=400, detail="Confirmation email does not match user email")
    deleted = delete_account(user_id)
    return {"status": "ok", "deleted": deleted}


@app.get("/api/admin/llm-usage")
def admin_llm_usage(admin: dict = Depends(get_current_admin)):
    """30-day message counts and top 5 users."""
    return get_admin_llm_usage()


@app.get("/api/admin/tables")
def admin_tables_overview(admin: dict = Depends(get_current_admin)):
    """List tables available for read-only inspection and their row counts."""
    return {"tables": get_admin_table_overview()}


@app.get("/api/admin/tables/{table_name}")
def admin_table_rows(
    table_name: str,
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    admin: dict = Depends(get_current_admin),
):
    """Read-only paginated inspection for an explorer table."""
    try:
        return get_admin_table_rows(table_name, search=search, page=page, page_size=page_size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/admin/settings")
def admin_settings_get(admin: dict = Depends(get_current_admin)):
    """Fetch all live app settings."""
    return {"settings": get_app_settings(force_refresh=True)}


@app.put("/api/admin/settings")
def admin_settings_update(settings_dict: dict, admin: dict = Depends(get_current_admin)):
    """Update app settings in database."""
    for k, v in settings_dict.items():
        set_app_setting(str(k), str(v))
    return {"status": "ok", "settings": get_app_settings(force_refresh=True)}


# ---------- App Version Management ----------

@app.get("/api/app/version", response_model=AppVersionResponse)
def get_app_version_endpoint(platform: str = "android"):
    """Get latest published app version configuration (no auth required)."""
    return get_app_version(platform=platform)


@app.get("/api/admin/app/version", response_model=AppVersionResponse)
def admin_get_app_version_endpoint(platform: str = "android", admin: dict = Depends(get_current_admin)):
    """Fetch current app version configuration for admin portal (admin auth required)."""
    return get_app_version(platform=platform)


@app.post("/api/admin/app/version", response_model=AppVersionResponse)
def admin_update_app_version_endpoint(
    req: AppVersionUpdateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Publish a new app version configuration (admin auth required)."""
    if not req.version or not req.version.strip():
        raise HTTPException(status_code=400, detail="Version string is required")
    if not req.download_url or not req.download_url.strip():
        raise HTTPException(status_code=400, detail="Download URL is required")

    return set_app_version(
        platform=req.platform.strip() if req.platform else "android",
        version=req.version.strip(),
        download_url=req.download_url.strip(),
        changelog=req.changelog.strip() if req.changelog else "",
        is_forced=bool(req.is_forced),
    )


# ---------- SMS Ingestion (Capacitor Android) ----------

@app.post("/api/sms/ingest")
async def ingest_sms(
    payload: SmsIngestPayload,
    user: dict = Depends(get_current_user),
):
    """Ingest bank transaction SMS from Capacitor Android app."""
    items = []
    if payload.batch and isinstance(payload.batch, list):
        items = payload.batch
    elif payload.sms and isinstance(payload.sms, list):
        items = payload.sms
    elif payload.body:
        items = [{"sender": payload.sender or "", "body": payload.body, "timestamp": payload.timestamp}]

    imported_count = 0
    duplicate_count = 0
    from datetime import date as d_date

    amt_pattern = re.compile(r"(?:rs\.?|inr|\u20b9)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
    debit_keywords = ("debited", "spent", "paid", "sent", "withdrawn", "dr", "purchase")
    credit_keywords = ("credited", "received", "cr", "deposited", "refund")

    for item in items:
        if not isinstance(item, dict):
            continue
        body = item.get("body", "").strip()
        if not body:
            continue
        sender = item.get("sender", "").strip()
        body_lower = body.lower()
        m = amt_pattern.search(body)
        if not m:
            continue
        try:
            amt = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        is_credit = any(k in body_lower for k in credit_keywords) and not any(k in body_lower for k in debit_keywords)
        d_str = d_date.today().isoformat()
        desc = sender or body[:60]
        norm_merchant = normalize_merchant(user["id"], desc) if desc else ""
        merchant_name = norm_merchant or desc

        if not is_credit and amt > 0:
            dup = check_duplicate_expense(user["id"], amt, "", merchant_name, d_str)
            if dup:
                duplicate_count += 1
                continue

            log_transaction(
                user_id=user["id"],
                amount=amt,
                category="Other",
                note=desc[:200],
                raw_message=f"SMS from {sender}: {body}"[:500],
                merchant=merchant_name,
                entry_date=d_str,
            )
            imported_count += 1

    return {"status": "ok", "imported": imported_count, "duplicates": duplicate_count}


# ---------- Global Unhandled Error Handler ----------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled server exception on %s", request.url.path)
    try:
        # Never log user body/params -- only route path and clean error string
        log_server_error(request.url.path, f"{type(exc).__name__}: {str(exc)}")
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ---------- Frontend ----------

# Mount static assets (CSS, JS, images, manifest)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/admin")
@app.get("/admin/{path:path}")
def serve_admin(path: str = ""):
    """Serve the dedicated admin panel SPA."""
    admin_path = FRONTEND_DIR / "admin.html"
    if admin_path.exists():
        return FileResponse(str(admin_path))
    return JSONResponse(status_code=404, content={"detail": "Admin panel not found"})


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


@app.get("/icon-192.png")
def serve_icon_192():
    return FileResponse(str(FRONTEND_DIR / "icon-192.png"), media_type="image/png")


@app.get("/icon-512.png")
def serve_icon_512():
    return FileResponse(str(FRONTEND_DIR / "icon-512.png"), media_type="image/png")


@app.get("/download")
def serve_download():
    """Serve the Android APK download page."""
    dl_path = FRONTEND_DIR / "download.html"
    if dl_path.exists():
        return FileResponse(str(dl_path), media_type="text/html")
    return FileResponse(str(FRONTEND_DIR / "index.html"), media_type="text/html")


@app.get("/download/latest")
def download_latest_apk():
    """Directly redirect to the latest Android APK download URL."""
    fallback_apk = "https://github.com/Vanshivtech/Budget_tracker/releases/download/v1.0.2/saarth-release.apk"
    try:
        ver_info = get_app_version("android")
        download_url = ver_info.get("download_url") if isinstance(ver_info, dict) else None
        if download_url and download_url.strip() and "saarth-v1.0.0.apk" not in download_url:
            return RedirectResponse(url=download_url.strip(), status_code=302)
    except Exception as e:
        logger.warning(f"Error resolving latest APK download URL: {e}")
    return RedirectResponse(url=fallback_apk, status_code=302)


@app.get("/")
@app.get("/login")
@app.get("/settings")
@app.get("/dashboard")
@app.get("/goals")
@app.get("/insights")
def serve_frontend():
    """Serve the single-page frontend."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))
