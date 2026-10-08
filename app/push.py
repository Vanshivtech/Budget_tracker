"""
Web Push notification service using VAPID standards (RFC 8291, RFC 8292).
Manages subscriptions, sending encrypted push messages, handling unsubscribes,
and pruning expired endpoints (HTTP 404/410).
"""
import json
import logging
import sys
from typing import Optional, Dict, Any
from pywebpush import webpush, WebPushException

from app.config import settings

logger = logging.getLogger(__name__)


def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def send_web_push(
    subscription_info: dict,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "general",
) -> tuple[bool, int, str]:
    """Send an encrypted Web Push notification to a single browser endpoint."""
    endpoint = subscription_info.get("endpoint", "")
    if not settings.VAPID_PRIVATE_KEY:
        logger.warning("[PUSH] VAPID_PRIVATE_KEY not set. Cannot send push notification.")
        _safe_print("[PUSH] VAPID_PRIVATE_KEY not set. Cannot send push notification.")
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
        _safe_print(f"✅ Push sent successfully to {endpoint[:30]}...")
        return True, status, ""
    except WebPushException as ex:
        _safe_print(f"❌ Push failed: {ex}")
        _safe_print(f"❌ Response: {ex.response.text if ex.response else 'no response'}")
        _safe_print(f"❌ Status: {ex.response.status_code if ex.response else 'none'}")
        status_code = ex.response.status_code if ex.response is not None else 0
        if status_code in (404, 410, 403):
            try:
                from app.db import remove_push_subscription
                remove_push_subscription(endpoint)
                _safe_print(f"[PUSH] Deleted invalid/expired subscription {endpoint} (HTTP {status_code})")
            except Exception as rem_err:
                logger.error(f"[PUSH] Failed to delete invalid subscription {endpoint}: {rem_err}")
        raise ex
    except Exception as ex:
        _safe_print(f"❌ Push unexpected error: {ex}")
        raise ex


def send_engagement_notification(
    subscription_info: dict,
    title: str,
    body: str,
    url: str = "/",
) -> tuple[bool, int, str]:
    """Send an engagement push notification to a single browser endpoint."""
    try:
        return send_web_push(
            subscription_info=subscription_info,
            title=title,
            body=body,
            url=url,
            tag="engagement",
        )
    except Exception as ex:
        status_code = getattr(getattr(ex, "response", None), "status_code", 0) or 0
        return False, status_code, str(ex)

