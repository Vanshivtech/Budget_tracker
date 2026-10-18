"""
Push notification service supporting:
1. Firebase Cloud Messaging (FCM) for native Android app (Capacitor).
2. Web Push (RFC 8291, RFC 8292) using VAPID standards for browsers and PWAs.
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from pywebpush import webpush, WebPushException

from app.config import settings

logger = logging.getLogger(__name__)

_firebase_initialized = False


def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def get_firebase_app() -> bool:
    """Lazily and safely initialize Firebase Admin SDK using service account JSON."""
    global _firebase_initialized
    if _firebase_initialized:
        return True

    sa_config = settings.FIREBASE_SERVICE_ACCOUNT_JSON
    if not sa_config:
        return False

    sa_path = Path(sa_config)
    if not sa_path.is_absolute():
        project_root = Path(__file__).resolve().parent.parent
        sa_path = project_root / sa_config

    if not sa_path.exists():
        logger.warning(f"[FCM] Service account file not found at {sa_path}")
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(str(sa_path))
            firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("[FCM] Firebase Admin SDK initialized successfully")
        return True
    except Exception as e:
        logger.error(f"[FCM] Failed to initialize Firebase Admin SDK: {e}")
        return False


def send_fcm_notification(
    token: str,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "general",
    data_payload: Optional[dict] = None,
) -> tuple[bool, str]:
    """Send an FCM message to an Android device token via Firebase Admin SDK."""
    if not get_firebase_app():
        logger.warning("[FCM] Firebase Admin is not initialized. Falling back silently.")
        return False, "Firebase not configured"

    try:
        from firebase_admin import messaging

        payload_data = {
            "title": str(title),
            "body": str(body),
            "url": str(url),
            "tag": str(tag),
        }
        if data_payload:
            for k, v in data_payload.items():
                payload_data[str(k)] = str(v)

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=payload_data,
            token=token,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="saarth_alerts",
                    icon="ic_launcher",
                ),
            ),
        )
        response = messaging.send(message)
        _safe_print(f"✅ FCM sent successfully to {token[:20]}... id={response}")
        return True, response
    except Exception as ex:
        _safe_print(f"❌ FCM send failed: {ex}")
        err_str = str(ex).lower()
        if "not-found" in err_str or "unregistered" in err_str or "invalid-argument" in err_str or "invalid registration" in err_str:
            try:
                from app.db import remove_push_subscription
                remove_push_subscription(token)
                _safe_print(f"[FCM] Deleted invalid/unregistered token {token[:20]}...")
            except Exception as rem_err:
                logger.error(f"[FCM] Failed to delete invalid token: {rem_err}")
        return False, str(ex)


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
        _safe_print(f"✅ Web Push sent successfully to {ep[:30]}...")
        return True, status, ""
    except WebPushException as ex:
        _safe_print(f"❌ Web Push failed: {ex}")
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
    - If device is Android FCM (type == 'fcm'), dispatches via Firebase Admin SDK.
    - If device is Browser Web Push (type == 'web'), dispatches via Web Push VAPID.
    - If FCM service account is unconfigured, silently falls back.
    Prunes expired subscriptions automatically.
    Returns the count of successfully notified devices.
    """
    from app.db import get_db_cursor

    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT endpoint, p256dh, auth, type 
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
        sub_type = (sub.get("type") or "web").lower()
        if sub_type == "fcm":
            # Send via Firebase Cloud Messaging
            success, resp = send_fcm_notification(
                token=sub["endpoint"],
                title=title,
                body=body,
                url=url,
            )
            if success:
                sent_count += 1
            else:
                logger.debug(f"[PUSH] FCM send to user {user_id} unhandled: {resp}")
        else:
            # Send via Web Push
            success, code, err = send_web_push(
                endpoint=sub["endpoint"],
                p256dh=sub.get("p256dh"),
                auth=sub.get("auth"),
                title=title,
                body=body,
                url=url,
            )
            if success:
                sent_count += 1
            elif code in (404, 410):
                try:
                    delete_subscription(sub["endpoint"])
                except Exception as del_err:
                    logger.error(f"[PUSH] Failed to remove expired subscription {sub['endpoint']}: {del_err}")

    _safe_print(f"🔔 Notifications delivered to user {user_id} ({sent_count} device(s)): {title}")
    return sent_count


def send_engagement_notification(
    subscription_info: dict,
    title: str,
    body: str,
    url: str = "/",
) -> tuple[bool, int, str]:
    """Send an engagement push notification to a single browser or FCM endpoint."""
    sub_type = (subscription_info.get("type") or "web").lower()
    if sub_type == "fcm":
        success, resp = send_fcm_notification(
            token=subscription_info.get("endpoint", ""),
            title=title,
            body=body,
            url=url,
            tag="engagement",
        )
        return success, 200 if success else 400, resp

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
