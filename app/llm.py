"""
LLM key pool manager with automatic failover.

Manages multiple Groq API keys with:
  - Round-robin key selection (skip cooled-down or disabled keys)
  - Rate-limit cooldown (Retry-After header, default 60s)
  - Auth-failure disablement (key disabled until restart, logged warning)
  - Max 3 attempts per request across all keys
  - Optional fallback to a different LLM provider
  - Never logs full keys -- only slot name + last 4 chars
"""
import logging
import time
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq

from app.config import settings

logger = logging.getLogger("budget-tracker.llm")

# Error codes / status codes that trigger specific retry behaviour
_RATE_LIMIT_CODES = {429}
_AUTH_FAIL_CODES = {401, 403}
_NON_RETRYABLE_CODES = {400}

# Strings in error messages that indicate quota/rate issues
_RATE_LIMIT_PHRASES = ("rate_limit", "rate limit", "quota", "too many requests", "resource_exhausted")
_AUTH_FAIL_PHRASES = ("invalid_api_key", "invalid api key", "unauthorized", "forbidden", "authentication")
_TIMEOUT_PHRASES = ("timeout", "timed out", "connection error", "connect timeout")


def _mask_key(key: str) -> str:
    """Return last 4 chars of a key for safe logging."""
    if not key or len(key) < 4:
        return "****"
    return f"...{key[-4:]}"


class _KeySlot:
    """Tracks a single API key's health state."""

    __slots__ = ("slot_name", "key", "disabled", "cooldown_until", "provider", "last_used")

    def __init__(self, slot_name: str, key: str, provider: str = "groq"):
        self.slot_name = slot_name
        self.key = key
        self.disabled = False
        self.cooldown_until: float = 0.0
        self.provider = provider
        self.last_used: float | None = None

    def is_available(self) -> bool:
        if self.disabled:
            return False
        if self.cooldown_until > time.time():
            return False
        return True

    def cool_down(self, seconds: float = 60.0):
        self.cooldown_until = time.time() + seconds
        logger.warning(
            "Key slot %s (%s) rate-limited, cooling down for %.0fs",
            self.slot_name, _mask_key(self.key), seconds,
        )

    def disable(self):
        self.disabled = True
        logger.warning(
            "Key slot %s (%s) DISABLED due to auth failure -- will not retry until restart",
            self.slot_name, _mask_key(self.key),
        )

    def __repr__(self):
        return f"<KeySlot {self.slot_name} avail={self.is_available()}>"


