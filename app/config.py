"""
Central configuration. All config comes strictly from environment variables.
See .env.example for the full list.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Groq (LLM) — Multi-key fallback chain ---
    # GROQ_API_KEY is kept as an alias for PRIMARY for backward compat.
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_API_KEY_PRIMARY: str = os.getenv("GROQ_API_KEY_PRIMARY", "")
    GROQ_API_KEY_SECONDARY: str = os.getenv("GROQ_API_KEY_SECONDARY", "")
    GROQ_API_KEY_TERTIARY: str = os.getenv("GROQ_API_KEY_TERTIARY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Optional final fallback to a different provider (e.g. OpenAI, Together, etc.)
    FALLBACK_PROVIDER: str = os.getenv("FALLBACK_PROVIDER", "")
    FALLBACK_API_KEY: str = os.getenv("FALLBACK_API_KEY", "")
    FALLBACK_MODEL: str = os.getenv("FALLBACK_MODEL", "")

    # --- Storage (Supabase Postgres) ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # --- Supabase Storage (Receipts & Bills) ---
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "receipts")

    # --- Web Push (VAPID) ---
    # Default keys provided so Web Push works out of the box, can be overridden in .env
    VAPID_PUBLIC_KEY: str = os.getenv(
        "VAPID_PUBLIC_KEY",
        "BFgUUCw7TdlAzVVLljypdhnjNmR6HOWkLuxNWmOkth2sC2dGSeH6tCwX4RDN_Nr5FPQ3ZGsA9fZ59oRcxySljyA",
    )
    VAPID_PRIVATE_KEY: str = os.getenv(
        "VAPID_PRIVATE_KEY",
        "mMNnNYuz5PeeZaCgVP2uvqF_5VuC9omraznptIurZEE",
    )
    VAPID_SUBJECT: str = os.getenv("VAPID_SUBJECT", "mailto:admin@budgettracker.local")

    # --- Display ---
    CURRENCY_SYMBOL: str = os.getenv("CURRENCY_SYMBOL", "\u20b9")

    # --- Auth ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_DAYS: int = int(os.getenv("JWT_EXPIRATION_DAYS", "30"))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # --- Email (Resend HTTP API) ---
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")

    # --- Admin Authentication (Separate from user auth) ---
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")
    ADMIN_PASSWORD_HASH: str = os.getenv("ADMIN_PASSWORD_HASH", "")
    ADMIN_TOKEN_SECRET: str = os.getenv("ADMIN_TOKEN_SECRET", "")

    # --- Misc ---
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")

    def get_supabase_url(self) -> str:
        """Return SUPABASE_URL or infer it from DATABASE_URL if not explicitly set."""
        if self.SUPABASE_URL:
            return self.SUPABASE_URL.rstrip("/")
        if self.DATABASE_URL:
            import re
            m = re.search(r"postgres\.([a-zA-Z0-9]+):", self.DATABASE_URL)
            if m:
                return f"https://{m.group(1)}.supabase.co"
        return ""

    def get_groq_keys(self) -> list[dict]:
        """Return list of configured Groq API keys as {slot, key} dicts.
        PRIMARY alias: GROQ_API_KEY_PRIMARY takes precedence, falls back to GROQ_API_KEY."""
        keys = []
        primary = self.GROQ_API_KEY_PRIMARY or self.GROQ_API_KEY
        if primary:
            keys.append({"slot": "PRIMARY", "key": primary})
        if self.GROQ_API_KEY_SECONDARY:
            keys.append({"slot": "SECONDARY", "key": self.GROQ_API_KEY_SECONDARY})
        if self.GROQ_API_KEY_TERTIARY:
            keys.append({"slot": "TERTIARY", "key": self.GROQ_API_KEY_TERTIARY})
        return keys

    def has_fallback_provider(self) -> bool:
        """Check if a fallback provider is configured."""
        return bool(self.FALLBACK_PROVIDER and self.FALLBACK_API_KEY and self.FALLBACK_MODEL)

    def validate(self) -> None:
        """Validate that all required production environment variables are configured."""
        missing = []
        groq_keys = self.get_groq_keys()
        if not groq_keys and not self.has_fallback_provider():
            missing.append(
                "At least one GROQ_API_KEY (or GROQ_API_KEY_PRIMARY) must be set, "
                "OR configure FALLBACK_PROVIDER + FALLBACK_API_KEY + FALLBACK_MODEL. "
                "Get a free Groq key from https://console.groq.com/keys"
            )
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL (Supabase Postgres pooler connection string)")
        if not self.JWT_SECRET:
            missing.append("JWT_SECRET (generate with: python -c 'import secrets; print(secrets.token_hex(32))')")
        if not self.ADMIN_EMAIL:
            missing.append("ADMIN_EMAIL (Admin login email address)")
        if not self.ADMIN_PASSWORD_HASH:
            missing.append(
                "ADMIN_PASSWORD_HASH (Bcrypt hash of admin password; generate with: "
                "python -c \"import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())\")"
            )
        if not self.ADMIN_TOKEN_SECRET:
            missing.append("ADMIN_TOKEN_SECRET (Separate JWT secret for admin panel token signing)")

        if missing:
            raise RuntimeError(
                "\n[CONFIG ERROR] Application cannot start due to missing environment variables:\n"
                + "\n".join(f"  - {m}" for m in missing)
                + "\n\nPlease define these in your .env file or deployment host environment settings."
            )


settings = Settings()
