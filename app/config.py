"""
Central configuration. All config comes strictly from environment variables.
See .env.example for the full list.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Groq (LLM) ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # --- Storage (Supabase Postgres) ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # --- Display ---
    CURRENCY_SYMBOL: str = os.getenv("CURRENCY_SYMBOL", "₹")

    # --- Auth ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_DAYS: int = int(os.getenv("JWT_EXPIRATION_DAYS", "30"))

    # --- Misc ---
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")

    def validate(self) -> None:
        """Validate that all required production environment variables are configured."""
        missing = []
        if not self.GROQ_API_KEY:
            missing.append("GROQ_API_KEY (get a free key from https://console.groq.com/keys)")
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL (Supabase Postgres pooler connection string)")
        if not self.JWT_SECRET:
            missing.append("JWT_SECRET (generate with: python -c 'import secrets; print(secrets.token_hex(32))')")

        if missing:
            raise RuntimeError(
                "\n[CONFIG ERROR] Application cannot start due to missing environment variables:\n"
                + "\n".join(f"  • {m}" for m in missing)
                + "\n\nPlease define these in your .env file or deployment host environment settings."
            )


settings = Settings()
