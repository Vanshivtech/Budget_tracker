"""
Web Push notification service using VAPID standards (RFC 8291, RFC 8292).
Manages subscriptions, sending encrypted push messages, handling unsubscribes,
and pruning expired endpoints (HTTP 404/410).
"""
import json
import logging
from typing import Optional, Dict, Any
from pywebpush import webpush, WebPushException

from app.config import settings

logger = logging.getLogger(__name__)


def send_web_push(
    subscription_info: dict,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "general",
) -> tuple[bool, int, str]:
    """Send an encrypted Web Push notification to a single browser endpoint.
    subscription_info format:
    {
        "endpoint": "https://...",
        "keys": {
            "p256dh": "...",
            "auth": "..."
        }
    }
    Returns: (success: bool, status_code: int, error_message: str)
    """
    if not settings.VAPID_PRIVATE_KEY:
        logger.warning("VAPID_PRIVATE_KEY not set. Cannot send push notification.")
        return False, 0, "VAPID private key is not configured"

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": tag,
    })

    vapid_claims = {
        "sub": settings.VAPID_SUBJECT,
    }

    try:
        response = webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims=vapid_claims,
            timeout=10,
        )
        status = response.status_code if hasattr(response, "status_code") else 201
        logger.info(f"Push notification sent successfully, status: {status}")
        return True, status, ""
    except WebPushException as ex:
        status_code = 0
        if ex.response is not None:
            status_code = ex.response.status_code
        logger.warning(f"WebPushException sending to {subscription_info.get('endpoint')[:30]}...: {ex} (HTTP {status_code})")
        return False, status_code, str(ex)
    except Exception as ex:
        logger.error(f"Unexpected error sending push notification: {ex}")
        return False, 0, str(ex)
