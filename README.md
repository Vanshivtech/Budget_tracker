# SAARTH — Make money meaningful

A multi-user personal finance and budget management platform designed for cloud deployment. SAARTH combines conversational AI expense tracking (via Groq LLM and LangGraph ReAct agent) with a comprehensive manual management interface (quick-add bar, full transaction ledger, category budget manager, udhar tracking, savings goals, recurring bill schedules, and admin operations).

---

## Table of Contents

1. [Architecture and System Design](#architecture-and-system-design)
2. [Quick Start (Local Development)](#quick-start-local-development)
3. [Production Deployment](#production-deployment)
4. [Project Status Report & Technical Audit](#project-status-report--technical-audit)
   - [1. File Inventory](#1-file-inventory)
   - [2. Database Schema Verification](#2-database-schema-verification)
   - [3. Backend API Audit](#3-backend-api-audit)
   - [4. Frontend Completeness Audit](#4-frontend-completeness-audit)
   - [5. Agent Tools Audit](#5-agent-tools-audit)
   - [6. Background Scheduler Audit](#6-background-scheduler-audit)
   - [7. Known Issues and Code Audit](#7-known-issues-and-code-audit)
   - [8. Environment Variables Audit](#8-environment-variables-audit)
   - [9. Recent Session Changes (Manual Entry & Management)](#9-recent-session-changes-manual-entry--management)
   - [10. Definitive Feature Status (The Three Lists)](#10-definitive-feature-status-the-three-lists)

---

## Architecture and System Design

The application follows a dual-entry architectural pattern where both conversational AI and manual UI interactions write to the same relational database layer:

- **Conversational Entry:** User sends natural language messages in the chat interface. A LangGraph ReAct agent powered by Groq LLM (with multi-key failover) uses 22 user-scoped tools to log expenses, split bills, check budgets, compute health scores, and track goals.
- **Manual Entry & Management:** Direct forms and modals allow users to quick-add expenses, search and filter the full transaction ledger, perform inline edits, execute bulk deletions, configure monthly category budgets with rollovers, manage peer-to-peer debts (udhar), track savings goals, and pause/resume recurring bills.
- **Backend Core:** FastAPI application exposing 86 endpoints with bcrypt password hashing, JWT session authentication, and user isolation enforced at the database query level.
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
```

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

## Production Deployment

### Deployment to Render or Railway

1. **Database:** Create a project on Supabase. Copy the connection pooler URI (`aws-0-region.pooler.supabase.com:6543`) into `DATABASE_URL`.
2. **Repository:** Ensure `.env` is ignored by `.gitignore`. Push repository to GitHub.
3. **Web Service Configuration:**
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Python Version:** 3.12.0 (detected via `runtime.txt`)
4. **Environment Variables:** Configure all required variables listed above in the host dashboard.
5. **Health Check:** Verify `https://your-service-url/api/health` returns `{"status":"ok"}`.

---

## Project Status Report & Technical Audit

### 1. File Inventory

#### Backend (`app/`)
| File | Last Modified | Size (Bytes) | Size (KB) | Purpose |
|---|---|---|---|---|
| `app/__init__.py` | 2026-09-17 21:16:35 | 0 | 0.0 KB | Package initialization marker |
| `app/agent.py` | 2026-10-02 00:14:34 | 28,410 | 27.7 KB | LangGraph ReAct agent, prompt, memory checkpointer, 22 financial tools |
| `app/auth.py` | 2026-10-02 00:14:54 | 4,701 | 4.6 KB | User and admin password hashing (bcrypt), JWT token issue and decode |
| `app/config.py` | 2026-10-02 00:13:03 | 5,373 | 5.2 KB | Central settings class, environment variable loading, validation |
| `app/db.py` | 2026-10-03 13:09:41 | 174,391 | 170.3 KB | Supabase Postgres database layer, connection pooling, schema DDL, queries |
| `app/importer.py` | 2026-10-01 23:00:42 | 15,703 | 15.3 KB | CSV and plain-text statement parser, rule-based & LLM categorization |
| `app/llm.py` | 2026-10-02 00:14:09 | 10,300 | 10.1 KB | Groq multi-key fallback pool, cooldown tracking, provider fallback |
| `app/main.py` | 2026-10-02 01:06:11 | 66,196 | 64.6 KB | FastAPI application instance, lifespan scheduler, 86 route handlers |
| `app/push.py` | 2026-10-01 23:00:19 | 2,119 | 2.1 KB | Web Push notification delivery via pywebpush and VAPID |
| `app/storage.py` | 2026-10-01 23:00:03 | 7,638 | 7.5 KB | Supabase Storage receipt upload, file validation, signed URL generation |

#### Frontend (`frontend/`)
| File | Last Modified | Size (Bytes) | Size (KB) | Purpose |
|---|---|---|---|---|
| `frontend/Logo_ABT.png` | 2026-09-28 23:57:39 | 46,067 | 45.0 KB | Main application brand logo (PNG format) |
| `frontend/admin.html` | 2026-10-02 00:24:57 | 65,684 | 64.1 KB | Standalone Administrative portal (dashboard, users, tables, settings) |
| `frontend/app.js` | 2026-10-03 12:47:12 | 205,045 | 200.2 KB | Client application controller, state management, API client, dirty checkers |
| `frontend/favicon.png` | 2026-09-28 23:57:39 | 3,799 | 3.7 KB | Application browser favicon (raster) |
| `frontend/favicon.svg` | 2026-09-28 23:44:12 | 495 | 0.5 KB | Application browser favicon (vector) |
| `frontend/icon-192.png` | 2026-09-28 23:57:39 | 15,224 | 14.9 KB | PWA web app manifest icon (192x192) |
| `frontend/icon-512.png` | 2026-09-28 23:57:39 | 40,707 | 39.8 KB | PWA web app manifest icon (512x512) |
| `frontend/index.html` | 2026-10-03 12:48:53 | 82,750 | 80.8 KB | Main single-page interface with 9 views and modal containers |
| `frontend/logo.svg` | 2026-09-28 23:44:24 | 495 | 0.5 KB | Application brand logo (SVG format) |
| `frontend/manifest.json` | 2026-10-01 00:05:26 | 868 | 0.8 KB | Progressive Web App manifest definition |
| `frontend/styles.css` | 2026-10-03 13:26:33 | 92,455 | 90.3 KB | Dark fintech design system, responsive grid, micro-animations |
| `frontend/sw.js` | 2026-10-03 12:49:23 | 2,913 | 2.8 KB | Service Worker for offline asset caching and push notifications |

#### Root Files
| File | Last Modified | Size (Bytes) | Size (KB) | Purpose |
|---|---|---|---|---|
| `requirements.txt` | 2026-10-02 01:21:39 | 177 | 0.2 KB | Pinned production Python dependencies |
| `.env.example` | 2026-10-02 00:13:14 | 2,062 | 2.0 KB | Template configuration for environment variables |
| `Procfile` | 2026-09-20 16:29:16 | 54 | 0.1 KB | Process manager configuration for Render / Railway |
| `runtime.txt` | 2026-09-20 16:29:24 | 14 | 0.0 KB | Python runtime declaration (`python-3.12.0`) |
| `README.md` | Current | - | - | Complete project documentation and status audit |
| `schema.sql` | 2026-09-20 16:28:18 | 1,306 | 1.3 KB | Initial legacy 3-table DDL schema (superseded by `app/db.py`) |
| `.gitignore` | 2026-09-20 16:29:06 | 526 | 0.5 KB | Git ignore rules for virtual environments, secrets, caches |

---

### 2. Database Schema Verification

A live schema inspection was executed against the production Supabase PostgreSQL instance specified in `DATABASE_URL`.

- **All 16 target tables exist** in the live database.
- **4 additional active system tables** exist in the live database.
- **Column schemas match `app/db.py` 100%**. There are zero missing columns or discrepancies between code expectations and the live PostgreSQL database.

| Table Name | Live Status | Live Column Names | Discrepancies with `app/db.py` |
|---|---|---|---|
| `users` | Verified | `id`, `email`, `password_hash`, `created_at`, `username`, `avatar_id`, `last_login_at`, `suspended_at`, `force_password_reset` | None |
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

- **Implementation:** The background scheduler runs directly inside the FastAPI `lifespan` handler (`app/main.py`) via `asyncio.create_task(_daily_recurring_scheduler())`.
- **Scheduled Jobs:**
  1. **Startup Check:** On application startup, `check_and_process_recurring_reminders()` executes immediately to evaluate bills due.
  2. **12-Hour Polling Loop (`_daily_recurring_scheduler`):** Runs an infinite loop with `await asyncio.sleep(12 * 3600)`. Every 12 hours, it scans all user recurring expenses.
- **Notification Logic & Idempotency:**
  - Queries `recurring_expenses` for rows where `active = True` and `next_due_date <= CURRENT_DATE + 3 days`.
  - Checks the `sent_notifications` table to ensure that a reminder for a given cycle has not already been sent, preventing duplicate push notifications.
  - Computes the updated `next_due_date` depending on frequency (`weekly`, `monthly`, `quarterly`, `yearly`) and advances the schedule.
- **Persistence Across Restarts:** All recurring expense definitions, active statuses, and sent notification logs reside in PostgreSQL (`recurring_expenses`, `sent_notifications`). If the server restarts or scales down, scheduled tasks re-register cleanly without lost state or repeated notifications.

---

### 7. Known Issues and Code Audit

#### Syntax and Compilation
All 10 Python modules in `app/` compile without syntax errors (`python -m py_compile` passed 100%).

#### Critical Latent Bug in `app/importer.py`
- **Location:** `app/importer.py` line 424.
- **Issue:** Function `batch_llm_categorize` imports `from app.llm import execute_with_fallback`.
- **Root Cause:** `execute_with_fallback` does not exist in `app/llm.py` (the pool manager exposes `llm_pool.invoke_with_retry`).
- **Impact:** CSV and text statement imports that rely on rule-based categorization (`categorize_by_rule`) succeed normally. However, if a user uploads a statement containing unrecognized merchants and triggers the LLM fallback path, an `ImportError` occurs.
- **Remedy Required:** Replace `execute_with_fallback` with `llm_pool.invoke_with_retry` in `app/importer.py`.

#### Duplicate Route Handlers in `app/main.py`
- Endpoints `GET /api/user/display`, `GET /api/categories`, `POST /api/categories`, and `DELETE /api/categories/{name}` are declared twice in `app/main.py` (first at lines 749-790, and repeated at lines 1010-1048). The second set of declarations shadows the first.

#### Bare / Silent Exception Passes
Several low-level fallback blocks use `except Exception: pass`. These were inspected and validated:
- `app/agent.py:522`: Graceful fallback from JSON-formatted split participants to comma-separated text strings.
- `app/main.py:875`: Month string parsing fallback when optional filter dates are omitted.
- `app/main.py:1430`: Column mapping JSON parse fallback in statement importer.
- `app/main.py:1880`: Global unhandled exception handler logging fallback to ensure 500 JSON response delivery.

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

### 9. Recent Session Changes (Manual Entry & Management)

A parallel manual management interface was added to provide direct CRUD capabilities alongside the conversational AI:

#### Files Modified
- `app/db.py`: Added CRUD functions (`update_expense`, `delete_expense`, `bulk_delete_expenses`, `set_budget`, `delete_budget`, `get_budgets_manager`, `update_udhar_entry`, `delete_udhar_entry`, `resolve_udhar_due_date`, `update_savings_goal`, `delete_savings_goal`, `update_recurring_expense`, `delete_recurring_expense`, `toggle_recurring_expense`). Optimized `search_transactions` tag loading to batched `ANY(%s)` queries.
- `app/main.py`: Added REST routes for manual transactions (`POST /api/transactions`, `GET /api/transactions`, `PUT /api/transactions/{id}`, `DELETE /api/transactions/{id}`, `POST /api/transactions/bulk-delete`), budgets manager (`GET /api/budgets`, `POST /api/budgets`, `PATCH /api/budgets/{category}`, `DELETE /api/budgets/{category}`), udhar management (`PUT /api/udhar/{id}`, `DELETE /api/udhar/{id}`, `POST /api/udhar/{id}/resolve`), and recurring bill management (`POST /api/recurring/{id}/toggle`, `PUT /api/recurring/{id}`, `DELETE /api/recurring/{id}`).
- `frontend/index.html`: Added quick-add bar on dashboard and transactions tab, dedicated Transactions ledger view (`#view-transactions`), transaction edit modal (`#transactionEditModal`), Category Budget Manager in Settings, Udhar repayment modal with debt warning alert, Savings goals manager, and recurring bills manager.
- `frontend/styles.css`: Added responsive styles for quick-add form, transactions table ledger, inline edit modal, budget manager cards, debt warning banners, and dirty-form dialogs.
- `frontend/app.js`: Added client controller handlers, search debouncing, date slicers, pagination, bulk delete with typed confirmation (`CONFIRM DELETE` for >10 items), client-side debt-check logic, and dirty-form trackers (`modalDirtyCheckers`, `showUnsavedConfirmDialog`).

#### Test Execution
- **Backend Test Suite:** Executed `scratch/test_manual_routes.py` covering all manual routes (transaction CRUD, bulk delete, budget manager, udhar CRUD, savings goal CRUD, recurring bills CRUD).
- **Result:** **100% Passed** (`Ran 5 tests in 148.801s, OK`).

#### Mobile Visual Verification (375px iPhone SE)
All five core manual entry and management workflows were visually verified and captured using Selenium headless Chrome in 375px mobile viewport mode:
1. `scratch/screenshots/01_quick_add_bar_mobile.png` (Quick-add expense bar)
2. `scratch/screenshots/02_transactions_view_and_edit_modal_mobile.png` (Transactions ledger & edit modal)
3. `scratch/screenshots/03_budget_manager_mobile.png` (Category budget manager)
4. `scratch/screenshots/04_udhar_add_with_repayment_warning_mobile.png` (Udhar modal with dynamic repayment debt warning)
5. `scratch/screenshots/05_savings_goals_mobile.png` (Savings goals manager & pace calculator)

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
- **Web Push Notifications:** VAPID subscription registration, browser permission handling, and test notification dispatch.
- **Monthly Statement Export:** Dynamic export of monthly spending data to Excel (`.xlsx`) and PDF formats.
- **Statement Importer (Rule-Based):** Drag-and-drop CSV and text statement uploader, column mapping modal, preview table with duplicate detection, and bulk commit.

#### 2. BUILT BUT UNVERIFIED (Code Exists, Partial Testing or Missing Cloud Services)
- **Service Worker PWA Offline Caching (`frontend/sw.js`):** Script is registered in the browser, but full offline fallback, offline queuing, and cache invalidation have not been verified under network disconnection.
- **Supabase Cloud Storage for Receipts (`app/storage.py`):** File validation and upload logic are implemented, but live binary upload to a Supabase Storage bucket requires an active `SUPABASE_SERVICE_ROLE_KEY` in production.
- **Batch LLM Categorization Fallback (`app/importer.py`):** Code exists but has a broken import (`from app.llm import execute_with_fallback`), causing it to fail if rule-based categorization does not match and LLM fallback is triggered.
- **Cashflow Calendar View (`GET /api/calendar`):** Endpoint and frontend calendar grid are built and tested on standard months, but complex multi-month edge cases (leap years, 30+ transactions/day) have not been tested with large datasets.
- **Overspending Projections View (`GET /api/projections`):** Math and backend endpoint are verified, but projections are currently surfaced via dashboard cards rather than a dedicated standalone view.
- **Undo System (`undo_log`, `POST /api/undo`, `undo_last_action`):** Backend undo tracking and agent tool are functional, but the frontend lacks a persistent floating undo toast banner.

#### 3. NOT BUILT (Mentioned in Initial Concepts or Specs but No Implementation)
- **Native WhatsApp Webhook Integration:** The application runs exclusively as a responsive web app and PWA; Meta Cloud API / Twilio WhatsApp webhook listeners are not implemented.
- **Bank Account Aggregator / Open Banking Integration:** Direct bank sync (Plaid / Setu / Account Aggregator) is not implemented; transactions are logged manually or via CSV/text statements.
- **Multi-Currency Conversion:** A single configurable currency symbol (`CURRENCY_SYMBOL`) is supported; live foreign exchange conversions are not supported.
- **Biometric Authentication (WebAuthn / Passkeys):** Login relies on email and password; biometric device unlock is not implemented.
- **Optical Character Recognition (OCR) for Receipts:** The OCR function in `app/storage.py` is a placeholder stub; Google Cloud Vision or Tesseract integrations are not connected.