class LLMPool:
    """Manages LLM key rotation and failover."""

    _FRIENDLY_ERROR = "The assistant is busy right now. Please try again in a minute."
    _MAX_ATTEMPTS = 3

    def __init__(self):
        self._slots: list[_KeySlot] = []
        self._model_cache: dict[str, BaseChatModel] = {}
        self._init_slots()

    def _init_slots(self):
        """Build key slots from config."""
        for kd in settings.get_groq_keys():
            slot = _KeySlot(slot_name=kd["slot"], key=kd["key"], provider="groq")
            self._slots.append(slot)
            logger.info("Registered Groq key slot %s (%s)", kd["slot"], _mask_key(kd["key"]))

        if settings.has_fallback_provider():
            slot = _KeySlot(
                slot_name="FALLBACK",
                key=settings.FALLBACK_API_KEY,
                provider=settings.FALLBACK_PROVIDER.lower(),
            )
            self._slots.append(slot)
            logger.info(
                "Registered fallback provider %s slot (%s)",
                settings.FALLBACK_PROVIDER, _mask_key(settings.FALLBACK_API_KEY),
            )

        if not self._slots:
            raise RuntimeError("[LLM] No API keys configured. Cannot start.")

    def _get_model(self, slot: _KeySlot) -> BaseChatModel:
        """Get or create a cached LLM instance for a key slot."""
        cache_key = f"{slot.provider}:{slot.slot_name}"
        if cache_key not in self._model_cache:
            if slot.provider == "groq":
                self._model_cache[cache_key] = ChatGroq(
                    model=settings.GROQ_MODEL,
                    api_key=slot.key,
                )
            else:
                # Fallback provider: try langchain_openai-compatible interface
                try:
                    from langchain_openai import ChatOpenAI
                    self._model_cache[cache_key] = ChatOpenAI(
                        model=settings.FALLBACK_MODEL,
                        api_key=slot.key,
                    )
                except ImportError:
                    logger.error("langchain_openai not installed; fallback provider unavailable")
                    slot.disable()
                    raise
        return self._model_cache[cache_key]

    def _classify_error(self, error: Exception) -> str:
        """Classify an error as 'rate_limit', 'auth_fail', 'timeout', 'non_retryable', or 'unknown'."""
        err_str = str(error).lower()

        # Check for HTTP status codes in error
        status_code = getattr(error, "status_code", None)
        if status_code is None:
            # Try to extract from error message
            for code in _RATE_LIMIT_CODES:
                if str(code) in err_str:
                    status_code = code
                    break
            if status_code is None:
                for code in _AUTH_FAIL_CODES:
                    if str(code) in err_str:
                        status_code = code
                        break
            if status_code is None:
                for code in _NON_RETRYABLE_CODES:
                    if str(code) in err_str:
                        status_code = code
                        break

        if status_code in _RATE_LIMIT_CODES:
            return "rate_limit"
        if status_code in _AUTH_FAIL_CODES:
            return "auth_fail"
        if status_code in _NON_RETRYABLE_CODES:
            return "non_retryable"

        # Phrase-based fallback
        for phrase in _RATE_LIMIT_PHRASES:
            if phrase in err_str:
                return "rate_limit"
        for phrase in _AUTH_FAIL_PHRASES:
            if phrase in err_str:
                return "auth_fail"
        for phrase in _TIMEOUT_PHRASES:
            if phrase in err_str:
                return "timeout"

        return "unknown"

    def _extract_retry_after(self, error: Exception) -> float:
        """Try to extract Retry-After seconds from an error. Default 60s."""
        try:
            ra = getattr(error, "headers", {}).get("Retry-After") or getattr(error, "retry_after", None)
            if ra is not None:
                return float(ra)
        except (TypeError, ValueError):
            pass
        return 60.0

    def get_available_model(self) -> tuple[BaseChatModel, _KeySlot] | None:
        """Return (model, slot) for the first available key, or None."""
        for slot in self._slots:
            if slot.is_available():
                try:
                    return self._get_model(slot), slot
                except Exception:
                    continue
        return None

    def invoke_with_retry(self, invoke_fn, *args, **kwargs) -> Any:
        """Call invoke_fn(model, *args, **kwargs) with up to MAX_ATTEMPTS retries across keys.

        invoke_fn should be a callable that takes (model, *args, **kwargs) and returns the result.
        Non-retryable errors (400, tool-schema) are raised immediately.
        Returns the friendly error string if all attempts fail.
        """
        attempts = 0
        last_error = None

        while attempts < self._MAX_ATTEMPTS:
            pair = self.get_available_model()
            if pair is None:
                logger.warning("No available LLM keys -- all rate-limited or disabled")
                return self._FRIENDLY_ERROR

            model, slot = pair
            slot.last_used = time.time()
            attempts += 1

            try:
                result = invoke_fn(model, *args, **kwargs)
                return result
            except Exception as e:
                last_error = e
                err_type = self._classify_error(e)
                logger.warning(
                    "LLM call failed on slot %s (%s), attempt %d/%d: %s [%s]",
                    slot.slot_name, _mask_key(slot.key), attempts, self._MAX_ATTEMPTS,
                    type(e).__name__, err_type,
                )

                if err_type == "non_retryable":
                    logger.error("Non-retryable error on slot %s: %s", slot.slot_name, e)
                    raise

                if err_type == "rate_limit":
                    retry_after = self._extract_retry_after(e)
                    slot.cool_down(retry_after)
                elif err_type == "auth_fail":
                    slot.disable()
                elif err_type == "timeout":
                    slot.cool_down(30.0)
                else:
                    # Unknown error -- cool down briefly and try next
                    slot.cool_down(15.0)

        logger.error("All %d LLM attempts exhausted. Last error: %s", self._MAX_ATTEMPTS, last_error)
        return self._FRIENDLY_ERROR

    def get_pool_status(self) -> list[dict]:
        """Return the health state, cooldown, and last used time for each configured key slot."""
        from datetime import datetime, timezone
        statuses = []
        now = time.time()
        for slot in self._slots:
            if slot.disabled:
                state = "disabled"
            elif slot.cooldown_until > now:
                state = "cooling"
            else:
                state = "healthy"

            last_used_str = (
                datetime.fromtimestamp(slot.last_used, timezone.utc).isoformat()
                if slot.last_used
                else None
            )
            statuses.append({
                "slot": slot.slot_name,
                "provider": slot.provider,
                "state": state,
                "last_used": last_used_str,
                "key_masked": _mask_key(slot.key),
                "cooldown_remaining": max(0, int(slot.cooldown_until - now)) if slot.cooldown_until > now else 0,
            })
        return statuses


# Module-level singleton
llm_pool = LLMPool()
