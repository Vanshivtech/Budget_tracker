"""
Email verification and notification service for SAARTH.
Handles disposable domain checks, OTP generation, and email delivery via Resend HTTP API.
"""
import logging
import os
import re
import secrets
import resend

from app.config import settings

logger = logging.getLogger(__name__)

# Standard email regex: name@domain.tld
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
)

# Blocklist of disposable email domains (top 20+ disposable providers)
DISPOSABLE_EMAIL_DOMAINS: set[str] = {
    # Specifically requested in prompt
    "mailinator.com",
    "tempmail.com",
    "guerrillamail.com",
    "10minutemail.com",
    "throwam.com",
    "yopmail.com",
    # Top 20 disposable providers
    "trashmail.com",
    "getairmail.com",
    "sharklasers.com",
    "dispostable.com",
    "fakeinbox.com",
    "guerrillamailblock.com",
    "mohmal.com",
    "generator.email",
    "yopmail.fr",
    "yopmail.net",
    "dropmail.me",
    "inboxkitten.com",
    "mytemp.email",
    "crazymailing.com",
    "10minutemail.net",
    "tempail.com",
    "burnermail.io",
    "nada.ltd",
    "getnada.com",
    "disposablemail.com",
    "temp-mail.org",
    "maildrop.cc",
    "fakemailgenerator.com",
    "emailondeck.com",
}


def validate_email_address(email: str) -> tuple[bool, str]:
    """Validate email format and verify it is not from a disposable domain.

    Returns:
        (is_valid: bool, error_message: str)
    """
    if not email or not isinstance(email, str):
        return False, "Email address is required."

    cleaned = email.strip().lower()
    if not EMAIL_REGEX.match(cleaned):
        return False, "Please provide a valid email address."

    parts = cleaned.split("@")
    if len(parts) != 2:
        return False, "Please provide a valid email address."

    domain = parts[1]
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return (
            False,
            "Disposable email addresses are not allowed. Please use a valid personal or work email.",
        )

    return True, ""


def generate_otp() -> str:
    """Generate a secure 6-digit numeric OTP."""
    return f"{secrets.randbelow(1000000):06d}"


resend.api_key = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")


def send_otp_email(to_email: str, otp: str):
    """Send 6-digit OTP verification email via Resend HTTP API."""
    key = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")
    if key:
        resend.api_key = key

    # If RESEND_API_KEY is not configured (e.g. in test or local dev without a key),
    # log cleanly so offline tests do not crash.
    if not resend.api_key or resend.api_key.startswith("re_test") or resend.api_key == "re_xxxxxxxxxxxx":
        print(f"[Resend NOTICE] RESEND_API_KEY not configured. OTP for {to_email}: {otp}")
        return True

    try:
        response = resend.Emails.send({
            "from": "SAARTH <onboarding@resend.dev>",
            "to": [to_email],
            "subject": "Your SAARTH verification code",
            "html": f"""
            <div style="font-family: sans-serif; max-width: 400px; 
                        margin: 0 auto; padding: 24px;">
              <h2 style="color: #111;">Your SAARTH code</h2>
              <p>Use this code to verify your account:</p>
              <div style="font-size: 36px; font-weight: bold; 
                          letter-spacing: 8px; color: #22c55e; 
                          padding: 16px 0;">{otp}</div>
              <p style="color: #666;">Valid for 10 minutes. 
                 Do not share this code with anyone.</p>
              <hr style="border: none; border-top: 1px solid #eee;">
              <p style="color: #999; font-size: 12px;">
                SAARTH — Know what you can safely spend today.
              </p>
            </div>
            """
        })
        return True
    except Exception as e:
        print(f"Resend email error: {e}")
        raise e
