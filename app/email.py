"""
Email verification and notification service for SAARTH.
Handles disposable domain checks, OTP generation, and email sending via SMTP.
"""
import logging
import re
import secrets
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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


def build_otp_html(otp: str) -> str:
    """Build clean HTML template for OTP email."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Your SAARTH verification code</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #0b132b;
      color: #f8fafc;
      margin: 0;
      padding: 32px 16px;
    }}
    .container {{
      max-width: 480px;
      margin: 0 auto;
      background-color: #1c2541;
      border-radius: 14px;
      padding: 36px 28px;
      border: 1px solid #3a506b;
      box-shadow: 0 10px 25px rgba(0,0,0,0.3);
    }}
    .brand {{
      font-size: 24px;
      font-weight: 800;
      letter-spacing: 1px;
      color: #6fffe9;
      margin-bottom: 20px;
      text-align: center;
    }}
    .heading {{
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 12px;
      color: #ffffff;
      text-align: center;
    }}
    .desc {{
      font-size: 14px;
      color: #cbd5e1;
      line-height: 1.6;
      margin-bottom: 24px;
      text-align: center;
    }}
    .otp-code {{
      background: #0b132b;
      border: 2px dashed #6fffe9;
      border-radius: 10px;
      padding: 16px;
      text-align: center;
      font-size: 34px;
      font-weight: 800;
      letter-spacing: 8px;
      color: #6fffe9;
      margin: 0 auto 24px auto;
      user-select: all;
    }}
    .note {{
      font-size: 12px;
      color: #94a3b8;
      text-align: center;
      line-height: 1.5;
    }}
    .footer {{
      margin-top: 28px;
      padding-top: 16px;
      border-top: 1px solid #3a506b;
      font-size: 11px;
      color: #64748b;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="brand">SAARTH</div>
    <div class="heading">Verify your email address</div>
    <div class="desc">
      Use the 6-digit verification code below to activate your SAARTH account.
      This code is valid for <strong>10 minutes</strong>.
    </div>
    <div class="otp-code">{otp}</div>
    <div class="note">
      If you did not request this verification code, please ignore this email.
    </div>
    <div class="footer">
      &copy; SAARTH &bull; Personal Financial Assistant
    </div>
  </div>
</body>
</html>"""


def send_otp_email(to_email: str, otp: str) -> bool:
    """Send OTP email with subject 'Your SAARTH verification code'.

    Uses SMTP when configured; gracefully logs to stdout/logger if SMTP is not configured.
    """
    subject = "Your SAARTH verification code"
    text_content = (
        f"Your SAARTH verification code is: {otp}\n\n"
        f"This code is valid for 10 minutes. Use it to activate your account.\n"
        f"If you did not create an account, you can safely ignore this email."
    )
    html_content = build_otp_html(otp)

    # If SMTP is not configured, log clearly and succeed (ideal for local dev / testing)
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.info(
            "[EMAIL SERVICE] SMTP not configured. OTP for %s: %s (Subject: '%s')",
            to_email,
            otp,
            subject,
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email

        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        msg.attach(part1)
        msg.attach(part2)

        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_TLS:
                    server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())

        logger.info("Successfully sent OTP email to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send OTP email to %s: %s", to_email, e)
        # Even on SMTP delivery failure in test environments, avoid hard crashing
        return False
