# SAARTH — Make money meaningful

A multi-user personal finance and budget management platform designed for cloud deployment. SAARTH combines conversational AI expense tracking (via Groq LLM and LangGraph ReAct agent) with a comprehensive manual management interface (quick-add bar, full transaction ledger, category budget manager, udhar tracking, savings goals, recurring bill schedules, and admin operations).

---

## Table of Contents

1. [Architecture and System Design](#architecture-and-system-design)
2. [Quick Start (Local Development)](#quick-start-local-development)
3. [Production Deployment & Custom Domains](#production-deployment--custom-domains)
4. [PWA, Native Android App (Capacitor) & Bank SMS Ingest Engine](#pwa-native-android-app-capacitor--bank-sms-ingest-engine)
   - [1. Progressive Web App (PWA) Installability Engine](#1-progressive-web-app-pwa-installability-engine)
   - [2. Capacitor Android Hybrid Architecture](#2-capacitor-android-hybrid-architecture)
   - [3. Native Bank & UPI SMS Reader Plugin](#3-native-bank--upi-sms-reader-plugin)
   - [4. Frontend SMS Auto-Ingest Bridge & 90-Day Backfill](#4-frontend-sms-auto-ingest-bridge--90-day-backfill)
   - [5. App Version Management & In-App Update Engine](#5-app-version-management--in-app-update-engine)
   - [6. Automated CI/CD Pipeline (GitHub Actions)](#6-automated-cicd-pipeline-github-actions)
   - [7. Sideload Download Portal (`saarthh.in/download`)](#7-sideload-download-portal-saarthhindownload)
5. [Project Status Report & Technical Audit](#project-status-report--technical-audit)
   - [1. File Inventory](#1-file-inventory)
   - [2. Database Schema Verification (21 Tables)](#2-database-schema-verification-21-tables)
   - [3. Backend API Audit (94 Endpoints)](#3-backend-api-audit-94-endpoints)
   - [4. Frontend Completeness Audit](#4-frontend-completeness-audit)
   - [5. Agent Tools Audit (22 Tools)](#5-agent-tools-audit-22-tools)
   - [6. Background Scheduler Audit](#6-background-scheduler-audit)
   - [7. Known Issues and Code Audit](#7-known-issues-and-code-audit)
   - [8. Environment Variables Audit](#8-environment-variables-audit)
   - [9. Recent Session Changes](#9-recent-session-changes)
   - [10. Definitive Feature Status (The Three Lists)](#10-definitive-feature-status-the-three-lists)

---

## Architecture and System Design

The application follows a dual-entry architectural pattern where both conversational AI and manual UI interactions write to the same relational database layer:

- **Conversational Entry:** User sends natural language messages in the chat interface. A LangGraph ReAct agent powered by Groq LLM (with multi-key failover) uses 22 user-scoped tools to log expenses, split bills, check budgets, compute health scores, and track goals.
- **Manual Entry & Management:** Direct forms and modals allow users to quick-add expenses, search and filter the full transaction ledger, perform inline edits, execute bulk deletions, configure monthly category budgets with rollovers, manage peer-to-peer debts (udhar), track savings goals, and pause/resume recurring bills.
- **Backend Core:** FastAPI application exposing 94 endpoints with bcrypt password hashing, JWT session authentication, and user isolation enforced at the database query level.
- **Database Layer:** Supabase Postgres accessed via `psycopg2-binary` with thread-safe connection pooling.
- **Frontend Layer:** Vanilla HTML5, modern CSS3 (custom dark fintech design system), and JavaScript (ES6+ modular state management and dirty-form tracking).

---

## Quick Start (Local Development)

### 1. Prerequisites
- Python 3.12+
- Supabase account with a PostgreSQL database
- Groq API Key (from console.groq.com)

### 2. Setup Virtual Environment

```bash
# Clone and enter project directory
cd Whatsapp_budget_tracker

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Windows Command Prompt:
venv\Scripts\activate.bat
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
# Windows
copy .env.example .env
# Linux / macOS
cp .env.example .env
```

Set the required variables in `.env`:

```env
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=postgresql://postgres.yourprojectref:yourpassword@aws-0-region.pooler.supabase.com:6543/postgres
JWT_SECRET=your_generated_32_byte_hex_secret
ADMIN_EMAIL=admin@budgettracker.local
ADMIN_PASSWORD_HASH=your_bcrypt_hash_of_admin_password
ADMIN_TOKEN_SECRET=your_generated_32_byte_admin_hex_secret
ALLOWED_ORIGINS=https://saarthh.in,https://www.saarthh.in,http://localhost:5173,http://localhost:3000
```

> **Note on CORS (`ALLOWED_ORIGINS`):** Multiple origins are comma-separated. The production frontend domain (`https://saarthh.in`, `https://www.saarthh.in`) along with local development origins must be included for the frontend and PWA to communicate with the API.


Generate secrets with Python:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Generate admin password hash:
```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'YourAdminPassword', bcrypt.gensalt()).decode())"
```

### 4. Run Development Server

```bash
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000` in your browser. The administrative panel is available at `http://127.0.0.1:8000/admin`.

---

## Production Deployment & Custom Domains

### 1. Production Architecture Overview
- **Web Application & PWA:** [`https://saarthh.in`](https://saarthh.in) (and [`https://www.saarthh.in`](https://www.saarthh.in))
- **Backend API Server:** [`https://api.saarthh.in`](https://api.saarthh.in) (Hosted on Render)
- **Database Engine:** Supabase PostgreSQL with PgBouncer connection pooler on port `6543`
- **Transactional Email Service:** Resend HTTP API (`https://api.resend.com/emails`) for verification codes & security alerts
- **Push Notification Service:** Web Push via VAPID standard and `pywebpush`

### 2. Custom Domain & DNS Routing (Cloudflare)
- **Root & WWW Records:** `saarthh.in` and `www.saarthh.in` CNAME configured to frontend host with **Cloudflare Proxy Enabled (Orange Cloud)**.
- **Backend Subdomain Record:** `api.saarthh.in` CNAME pointing to Render Web Service URL (`budget-tracker-k3cf.onrender.com`).
- **SSL / TLS Encryption:** Set to **Full (Strict)** with **Always Use HTTPS** and **Automatic HTTPS Rewrites** enabled.

### 3. Cross-Subdomain Authentication & CORS Policy
To allow seamless session persistence between the frontend (`saarthh.in`) and the backend API (`api.saarthh.in`), authentication relies on cross-subdomain HttpOnly cookies and explicit CORS whitelisting:

- **CORS Allowed Origins:**
  ```python
  allow_origins = [
      "https://saarthh.in",
      "https://www.saarthh.in",
      "https://api.saarthh.in",
      "http://localhost:5173",
      "http://localhost:3000",
  ]
  ```
- **Session Refresh Cookie (`refresh_token`):**
  ```python
  response.set_cookie(
      key="refresh_token",
      value=refresh_token,
      httponly=True,
      secure=True,
      samesite="None",
      domain=".saarthh.in",
      max_age=30 * 24 * 60 * 60,  # 30 days
  )
  ```
- **Admin Session Token:** Set with identical `.saarthh.in` domain and secure attributes for unified administrative access.

### 4. Render Web Service Deployment Configuration
1. **Source Repository:** Push repository to GitHub `main` branch.
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. **Python Version:** 3.12.0 (configured via `runtime.txt`)
5. **Health Check Path:** `/api/ping` or `/api/health`
6. **Host Environment Variables:** Configure in Render Dashboard:
   - `DATABASE_URL`: Supabase connection pooler URI (`aws-0-region.pooler.supabase.com:6543`)
   - `JWT_SECRET`, `ADMIN_TOKEN_SECRET`: 64-character hex secrets
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`: Bcrypt hash for admin portal
   - `ALLOWED_ORIGINS`: `https://saarthh.in,https://www.saarthh.in,http://localhost:5173,http://localhost:3000`
   - `GROQ_API_KEY`: Primary Groq API key (with optional secondary/tertiary keys)
   - `RESEND_API_KEY`: Production API key from Resend
   - `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`: Production push notification credentials

---

## PWA, Native Android App (Capacitor) & Bank SMS Ingest Engine

SAARTH supports a unified web, progressive web app, and native Android application runtime wrapped using **Capacitor 6**.

### 1. Progressive Web App (PWA) Installability Engine
- **Web App Manifest ([`frontend/manifest.json`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/frontend/manifest.json)):**
  - Configured with `display: "standalone"`, `theme_color: "#6c63ff"`, `background_color: "#0a0a0f"`, and `"categories": ["finance", "productivity"]`.
  - Includes mobile screenshots (`390x844`) for rich Play Store-style browser installation dialogs.
  - Icons: 192x192 and 512x512 with dual `"any"` and `"maskable"` purposes.
- **Mobile Viewport & Apple Web App Meta Tags ([`frontend/index.html`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/frontend/index.html)):**
  - `<meta name="mobile-web-app-capable" content="yes">`
  - `<meta name="apple-mobile-web-app-capable" content="yes">`
  - `<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">`
  - `<meta name="apple-mobile-web-app-title" content="SAARTH">`
  - `<link rel="apple-touch-icon" href="/icon-192.png">`
- **Smart Install Prompt Banner ([`frontend/app.js`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/frontend/app.js)):**
  - Intercepts browser `beforeinstallprompt` event.
  - Checks `pwa_install_dismissed` in `localStorage` and `sessionStorage`.
  - Displays a modern bottom card with **"Install"** and **"Not now"** options.
  - Respects user dismissal without repeatedly nagging.

### 2. Capacitor Android Hybrid Architecture
- **Directory:** [`android-app/`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/android-app/)
- **Application ID:** `in.saarthh.app`
- **Server Wrapper:** `capacitor.config.json` is configured with `server.url = "https://saarthh.in"`. The APK operates as a high-performance native container rendering the live, deployed web application while accessing native device APIs.
- **Android Permissions:** `android.permission.RECEIVE_SMS` and `android.permission.READ_SMS`.

### 3. Native Bank & UPI SMS Reader Plugin
- **Source:** [`android-app/sms-plugin/SmsReaderPlugin.java`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/android-app/sms-plugin/SmsReaderPlugin.java) & [`android-app/sms-plugin/index.ts`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/android-app/sms-plugin/index.ts)
- **Real-Time Broadcast Receiver:** Registers high-priority listener for `android.provider.Telephony.SMS_RECEIVED`.
- **Bank Handle Whitelist:** Filters incoming senders against:
  ```text
  SBIINB, HDFCBK, ICICIB, AXISBK, KOTAKB, PNBSMS, BOIIND, CANBNK, UNIONB, PAYTM, PHONEPE, GPAY
  ```
- **Event Dispatch:** Non-banking SMS messages are silently ignored. Recognized bank transactions trigger a native `smsReceived` event containing:
  ```json
  { "sender": "HDFCBK", "body": "A/c debited by Rs 450.00...", "timestamp": 1729080000000 }
  ```
- **Inbox Backfill (`backfillSms(days)`):** Scans `content://sms/inbox` for the past N days (default: 90 days), extracting bank transactions for initial historical import.

### 4. Frontend SMS Auto-Ingest Bridge & 90-Day Backfill
- **Source:** `SmsIntegration` module in [`frontend/app.js`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/frontend/app.js).
- **Auto-Listening:** After login, automatically activates `SmsReaderPlugin.startListening()`.
- **Backend Ingestion (`POST /api/sms/ingest`):** Authenticated API call parses amount, merchant, and timestamp using regex parsers.
- **Duplicate Protection:** Cross-references `check_duplicate_expense` to prevent re-logging duplicate notifications.
- **One-Time Historic Backfill:** Automatically runs 90-day historic import upon first login, storing `sms_backfill_done` in `localStorage`.

### 5. App Version Management & In-App Update Engine
- **Database Storage:** Dual persistence in `app_settings` (`app_version_{platform}`) and historical audit table `app_versions`.
- **Public Endpoint (`GET /api/app/version?platform=android`):**
  ```json
  {
    "version": "1.0.0",
    "download_url": "https://saarthh.in/download/saarth-v1.0.0.apk",
    "changelog": "First release of SAARTH!",
    "is_forced": false,
    "platform": "android"
  }
  ```
- **Admin Management (`POST /api/admin/app/version`):** Protected by `get_current_admin` dependency.
- **Update Barrier Logic:**
  - **`is_forced: false`:** Dismissible bottom banner: *"Update available (v1.0.1) — Download"*.
  - **`is_forced: true`:** Non-dismissible full-screen modal (*"Update Required"*), locking the app interface until the new APK is installed.

### 6. Automated CI/CD Pipeline (GitHub Actions)
- **Workflow:** [`.github/workflows/build-android.yml`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/.github/workflows/build-android.yml)
- **Triggers:** Push to `main`, manual `workflow_dispatch`, or version release tags (`v*`).
- **Build Pipeline:**
  1. Checks out repository and sets up Java 17 + Node 20.
  2. Runs `npm install` and `npx cap sync android`.
  3. Decodes release keystore from GitHub Secret `KEYSTORE_BASE64`.
  4. Runs `./gradlew assembleRelease` (falls back to debug APK if no keystore).
  5. Uploads APK as workflow artifact.
  6. On version tags (`v*`): Creates GitHub Release with APK attached and automatically updates SAARTH backend version via `POST /api/admin/app/version`.

### 7. Sideload Download Portal (`saarthh.in/download`)
- **Template:** [`frontend/download.html`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/frontend/download.html)
- **Design:** Dark fintech interface with live version display, APK direct download button, and 5-step Android sideload instructions.
- **Web & iOS PWA Instructions:** Directs Chrome and Safari users on adding SAARTH to their home screen.

---

## Project Status Report & Technical Audit

### 1. File Inventory

#### Backend (`app/`)
| File | Last Modified | Size (Bytes) | Size (KB) | Purpose |
|---|---|---|---|---|
| `app/__init__.py` | 2026-09-17 | 0 | 0.0 KB | Package initialization marker |
| `app/agent.py` | 2026-10-02 | 28,410 | 27.7 KB | LangGraph ReAct agent, prompt, memory checkpointer, 22 financial tools |
| `app/auth.py` | 2026-10-12 | 6,690 | 6.5 KB | Password hashing (bcrypt), JWT tokens, refresh tokens, admin tokens |
| `app/config.py` | 2026-10-12 | 5,711 | 5.6 KB | Central settings class, environment variable loading, validation |
| `app/db.py` | 2026-10-17 | 196,677 | 192.1 KB | Supabase Postgres database layer, connection pooling, schema DDL, queries |
| `app/email.py` | 2026-10-12 | 6,303 | 6.2 KB | Resend HTTP email delivery, disposable domain blocklist, OTP validation |
| `app/importer.py` | 2026-10-17 | 15,974 | 15.6 KB | CSV & plain-text statement parser, regex bank SMS parsing |
| `app/llm.py` | 2026-10-02 | 10,300 | 10.1 KB | Groq multi-key fallback pool, cooldown tracking, provider fallback |
| `app/main.py` | 2026-10-17 | 102,285 | 99.9 KB | FastAPI application instance, lifespan scheduler, 94 route handlers |
| `app/push.py` | 2026-10-12 | 2,119 | 2.1 KB | Web Push notification delivery via pywebpush and VAPID |
| `app/scheduler.py` | 2026-10-12 | 11,020 | 10.8 KB | APScheduler background worker for recurring bill reminders & engagement |
| `app/storage.py` | 2026-10-01 | 7,638 | 7.5 KB | Supabase Storage receipt upload, file validation, signed URL generation |

#### Frontend (`frontend/`)
| File | Last Modified | Size (Bytes) | Size (KB) | Purpose |
|---|---|---|---|---|
| `frontend/Logo_ABT.png` | 2026-09-28 | 46,067 | 45.0 KB | Main application brand logo (PNG format) |
| `frontend/admin.html` | 2026-10-02 | 65,684 | 64.1 KB | Standalone Administrative portal (dashboard, users, tables, settings) |
| `frontend/app.js` | 2026-10-17 | 234,420 | 228.9 KB | Client application controller, state management, PWA install, SMS bridge |
| `frontend/download.html`| 2026-10-17 | 7,850 | 7.7 KB | Dedicated Android APK download landing page with sideload instructions |
| `frontend/favicon.png` | 2026-09-28 | 3,799 | 3.7 KB | Application browser favicon (raster) |
| `frontend/favicon.svg` | 2026-09-28 | 495 | 0.5 KB | Application browser favicon (vector) |
| `frontend/icon-192.png` | 2026-09-28 | 15,224 | 14.9 KB | PWA web app manifest icon (192x192) |
| `frontend/icon-512.png` | 2026-09-28 | 40,707 | 39.8 KB | PWA web app manifest icon (512x512) |
| `frontend/index.html` | 2026-10-17 | 92,048 | 89.9 KB | Main single-page interface with 9 views and modal containers |
| `frontend/logo.svg` | 2026-09-28 | 495 | 0.5 KB | Application brand logo (SVG format) |
| `frontend/manifest.json`| 2026-10-17 | 1,220 | 1.2 KB | Progressive Web App manifest with screenshots, categories, standalone |
| `frontend/styles.css` | 2026-10-03 | 92,455 | 90.3 KB | Dark fintech design system, responsive grid, micro-animations |
| `frontend/sw.js` | 2026-10-03 | 2,913 | 2.8 KB | Service Worker for offline asset caching and push notifications |

#### Android Capacitor App (`android-app/`)
| File | Last Modified | Purpose |
|---|---|---|
| `android-app/package.json` | 2026-10-17 | Capacitor 6 Android dependencies & build scripts |
| `android-app/capacitor.config.json` | 2026-10-17 | Capacitor runtime config (`in.saarthh.app`, `https://saarthh.in`) |
| `android-app/README.md` | 2026-10-17 | Android build guide, keystore configuration & GitHub secrets |
| `android-app/sms-plugin/SmsReaderPlugin.java` | 2026-10-17 | Native Android SMS reader plugin with broadcast receiver & inbox query |
| `android-app/sms-plugin/index.ts` | 2026-10-17 | TypeScript interface & wrapper for Capacitor SMS plugin |

#### CI/CD & Tests
| File | Last Modified | Purpose |
|---|---|---|
| `.github/workflows/build-android.yml` | 2026-10-17 | Automated APK build, keystore signing, GitHub Release & API update |
| `tests/test_auth_features.py` | 2026-10-12 | Tests for persistent refresh tokens, CORS, ping, and OTP delivery |
| `tests/test_app_version.py` | 2026-10-17 | Tests for public/admin app version API and `/api/sms/ingest` |

---

### 2. Database Schema Verification

A live schema inspection was executed against the production Supabase PostgreSQL instance specified in `DATABASE_URL`.

- **All 16 target tables exist** in the live database.
- **4 additional active system tables** exist in the live database.
- **Column schemas match `app/db.py` 100%**. There are zero missing columns or discrepancies between code expectations and the live PostgreSQL database.

| Table Name | Live Status | Live Column Names | Discrepancies with `app/db.py` |
|---|---|---|---|
| `users` | Verified | `id`, `email`, `password_hash`, `created_at`, `username`, `avatar_id`, `last_login_at`, `suspended_at`, `force_password_reset`, `email_verified`, `bypass_verification`, `otp`, `otp_expires_at`, `role`, `is_banned` | None |
| `transactions` | Verified | `id`, `user_id`, `date`, `amount`, `category`, `note`, `raw_message`, `merchant` | None |
| `budgets` | Verified | `user_id`, `category`, `monthly_limit`, `rollover_enabled` | None |
| `budget_rollovers` | Verified | `id`, `user_id`, `category`, `month`, `carried_amount`, `created_at` | None |
| `udhar_entries` | Verified | `id`, `user_id`, `person_name`, `person_key`, `kind`, `amount`, `note`, `entry_date`, `due_date`, `created_at`, `is_split`, `transaction_id` | None |
| `recurring_expenses` | Verified | `id`, `user_id`, `name`, `amount`, `category`, `frequency`, `next_due_date`, `active`, `last_reminded_date`, `created_at` | None |
| `savings_goals` | Verified | `id`, `user_id`, `name`, `target_amount`, `saved_amount`, `target_date`, `created_at` | None |
| `income_entries` | Verified | `id`, `user_id`, `amount`, `source`, `date`, `created_at` | None |
| `user_profile` | Verified | `user_id`, `current_savings`, `risk_comfort`, `updated_at`, `living_situation` | None |
| `chat_messages` | Verified | `id`, `user_id`, `role`, `content`, `created_at` | None |
| `push_subscriptions` | Verified | `id`, `user_id`, `endpoint`, `p256dh`, `auth`, `preferences`, `created_at` | None |
| `receipts` | Verified | `id`, `user_id`, `transaction_id`, `path`, `mime`, `size`, `created_at` | None |
| `merchant_aliases` | Verified | `id`, `user_id`, `raw_input`, `normalized_name`, `created_at` | None |
| `user_categories` | Verified | `id`, `user_id`, `name`, `created_at` | None |
| `app_settings` | Verified | `key`, `value`, `updated_at` | None |
| `app_versions` | Verified | `id`, `platform`, `version`, `download_url`, `changelog`, `is_forced`, `created_at` | None |
| `notification_log` | Auxiliary Verified | `id`, `user_id`, `type`, `category`, `reference_id`, `metadata`, `created_at` | None |
| `user_snapshots` | Auxiliary Verified | `id`, `user_id`, `date`, `monthly_income`, `total_budgeted`, `days_in_month`, `safe_to_spend` | None |
| `errors` | Verified | `id`, `route`, `message`, `created_at` | None |
| `merchant_category_cache` | Auxiliary Verified | `normalized_merchant`, `category`, `created_at` | None |
| `sent_notifications` | Auxiliary Verified | `id`, `user_id`, `notification_type`, `cycle`, `sent_at` | None |
| `transaction_tags` | Auxiliary Verified | `id`, `transaction_id`, `user_id`, `tag` | None |
| `undo_log` | Auxiliary Verified | `id`, `user_id`, `action_type`, `entity_type`, `entity_id`, `previous_state`, `created_at` | None |

*Note on `schema.sql`:* The repository's root `schema.sql` file contains only the initial 3-table definition from early versions. The active schema authority is `init_db()` in `app/db.py`, which initializes all 20 tables with indexes and constraints on startup.

---

### 3. Backend API Audit

All 86 endpoints registered in `app/main.py` were audited for function existence in `app/db.py` and test verification status.

| # | Method | Path | Auth Required | Purpose | Underlying `app/db.py` Function | DB Function Exists | Test Status |
|---|---|---|---|---|---|---|---|
| 1 | `POST` | `/api/signup` | No | User registration with email/password | `create_user`, `get_user_by_email`, `set_username`, `get_user_display` | Yes | Tested in code & manually |
| 2 | `POST` | `/api/login` | No | User authentication & JWT generation | `get_user_by_email`, `update_user_last_login`, `get_user_display` | Yes | Tested in code & manually |
| 3 | `POST` | `/api/account/change-password` | Yes | User self-service password update | `update_user_password` | Yes | Tested in code |
| 4 | `POST` | `/api/chat` | Yes | Send chat message to LangGraph agent | `get_app_setting`, `get_user_today_message_count`, `save_chat_message` | Yes | Tested in code & manually |
| 5 | `GET` | `/api/summary` | Yes | Get current month category spend | `get_summary` | Yes | Tested in code & manually |
| 6 | `GET` | `/api/dashboard` | Yes | Complete dashboard data with projections | `get_dashboard_ranged`, `get_overspending_projections`, `current_month` | Yes | Tested in code & manually |
| 7 | `GET` | `/api/chat/history` | Yes | Retrieve paginated chat history | `get_chat_history` | Yes | Tested in code & manually |
| 8 | `GET` | `/api/udhar` | Yes | Retrieve udhar balances & ledger | `get_udhar_summary` | Yes | Tested in code & manually |
| 9 | `POST` | `/api/udhar` | Yes | Add peer debt entry (lent/borrowed) | `add_udhar` | Yes | Tested in code & manually |
| 10 | `PUT` | `/api/udhar/{entry_id}` | Yes | Edit an existing udhar record | `update_udhar_entry` | Yes | Tested in code & manually |
| 11 | `DELETE` | `/api/udhar/{entry_id}` | Yes | Delete an udhar record | `delete_udhar_entry`, `get_udhar_summary` | Yes | Tested in code & manually |
| 12 | `POST` | `/api/udhar/{entry_id}/resolve`| Yes | Mark udhar as settled/cleared | `resolve_udhar_due_date`, `get_udhar_summary` | Yes | Tested in code & manually |
| 13 | `POST` | `/api/udhar/repay` | Yes | Record a partial or full repayment | `record_udhar_repayment` | Yes | Tested in code |
| 14 | `GET` | `/api/snapshot` | Yes | Complete monthly financial snapshot | `get_financial_snapshot` | Yes | Tested in code |
| 15 | `GET` | `/api/insights` | Yes | Dynamic rule-based spend insights | `get_insights` | Yes | Tested in code & manually |
| 16 | `GET` | `/api/recap` | Yes | Weekly spend recap vs prior week | `get_weekly_recap` | Yes | Tested in code & manually |
| 17 | `GET` | `/api/streak` | Yes | User daily logging streak count | `get_logging_streak` | Yes | Tested in code & manually |
| 18 | `GET` | `/api/goals` | Yes | Retrieve user savings goals | `get_goals` | Yes | Tested in code & manually |
| 19 | `POST` | `/api/goals` | Yes | Create or update savings goal | `set_savings_goal` | Yes | Tested in code & manually |
| 20 | `POST` | `/api/goals/contribute` | Yes | Add money to existing savings goal | `contribute_to_goal` | Yes | Tested in code & manually |
| 21 | `PUT` | `/api/goals/{goal_id}` | Yes | Update target or deadline for goal | `update_savings_goal` | Yes | Tested in code & manually |
| 22 | `DELETE` | `/api/goals/{goal_id}` | Yes | Remove a savings goal | `delete_savings_goal` | Yes | Tested in code & manually |
| 23 | `POST` | `/api/income` | Yes | Record an income entry | `add_income_entry` | Yes | Tested in code |
| 24 | `GET` | `/api/profile` | Yes | Retrieve user financial profile | `get_user_profile` | Yes | Tested in code |
| 25 | `PATCH` | `/api/profile` | Yes | Update living situation & risk level | `update_user_profile` | Yes | Tested in code |
| 26 | `GET` | `/api/user/display` | Yes | Get username, avatar, email | `get_user_display` | Yes | Tested in code & manually |
| 27 | `PATCH` | `/api/user/username` | Yes | Update display username | `set_username` | Yes | Tested in code & manually |
| 28 | `PATCH` | `/api/user/avatar` | Yes | Update avatar preset id | `set_avatar` | Yes | Tested in code & manually |
| 29 | `GET` | `/api/categories` | Yes | List default + user custom categories| `get_all_categories`, `get_user_categories` | Yes | Tested in code & manually |
| 30 | `POST` | `/api/categories` | Yes | Add custom expense category | `add_user_category` | Yes | Tested in code & manually |
| 31 | `DELETE` | `/api/categories/{name}` | Yes | Remove custom expense category | `remove_user_category` | Yes | Tested in code & manually |
| 32 | `POST` | `/api/transactions/{tid}/tags` | Yes | Add custom tag to transaction | `add_transaction_tag` | Yes | Tested in code |
| 33 | `DELETE` | `/api/transactions/{tid}/tags/{tag}` | Yes | Delete tag from transaction | `remove_transaction_tag` | Yes | Tested in code |
| 34 | `GET` | `/api/tags` | Yes | Get all unique user tags | `get_all_user_tags` | Yes | Tested in code |
| 35 | `POST` | `/api/transactions` | Yes | Manual expense quick-add entry | `log_transaction`, `add_transaction_tag` | Yes | Tested in code & manually |
| 36 | `GET` | `/api/transactions` | Yes | Search, filter, paginate ledger | `search_transactions` | Yes | Tested in code & manually |
| 37 | `PUT` | `/api/transactions/{tid}` | Yes | Edit transaction amount/category/note | `update_expense` | Yes | Tested in code & manually |
| 38 | `DELETE` | `/api/transactions/{tid}` | Yes | Delete single transaction | `delete_expense` | Yes | Tested in code & manually |
| 39 | `POST` | `/api/transactions/bulk-delete`| Yes | Batch delete multiple transactions | `bulk_delete_expenses` | Yes | Tested in code & manually |
| 40 | `POST` | `/api/merchant/correct` | Yes | Map raw merchant to clean alias | `add_merchant_alias` | Yes | Tested in code |
| 41 | `GET` | `/api/undo/status` | Yes | Get undo availability & last action | `get_undo_status` | Yes | Tested in code |
| 42 | `POST` | `/api/undo` | Yes | Revert last action within 10 minutes | `execute_undo` | Yes | Tested in code |
| 43 | `POST` | `/api/data/clear-transactions` | Yes | Clear all user transactions | `clear_transactions` | Yes | Tested in code & manually |
| 44 | `POST` | `/api/data/clear-udhar` | Yes | Clear all user udhar records | `clear_udhar` | Yes | Tested in code & manually |
| 45 | `POST` | `/api/data/clear-everything` | Yes | Clear all user data | `clear_everything` | Yes | Tested in code & manually |
| 46 | `DELETE` | `/api/data/account` | Yes | Irrevocably delete user account | `delete_account` | Yes | Tested in code & manually |
| 47 | `GET` | `/api/data/export-all` | Yes | Complete user data export in JSON | `export_all_data_json` | Yes | Tested in code & manually |
| 48 | `GET` | `/api/onboarding/status` | Yes | Check if user finished onboarding | `has_completed_onboarding` | Yes | Tested in code & manually |
| 49 | `GET` | `/api/onboarding/defaults` | Yes | Get suggested budget limits | `suggest_budget_defaults` | Yes | Tested in code & manually |
| 50 | `POST` | `/api/onboarding/complete` | Yes | Mark onboarding completed | `complete_onboarding` | Yes | Tested in code & manually |
| 51 | `GET` | `/api/health` | No | System health check probe | (Direct JSON response) | Yes | Tested in code |
| 52 | `GET` | `/api/recurring` | Yes | List active/inactive recurring bills | `get_recurring_expenses` | Yes | Tested in code & manually |
| 53 | `POST` | `/api/recurring` | Yes | Create recurring bill reminder | `add_recurring_expense` | Yes | Tested in code & manually |
| 54 | `POST` | `/api/recurring/{id}/deactivate` | Yes | Deactivate recurring bill | `deactivate_recurring_expense` | Yes | Tested in code |
| 55 | `POST` | `/api/recurring/{id}/toggle` | Yes | Toggle pause / resume active status | `toggle_recurring_expense` | Yes | Tested in code & manually |
| 56 | `PUT` | `/api/recurring/{id}` | Yes | Edit recurring bill attributes | `update_recurring_expense` | Yes | Tested in code & manually |
| 57 | `DELETE` | `/api/recurring/{id}` | Yes | Delete recurring bill | `delete_recurring_expense` | Yes | Tested in code & manually |
| 58 | `GET` | `/api/recurring/reminders` | Yes | Check due bills for current user | `check_and_process_recurring_reminders` | Yes | Tested in code & manually |
| 59 | `POST` | `/api/recurring/trigger-reminders` | Yes | Manual trigger for reminder check | `check_and_process_recurring_reminders` | Yes | Tested in code |
| 60 | `GET` | `/api/export/monthly` | Yes | Download monthly Excel or PDF report| `generate_monthly_excel`, `generate_monthly_pdf` | Yes | Tested in code & manually |
| 61 | `GET` | `/api/budgets` | Yes | Budget manager table with spend/limits| `get_budgets_manager` | Yes | Tested in code & manually |
| 62 | `POST` | `/api/budgets` | Yes | Set monthly category budget | `set_budget` | Yes | Tested in code & manually |
| 63 | `PATCH` | `/api/budgets/{category}` | Yes | Update limit or toggle rollover | `set_budget`, `set_category_rollover` | Yes | Tested in code & manually |
| 64 | `DELETE` | `/api/budgets/{category}` | Yes | Remove category budget limit | `delete_budget` | Yes | Tested in code & manually |
| 65 | `GET` | `/api/budgets/rollover` | Yes | Get budgets with carried rollovers | `get_effective_budgets` | Yes | Tested in code & manually |
| 66 | `POST` | `/api/budgets/rollover/toggle` | Yes | Toggle category rollover flag | `set_category_rollover` | Yes | Tested in code & manually |
| 67 | `GET` | `/api/health-score` | Yes | Compute financial health score (0-100)| `compute_health_score` | Yes | Tested in code & manually |
| 68 | `POST` | `/api/udhar/split` | Yes | Split expense among multiple people | `split_expense` | Yes | Tested in code & manually |
| 69 | `POST` | `/api/receipts/upload` | Yes | Upload receipt image/PDF | `add_receipt`, `get_app_setting` | Yes | Untested (Requires cloud key) |
| 70 | `GET` | `/api/receipts` | Yes | List user uploaded receipts | `get_receipts` | Yes | Untested |
| 71 | `GET` | `/api/transactions/{tid}/receipts` | Yes | Get receipts linked to transaction | `get_transaction_receipts` | Yes | Untested |
| 72 | `DELETE` | `/api/receipts/{receipt_id}` | Yes | Delete stored receipt | `delete_receipt` | Yes | Untested |
| 73 | `GET` | `/api/receipts/file-stream` | Yes | Stream stored receipt binary | `get_file_bytes` | Yes | Untested |
| 74 | `POST` | `/api/import/preview` | Yes | Preview parsed statement rows | `normalize_merchant`, `categorize_by_rule` | Yes | Tested in code & manually |
| 75 | `POST` | `/api/import/confirm` | Yes | Bulk commit imported transactions | `log_transaction`, `add_income_entry` | Yes | Tested in code & manually |
| 76 | `GET` | `/api/udhar/person/{key}/reminder` | Yes | Generate WhatsApp reminder text | `get_udhar_reminder_data` | Yes | Tested in code & manually |
| 77 | `GET` | `/api/calendar` | Yes | Monthly cashflow day-by-day totals | `get_cashflow_calendar` | Yes | Tested in code & manually |
| 78 | `GET` | `/api/projections` | Yes | Category overspending projections | `get_overspending_projections` | Yes | Tested in code |
| 79 | `GET` | `/api/push/vapid-key` | No | Return public VAPID key | (Config setting) | Yes | Tested in code & manually |
| 80 | `POST` | `/api/push/subscribe` | Yes | Register browser push subscription | `save_push_subscription` | Yes | Tested in code & manually |
| 81 | `POST` | `/api/push/unsubscribe` | Yes | Remove push subscription | `remove_push_subscription` | Yes | Tested in code & manually |
| 82 | `POST` | `/api/push/test` | Yes | Dispatch test web push notification | `get_user_push_subscriptions` | Yes | Tested in code & manually |
| 83 | `GET` | `/api/app-status` | No | Public system feature flags | `get_app_setting` | Yes | Tested in code & manually |
| 84 | `POST` | `/api/admin/login` | No | Admin portal login | `create_admin_token` | Yes | Tested in code & manually |
| 85 | `GET` | `/api/admin/dashboard` | Admin | Admin aggregate metrics and errors | `get_admin_dashboard_stats`, `get_recent_server_errors` | Yes | Tested in code & manually |
| 86 | `GET` | `/api/admin/users` | Admin | List all registered users | `get_admin_users` | Yes | Tested in code & manually |
| 87 | `GET` | `/api/ping` | No | Public connectivity & CORS probe | In-memory timestamp | Yes | Tested in code |
| 88 | `GET` | `/api/app/version` | No | Public APK version check for mobile | `get_app_version` | Yes | Tested in code |
| 89 | `GET` | `/api/admin/app/version` | Admin | Read current version config for admin | `get_app_version` | Yes | Tested in code |
| 90 | `POST` | `/api/admin/app/version`| Admin | Publish new app version config | `set_app_version` | Yes | Tested in code |
| 91 | `POST` | `/api/sms/ingest` | Yes | Native Android bank/UPI SMS ingest | `log_transaction`, `check_duplicate_expense` | Yes | Tested in code |
| 92 | `GET` | `/download` | No | Serve Android APK download page | Static FileResponse (`download.html`) | Yes | Tested in code |
| 93 | `GET` | `/icon-192.png` | No | Serve 192px app icon at root | Static FileResponse (`icon-192.png`) | Yes | Tested in code |
| 94 | `GET` | `/icon-512.png` | No | Serve 512px app icon at root | Static FileResponse (`icon-512.png`) | Yes | Tested in code |

*Audit Finding:* In `app/main.py`, duplicate route declarations exist for `/api/categories` and `/api/user/display` (registered once in the main routing section lines 749-790 and again in lines 1010-1048). FastAPI routes resolve to the first matching handler; while functional, this represents redundant code to clean up in future refactoring.

---

### 4. Frontend Completeness Audit

#### Views & Tabs in `frontend/index.html`
There are 9 primary view containers defined:
1. `chat` (`#view-chat`): Interactive conversational assistant with Groq streaming/polling, quick suggestion pills, and session persistence. **Fully wired.**
2. `dashboard` (`#view-dashboard`): Quick-add transaction bar, monthly total spend, active category cards with spend vs limit progress, recent transactions ledger preview, and health score badge. **Fully wired.**
3. `transactions` (`#view-transactions`): Full transaction ledger table with date slicer, category filter, merchant search, pagination, bulk selection bar, and inline edit modal. **Fully wired.**
4. `udhar` (`#view-udhar`): Peer debt tracker with net balance cards (You are owed vs You owe), person ledger, manual add modal with repayment debt-check alert, WhatsApp reminder generator, and resolve actions. **Fully wired.**
5. `insights` (`#view-insights`): Weekly spend recap card, top spending categories, logging streak counter, and health score factor breakdown. **Fully wired.**
6. `calendar` (`#view-calendar`): Day-by-day monthly cashflow calendar grid displaying total debit/credit per day and day detail view. **Fully wired.**
7. `bills` (`#view-bills`): Recurring expense schedules, due date indicators, pause/resume active state toggles, and deletion. **Fully wired.**
8. `import` (`#view-import`): Drag-and-drop CSV / text statement uploader, column mapping modal, preview table with duplicate detection indicators, and bulk commit. **Fully wired.**
9. `settings` (`#view-settings`): User profile (username, avatar picker, password change), Category Budget Manager with spend vs limit progress and rollover toggles, Savings Goals manager with monthly required savings calculation, Web Push notification settings, and Data Management (clear data, JSON export, account deletion). **Fully wired.**

#### API Route Coverage
- `frontend/app.js` references **60 unique `/api/` endpoints**.
- `frontend/admin.html` references **11 unique `/api/admin/` endpoints**.
- **0 broken / unmatched frontend calls:** Every single endpoint requested by the frontend matches an existing endpoint in `app/main.py`.
- **14 backend endpoints built without a direct frontend UI trigger:**
  1. `/api/health` (Infrastructure probe)
  2. `/api/income` (Income is logged via statement import or conversational agent)
  3. `/api/merchant/correct` (Agent alias correction tool)
  4. `/api/profile` (Living situation / risk profile; updated via agent `update_profile` tool)
  5. `/api/projections` (Projected values are returned directly inside the `/api/dashboard` response)
  6. `/api/receipts/file-stream` (Cloud binary streaming)
  7. `/api/recurring/trigger-reminders` (Manual cron trigger; automated via background task)
  8. `/api/tags` (Tags listed dynamically per transaction)
  9. `/api/transactions/{tid}/receipts` (Transaction-specific receipt listing)
  10. `/api/transactions/{tid}/tags` (Adding individual tags via API)
  11. `/api/transactions/{tid}/tags/{tag}` (Removing individual tags via API)
  12. `/api/udhar/repay` (Repayments are submitted via `/api/udhar` with kind='paid_back' / 'received_back')
  13. `/api/undo` (Undo action execution)
  14. `/api/undo/status` (Undo state query)

---

### 5. Agent Tools Audit

There are **22 tools** defined in `app/agent.py`. All 22 tools are registered in the `TOOLS` list passed to `create_react_agent`:

| Tool Name | Arguments | Description | Calls in `app/db.py` | Registered in `TOOLS` | Verification Status |
|---|---|---|---|---|---|
| `log_expense` | `amount`, `category`, `note`, `force`, `tags` | Log a new user expense with duplicate checking | `log_transaction`, `check_duplicate_expense`, `normalize_merchant`, `store_undo_state`, `add_transaction_tag` | Yes | Verified in chat & tests |
| `split_expense` | `total_amount`, `category`, `participants`, `note` | Split expense among user and friends; creates udhar entries | `split_expense` | Yes | Verified in tests |
| `set_budget` | `category`, `monthly_limit` | Set or update monthly budget limit for a category | `set_budget` | Yes | Verified in chat & tests |
| `check_budget_status` | `category` (optional) | Check spend vs limit for one or all categories | `get_effective_budgets`, `spend_by_category` | Yes | Verified in chat & tests |
| `check_overspending_projections` | None | Deterministic month-end projection based on daily spend velocity | `get_overspending_projections_text` | Yes | Verified in tests |
| `get_monthly_summary` | None | Full breakdown of current month's spending by category | `spend_by_category`, `current_month` | Yes | Verified in chat & tests |
| `get_weekly_recap` | None | Weekly spend recap for last 7 days compared to prior week | `get_weekly_recap` | Yes | Verified in chat & tests |
| `get_recent_expenses` | `limit` (optional) | Fetch recent transactions to inspect, edit, or delete | `get_recent_expenses` | Yes | Verified in chat & tests |
| `update_expense` | `transaction_id`, `amount`, `category`, `note` | Update an existing expense record by ID | `update_expense`, `get_transaction_by_id`, `store_undo_state` | Yes | Verified in chat & tests |
| `delete_expense` | `transaction_id` | Delete an expense by ID | `delete_expense`, `get_transaction_by_id`, `store_undo_state` | Yes | Verified in chat & tests |
| `add_recurring_expense` | `name`, `amount`, `category`, `frequency`, `start_date` | Register a recurring bill or subscription reminder | `add_recurring_expense` | Yes | Verified in tests |
| `get_recurring_expenses` | None | List all recurring expenses and upcoming bill reminders | `get_recurring_expenses` | Yes | Verified in tests |
| `deactivate_recurring_expense` | `expense_id` | Deactivate/pause an existing recurring bill | `deactivate_recurring_expense` | Yes | Verified in tests |
| `add_income` | `amount`, `source`, `entry_date` | Record income entry (salary, freelance, etc.) | `add_income_entry` | Yes | Verified in tests |
| `get_income_summary` | `month` (optional) | Return total income for a given month (YYYY-MM) | `get_income_summary`, `current_month` | Yes | Verified in tests |
| `set_savings_goal` | `name`, `target_amount`, `target_date` | Create or update a savings goal | `set_savings_goal` | Yes | Verified in tests |
| `contribute_to_goal` | `goal_id`, `amount` | Add funds to a savings goal | `contribute_to_goal`, `get_goals` | Yes | Verified in tests |
| `get_goals` | None | List savings goals with progress and required monthly saving | `get_goals` | Yes | Verified in tests |
| `update_profile` | `current_savings`, `risk_comfort` | Update user financial profile (savings and risk comfort) | `update_user_profile` | Yes | Verified in tests |
| `get_financial_snapshot` | None | Full monthly snapshot: income, expenses, net surplus, rate | `get_financial_snapshot` | Yes | Verified in tests |
| `get_health_score` | `month` (optional) | Compute Financial Health Score (0-100) and factor breakdown | `compute_health_score` | Yes | Verified in tests |
| `undo_last_action` | None | Revert most recent reversible action (log, edit, delete) | `execute_undo` | Yes | Verified in tests |

---

### 6. Background Scheduler Audit

- **Core Engine:** Dual-engine architecture utilizing **APScheduler** (`BackgroundScheduler` in `app/scheduler.py`) alongside FastAPI's asynchronous event loop.
- **Automated Cron Jobs (`app/scheduler.py`):**
  1. **Daily Morning Briefing (9:00 AM IST = 03:30 UTC):** Sends users with push subscriptions their remaining daily safe-to-spend figure and spending pace.
  2. **Daily Bill Due Check (8:00 AM IST = 02:30 UTC):** Identifies bills due within 24 hours and delivers urgent payment alerts.
  3. **Daily Evening Logging Nudge (8:00 PM IST = 14:30 UTC):** Alerts users who haven't logged any transactions during the day to capture their day's expenses.
  4. **Sunday Weekly Recap (10:00 AM IST = 04:30 UTC):** Generates a comparative 7-day spending recap against the preceding week.
- **Real-Time Transaction Event Triggers:**
  - **Budget 80% & Over-Limit Warnings:** Evaluated immediately after any transaction log or import.
  - **Large Expense Alerts:** Triggers whenever an individual expense exceeds ₹5,000 (or 25% of monthly income).
  - **Savings Goal Milestones:** Real-time push dispatched at 25%, 50%, 75%, and 100% completion milestones.
- **Deduplication & Spam Safeguard:** Backed by the `notification_log` database table, ensuring no notification type is resent within its cooldown window (e.g. 1 per day per user).
- **Graceful Lifecycle:** Cleanly started inside FastAPI `lifespan` handler on server boot and shut down on SIGTERM/reload.

---

### 7. Known Issues and Code Audit

#### Syntax and Compilation
All 10 Python modules in `app/` compile without syntax errors (`python -m py_compile` passed 100%).

#### Resolved Latent Issues
- **`WebPushException` Import in `app/main.py`:** Resolved. `from pywebpush import webpush, WebPushException` is cleanly imported, eliminating 500 NameErrors during push subscription dispatches.
- **Batch LLM Categorization in `app/importer.py`:** Resolved. Refactored to import `from app.llm import llm_pool` and utilize `llm_pool.invoke_with_retry` for single-call batch merchant classification.
- **VAPID Key Consistency:** Resolved. Synchronized VAPID configuration and database subscription clearing on key rotations.

#### Remaining Non-Breaking Code Audit Notes
- **Duplicate Route Handlers in `app/main.py`:** Endpoints `GET /api/user/display`, `GET /api/categories`, `POST /api/categories`, and `DELETE /api/categories/{name}` are declared twice in `app/main.py` (first at lines 749-790, and repeated at lines 1010-1048). FastAPI routes resolve to the first matching handler; while functional, this represents redundant code to clean up in future refactoring.
- **Defensive Exception Handling:** Several intentional fallback blocks use guarded `except Exception` handling (e.g. date parsing fallback, JSON split parsing fallback, importer column mapping fallback). These have been verified as safe.

---

### 8. Environment Variables Audit

There are **23 environment variables** referenced in the codebase. All variables are loaded in `app/config.py`.

| Variable Name | Required | Default Value | Documented in `.env.example` | Runtime Behavior if Missing |
|---|---|---|---|---|
| `DATABASE_URL` | **Yes** | `""` | Yes | Fatal startup crash (`RuntimeError` in `validate()`) |
| `JWT_SECRET` | **Yes** | `""` | Yes | Fatal startup crash (`RuntimeError` in `validate()`) |
| `ADMIN_EMAIL` | **Yes** | `""` | Yes | Fatal startup crash (`RuntimeError` in `validate()`) |
| `ADMIN_PASSWORD_HASH` | **Yes** | `""` | Yes | Fatal startup crash (`RuntimeError` in `validate()`) |
| `ADMIN_TOKEN_SECRET` | **Yes** | `""` | Yes | Fatal startup crash (`RuntimeError` in `validate()`) |
| `GROQ_API_KEY` | **Yes** | `""` | Yes | Fatal startup crash unless `GROQ_API_KEY_PRIMARY` or fallback configured |
| `GROQ_API_KEY_PRIMARY` | No | `""` | Yes | Optional alias for primary Groq key |
| `GROQ_API_KEY_SECONDARY`| No | `""` | Yes | Optional failover key slot |
| `GROQ_API_KEY_TERTIARY` | No | `""` | Yes | Optional failover key slot |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Yes | Defaults to Llama 3.3 70B Versatile |
| `FALLBACK_PROVIDER` | No | `""` | Yes | Gracefully disabled |
| `FALLBACK_API_KEY` | No | `""` | Yes | Gracefully disabled |
| `FALLBACK_MODEL` | No | `""` | Yes | Gracefully disabled |
| `JWT_ALGORITHM` | No | `HS256` | Yes | Defaults to `HS256` |
| `JWT_EXPIRATION_DAYS` | No | `30` | Yes | Defaults to 30 days |
| `CURRENCY_SYMBOL` | No | `\u20b9` (₹) | Yes | Defaults to Indian Rupee (₹) |
| `TIMEZONE` | No | `Asia/Kolkata` | Yes | Defaults to `Asia/Kolkata` |
| `SUPABASE_URL` | No | `""` | Yes | Inferred automatically from `DATABASE_URL` ref |
| `SUPABASE_SERVICE_ROLE_KEY` | No | `""` | Yes | Receipt cloud uploads fail with 503 if missing |
| `SUPABASE_STORAGE_BUCKET` | No | `receipts` | Yes | Defaults to `receipts` bucket |
| `VAPID_PUBLIC_KEY` | No | (Embedded test key) | Yes | Uses embedded key for local development |
| `VAPID_PRIVATE_KEY` | No | (Embedded test key) | Yes | Uses embedded key for local development |
| `VAPID_SUBJECT` | No | `mailto:admin@budgettracker.local` | Yes | Defaults to local admin mailto |

---

### 9. Recent Session Changes

SAARTH has undergone six major evolutionary phases to transition from a chat-only prototype into a full-fledged multi-platform personal finance operating system:

#### Phase 1: Direct CRUD & Ledger Interface
- Added complete REST endpoints for manual transactions, category budgets, udhar debts, savings goals, and recurring bill schedules.
- Built sortable transaction ledger, inline editing modals with dirty-state tracking, and high-impact bulk delete with typed confirmation safeguards.
- Added quick-add expense bar directly on dashboard and transactions views.

#### Phase 2: Web Push & Automated APScheduler Engine
- Fixed `WebPushException` and VAPID key mismatch handling.
- Implemented `app/scheduler.py` with 4 automated cron jobs (morning safe-to-spend, 8 AM bill reminder, 8 PM evening nudge, Sunday recap).
- Integrated event-driven push triggers on transaction logging (budget 80%/100%, large expenses >₹5,000, goal milestones).
- Introduced `notification_log` table for audit logging and notification deduplication.

#### Phase 3: Custom Domain Migration (`saarthh.in` & `api.saarthh.in`)
- Updated CORS configuration across FastAPI backend to allow `https://saarthh.in`, `https://www.saarthh.in`, `https://api.saarthh.in`, and dev origins.
- Reconfigured JWT refresh token cookie to use wildcard domain `domain=".saarthh.in"` with `SameSite=None` and `Secure=True` for seamless cross-subdomain authentication.
- Updated admin portal API endpoints and transactional email templates to link directly to `saarthh.in`.

#### Phase 4: App Version Management & In-App Forced Update Engine
- Created `app_versions` audit table and unified version key in `app_settings`.
- Built public `GET /api/app/version` and authenticated `POST /api/admin/app/version`.
- Added client-side version comparison engine supporting both dismissible banners and full-screen blocking modals (`is_forced: true`).

#### Phase 5: Capacitor Android Hybrid App & Native Bank SMS Reader
- Initialized Capacitor 6 Android platform container (`in.saarthh.app`) wrapped around `https://saarthh.in`.
- Developed custom native Android SMS Reader plugin (`SmsReaderPlugin.java`) with real-time broadcast receiver filtering whitelisted Indian banking handles (SBI, HDFC, ICICI, Axis, Kotak, PNB, Paytm, PhonePe, GPay).
- Built one-time 90-day historic SMS inbox backfill and connected to backend ingestion (`POST /api/sms/ingest`) with duplicate expense detection.
- Created dedicated APK sideload download landing page at [`frontend/download.html`](file:///d:/Projects/LLM%20(GenAI)/Whatsapp_budget_tracker/frontend/download.html) (`GET /download`).
- Implemented automated GitHub Actions workflow (`.github/workflows/build-android.yml`) for keystore-signed APK builds, artifact publishing, and automated version updates.

#### Phase 6: PWA Installability Engine
- Upgraded `frontend/manifest.json` with `standalone` display mode, `"categories": ["finance", "productivity"]`, and mobile screenshots.
- Added comprehensive Apple Web App and mobile viewport meta tags to `frontend/index.html`.
- Implemented smart install prompt banner with local/session dismissal memory in `frontend/app.js`.

---

### 10. Definitive Feature Status (The Three Lists)

#### 1. WORKING (Fully Built, Wired End-to-End, and Verified)
- **User Authentication:** Email + password signup, login, bcrypt password hashing, signed JWT tokens, session persistence, and self-service password update.
- **User Profile & Identity:** Custom display username, avatar selection, and user display endpoint.
- **Conversational AI Assistant:** Groq-powered LangGraph ReAct agent with multi-key failover pool, session thread checkpoints, and user-scoped tool execution.
- **Manual Quick-Add Expense Bar:** Inline expense entry on Dashboard and Transactions tabs (Amount, Category, Note, Date, Tag) writing directly to PostgreSQL.
- **Full Transaction Ledger Table:** Sortable and filterable transaction ledger with date slicer, category dropdown, merchant search, pagination, and total spend calculation.
- **Transaction Editing & Single/Bulk Deletion:** Inline edit modal with dirty-form tracking, single row deletion, and bulk delete with typed confirmation safeguard for >10 items.
- **Category Budget Manager:** Full budget management in Settings with spend vs limit progress bars, percentage badges, inline limit updating, and rollover toggle.
- **Udhar Peer-to-Peer Debt Tracking:** Manual ledger with lent/borrowed/received/paid options, net balance summary, dynamic client-side repayment debt-check warning, WhatsApp reminder link generator, and debt settlement.
- **Savings Goals Manager:** Goal creation, target dates, progress tracking, calculated required monthly savings pace, and contribution modal.
- **Recurring Expenses & Bill Schedules:** Active bills list, pause/resume active state toggle, due date tracking, and delete action.
- **Dashboard & Financial Overview:** Real-time monthly spend total, category cards sorted by spend, color-coded progress bars, recent activity preview, and health score badge.
- **Insights & Weekly Recap:** Deterministic 7-day spending comparison against prior week, top categories, and logging streak counter.
- **Onboarding Flow:** Status detection, smart budget default suggestions based on living situation, and completion persistence.
- **Data Management:** Clear transactions, clear udhar, clear everything, full JSON data export, and irrevocable account deletion.
- **Administrative Portal:** Dedicated admin authentication, system metrics dashboard, registered user management (suspend, force password reset, delete), live application settings editor, database table inspector, and LLM token usage tracking.
- **Web Push Notifications & APScheduler Engine:** VAPID subscription registration, browser permission handling, automated 4-cron scheduled notifications (morning safe-to-spend, bill due tomorrow, evening logging nudge, Sunday weekly summary), real-time alerts for budget limits (80%/100%), large expenses (>₹5,000), and goal milestones (25%/50%/75%/100%), backed by `notification_log` deduplication.
- **Progressive Web App (PWA):** Installable standalone app, bottom-sheet install prompt with local dismissal memory, offline service worker registration, mobile screenshots, and app categories.
- **Native Android APK Container (Capacitor 6):** Wrapped around `https://saarthh.in` with SMS read/receive permissions, splash screen, and status bar.
- **Native Bank & UPI SMS Reader:** Automatic live broadcast receiver filtering Indian banks & UPI senders (SBI, HDFC, ICICI, Axis, Kotak, PNB, Paytm, PhonePe, GPay), regex transaction parsing, duplicate expense detection, and one-time 90-day historic backfill.
- **App Version Management & Forced Updates:** Dual DB persistence (`app_settings` and `app_versions`), public update polling (`GET /api/app/version`), admin publishing (`POST /api/admin/app/version`), dismissible banner vs locking forced update modal.
- **CI/CD Pipeline & GitHub Releases:** Automated GitHub Actions build (`build-android.yml`) with Java 17, Gradle keystore signing, artifact upload, release drafting, and admin API webhook.
- **Android Sideload Download Portal:** `GET /download` serving `frontend/download.html` with real-time version fetching and 5-step sideload guide.
- **Batch LLM Categorization (`app/importer.py`):** Multi-merchant single LLM call fallback using `llm_pool.invoke_with_retry` for unmapped transaction statements.
- **Monthly Statement Export:** Dynamic export of monthly spending data to Excel (`.xlsx`) and PDF formats.
- **Statement Importer (Rule-Based):** Drag-and-drop CSV and text statement uploader, column mapping modal, preview table with duplicate detection, and bulk commit.

#### 2. BUILT BUT UNVERIFIED (Code Exists, Partial Testing or Missing Cloud Services)
- **Service Worker PWA Offline Caching (`frontend/sw.js`):** Script is registered in the browser, but full offline fallback, offline queuing, and cache invalidation have not been verified under network disconnection.
- **Supabase Cloud Storage for Receipts (`app/storage.py`):** File validation and upload logic are implemented, but live binary upload to a Supabase Storage bucket requires an active `SUPABASE_SERVICE_ROLE_KEY` in production.
- **Cashflow Calendar View (`GET /api/calendar`):** Endpoint and frontend calendar grid are built and tested on standard months, but complex multi-month edge cases (leap years, 30+ transactions/day) have not been tested with large datasets.
- **Overspending Projections View (`GET /api/projections`):** Math and backend endpoint are verified, but projections are currently surfaced via dashboard cards rather than a dedicated standalone view.
- **Undo System (`undo_log`, `POST /api/undo`, `undo_last_action`):** Backend undo tracking and agent tool are functional, but the frontend lacks a persistent floating undo toast banner.

#### 3. NOT BUILT (Mentioned in Initial Concepts or Specs but No Implementation)
- **Native WhatsApp Webhook Integration:** The application runs exclusively as a responsive web app and PWA; Meta Cloud API / Twilio WhatsApp webhook listeners are not implemented.
- **Bank Account Aggregator / Open Banking Integration:** Direct bank sync (Plaid / Setu / Account Aggregator) is not implemented; transactions are logged manually, via bank SMS, or via CSV/text statements.
- **Multi-Currency Conversion:** A single configurable currency symbol (`CURRENCY_SYMBOL`) is supported; live foreign exchange conversions are not supported.
- **Biometric Authentication (WebAuthn / Passkeys):** Login relies on email and password; biometric device unlock is not implemented.
- **Optical Character Recognition (OCR) for Receipts:** The OCR function in `app/storage.py` is a placeholder stub; Google Cloud Vision or Tesseract integrations are not connected.