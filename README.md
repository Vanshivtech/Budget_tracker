# AI Budget Tracker & Savings Assistant

A multi-user, AI-powered personal finance web app built for cloud deployment. Track expenses, set budgets, edit transactions, and monitor spending in real time through natural conversation with a Groq-powered LLM assistant.

## Key Features

- **User Authentication**: Secure email + password signup and login, bcrypt password hashing, and signed JWT access tokens.
- **Multi-User Isolation**: Every transaction and budget is strictly scoped to the authenticated user's ID at both the database and AI agent tool level.
- **Natural Language Edit & Delete**: Tell the assistant *"actually it was 650"* or *"delete the lunch expense"* — the agent finds the right entry and confirms changes accurately.
- **Instant Budget Overview**: Live dashboard featuring monthly total spend, category cards sorted by spend with percentage badges and color-coded progress bars, and a recent transactions list.
- **Cloud-Ready Storage**: Powered by Supabase Postgres with connection pooling, ready for serverless and container hosts.

---

## Quick Start (Local Development)

### 1. Enter the project directory

```bash
cd Whatsapp_budget_tracker
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Windows (Command Prompt)
venv\Scripts\activate.bat

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

Copy `.env.example` to `.env`:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Edit `.env` and provide your settings:

```env
GROQ_API_KEY=gsk_your_actual_groq_key_here
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=postgresql://postgres.yourprojectref:yourpassword@aws-0-region.pooler.supabase.com:6543/postgres
JWT_SECRET=your_generated_random_secret_hex_here
```

> **Tip:** Generate a secure `JWT_SECRET` with:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

### 5. Run the app

```bash
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

---

## Deploy to Production (Supabase + Render / Railway)

### Step 1: Set up Supabase Postgres

1. Create a free account at [supabase.com](https://supabase.com) and create a new project.
2. Go to **Project Settings** -> **Database** -> **Connection String**.
3. Select **URI** and choose either **Session pooler** (port `5432`) or **Transaction pooler** (port `6543`).
   > **Important:** Always use the pooler URI (not the direct connection) for compatibility with serverless or cloud-hosted container environments.
4. Copy the connection URI and replace `[YOUR-PASSWORD]` with your actual database password. This is your `DATABASE_URL`.
5. *(Optional)* Go to the **SQL Editor** in your Supabase dashboard, paste the contents of [`schema.sql`](schema.sql), and click **Run**. (The application's `init_db()` will also auto-create tables on first boot if they don't exist).

### Step 2: Push code to GitHub

Make sure `.env` is **not** tracked (it is protected by `.gitignore`):

```bash
git add .
git commit -m "Deploy readiness: Supabase Postgres migration, secrets hygiene, and Procfile"
git push origin main
```

### Step 3: Deploy on Render or Railway

#### Option A: Render
1. Go to [render.com](https://render.com) and click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Configure the service:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (or let Render detect the `Procfile`)
4. Under **Environment Variables**, add:
   - `GROQ_API_KEY` = your Groq API key
   - `GROQ_MODEL` = `llama-3.3-70b-versatile` (or your chosen model)
   - `DATABASE_URL` = your Supabase pooler URI
   - `JWT_SECRET` = your generated 32-byte hex secret
   - `JWT_ALGORITHM` = `HS256`
   - `JWT_EXPIRATION_DAYS` = `30`
   - `TIMEZONE` = `Asia/Kolkata`
5. Click **Deploy Web Service**.

#### Option B: Railway
1. Go to [railway.app](https://railway.app) and click **New Project** -> **Deploy from GitHub repo**.
2. Select your repository.
3. Under **Variables**, add the same environment variables as listed above.
4. Railway automatically detects `Procfile` and `runtime.txt` (`python-3.12.0`) and deploys the app.

### Step 4: Verify Deployment

Once deployed, verify:
- Health check: `https://your-app-url.onrender.com/api/health` -> `{"status":"ok"}`
- Open `https://your-app-url.onrender.com/` in your browser to sign up, log in, and track your budget!

---

## Architecture & Codebase Structure

```
Whatsapp_budget_tracker/
├── app/
│   ├── __init__.py      # Package marker
│   ├── main.py          # FastAPI application & API routes
│   ├── auth.py          # bcrypt password hashing & JWT token handling
│   ├── agent.py         # LangGraph ReAct agent & scoped finance tools
│   ├── db.py            # Supabase Postgres storage layer with connection pool
│   └── config.py        # Central configuration, env loading & startup validation
├── frontend/
│   ├── index.html       # Auth modal + two-pane chat & overview dashboard
│   ├── styles.css       # Dark fintech theme with Inter typography
│   └── app.js           # Client auth, dynamic rendering & chat exchange
├── .env.example         # Template for environment variables
├── .gitignore           # Ignores .env, .db files, caches, and secrets
├── Procfile             # Process configuration for Render/Railway
├── runtime.txt          # Python runtime pinning (3.12.0)
├── schema.sql           # DDL schema for Supabase Postgres
├── requirements.txt     # Pinned production dependencies
└── README.md
```

### API Endpoints

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `POST` | `/api/signup` | No | Register new account with email & password |
| `POST` | `/api/login` | No | Authenticate and obtain signed JWT access token |
| `POST` | `/api/chat` | **Yes** (Bearer) | Send message to AI assistant (user-scoped) |
| `GET` | `/api/summary` | **Yes** (Bearer) | Fetch monthly categories, spend, and recent transactions |
| `GET` | `/api/health` | No | Service health check |

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn
- **Security:** bcrypt, PyJWT
- **AI Agent:** LangGraph (`create_react_agent`) + Groq LLM via `langchain-groq`
- **Database:** Supabase Postgres via `psycopg2-binary` (pooled connections)
- **Frontend:** Vanilla HTML5, CSS3 (Dark Fintech Design System), JavaScript (ES6)