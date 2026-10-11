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
    subscription_info: Optional[dict] = None,
    title: str = "",
    body: str = "",
    url: str = "/",
    tag: str = "general",
    endpoint: Optional[str] = None,
    p256dh: Optional[str] = None,
    auth: Optional[str] = None,
) -> tuple[bool, int, str]:
    """Send an encrypted Web Push notification to a single browser endpoint."""
    if subscription_info is None and endpoint:
        subscription_info = {
            "endpoint": endpoint,
            "keys": {
                "p256dh": p256dh or "",
                "auth": auth or "",
            },
        }

    if not subscription_info:
        return False, 400, "Missing subscription info"

    ep = subscription_info.get("endpoint", "")
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
        _safe_print(f"✅ Push sent successfully to {ep[:30]}...")
        return True, status, ""
    except WebPushException as ex:
        _safe_print(f"❌ Push failed: {ex}")
        status_code = ex.response.status_code if ex.response is not None else 0
        resp_text = ex.response.text if ex.response is not None else ""
        if status_code in (404, 410, 403):
            try:
                from app.db import remove_push_subscription
                remove_push_subscription(ep)
                _safe_print(f"[PUSH] Deleted invalid/expired subscription {ep} (HTTP {status_code})")
            except Exception as rem_err:
                logger.error(f"[PUSH] Failed to delete invalid subscription {ep}: {rem_err}")
        return False, status_code, f"{resp_text or str(ex)}"
    except Exception as ex:
        _safe_print(f"❌ Push unexpected error: {ex}")
        return False, 0, str(ex)


def delete_subscription(endpoint: str) -> bool:
    """Helper alias to remove push subscription by endpoint."""
    from app.db import remove_push_subscription
    return remove_push_subscription(endpoint)


def send_push_to_user(
    user_id: int,
    title: str,
    body: str,
    url: str = "/",
) -> int:
    """
    Send push notification to all active devices registered by user_id.
    Prunes expired subscriptions automatically.
    Returns the count of successfully notified devices.
    """
    from app.db import get_db_cursor, remove_push_subscription

    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT endpoint, p256dh, auth 
            FROM push_subscriptions 
            WHERE user_id = %s
            """,
            (user_id,),
        )
        subscriptions = cur.fetchall()

    if not subscriptions:
        logger.info(f"[PUSH] No active push subscriptions for user {user_id}")
        return 0

    sent_count = 0
    for sub in subscriptions:
        success, code, err = send_web_push(
            endpoint=sub["endpoint"],
            p256dh=sub["p256dh"],
            auth=sub["auth"],
            title=title,
            body=body,
            url=url,
        )
        if success:
            sent_count += 1
        elif code in (404, 410):
            # Subscription expired, delete it
            try:
                delete_subscription(sub["endpoint"])
            except Exception as del_err:
                logger.error(f"[PUSH] Failed to remove expired subscription {sub['endpoint']}: {del_err}")

    _safe_print(f"🔔 Push sent to user {user_id}: {title}")
    return sent_count


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
