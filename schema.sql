-- ================================================================
-- Supabase Postgres Schema for AI Budget Tracker
-- Run this in your Supabase project's SQL Editor (SQL tab in dashboard)
-- ================================================================

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    amount      NUMERIC(12, 2) NOT NULL,
    category    VARCHAR(100) NOT NULL,
    note        TEXT DEFAULT '',
    raw_message TEXT DEFAULT ''
);

-- 3. Budgets Table
CREATE TABLE IF NOT EXISTS budgets (
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category      VARCHAR(100) NOT NULL,
    monthly_limit NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (user_id, category)
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_budgets_user ON budgets(user_id);
